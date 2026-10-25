"""Web Push notification service (VAPID key management and push delivery)."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import os
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush

from games_platform.core.db import Database

logger = logging.getLogger(__name__)

VAPID_SETTINGS_KEY = "vapid_keys"
DEFAULT_VAPID_CLAIMS_SUB = "mailto:games@jakob-r.de"
PUSH_TTL_SECONDS = 300
MAX_PUSH_SUBSCRIPTIONS_PER_PLAYER = 5
ALLOWED_PUSH_HOSTS = frozenset(
    {
        "fcm.googleapis.com",
        "updates.push.services.mozilla.com",
        "web.push.apple.com",
    }
)
ALLOWED_PUSH_HOST_SUFFIXES = (
    ".push.apple.com",
    ".notify.windows.com",
)
EXPIRED_PUSH_STATUS_CODES = frozenset({401, 403, 404, 410})


class PushEndpointError(ValueError):
    """Raised when a client-supplied push endpoint is not a known push service."""


def validate_push_endpoint(endpoint: str) -> str:
    """Return a stripped endpoint, or raise if it is not an allowlisted HTTPS push URL."""
    cleaned = endpoint.strip()
    parts = urlsplit(cleaned)
    if parts.scheme != "https":
        raise PushEndpointError("Push endpoint must use https")
    if parts.username or parts.password:
        raise PushEndpointError("Push endpoint must not include credentials")
    host = parts.hostname
    if not host:
        raise PushEndpointError("Push endpoint must include a host")
    if parts.port not in (None, 443):
        raise PushEndpointError("Push endpoint must use port 443")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise PushEndpointError("Push endpoint must not be an IP address")

    normalized_host = host.lower().rstrip(".")
    allowed = normalized_host in ALLOWED_PUSH_HOSTS or any(
        normalized_host.endswith(suffix) for suffix in ALLOWED_PUSH_HOST_SUFFIXES
    )
    if not allowed:
        raise PushEndpointError("Push endpoint host is not a known push service")
    return cleaned


def generate_vapid_keypair() -> tuple[str, str]:
    """Generate a URL-safe base64-encoded P-256 (public_key, private_key) pair for VAPID."""
    priv_key = ec.generate_private_key(ec.SECP256R1())
    raw_priv = priv_key.private_numbers().private_value.to_bytes(32, "big")
    raw_pub = priv_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    b64_priv = base64.urlsafe_b64encode(raw_priv).rstrip(b"=").decode("ascii")
    b64_pub = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode("ascii")
    return b64_pub, b64_priv


def format_turn_notification(
    *,
    game_slug: str,
    game_title: str,
    room_id: str,
    actor_name: str | None = None,
    events: list[dict[str, Any]] | None = None,
    reason: str = "action",
) -> dict[str, str]:
    """Build a concise notification payload when it becomes a player's turn."""
    title = f"{game_title} — It's your turn!"
    actor = actor_name or "Your opponent"
    body = f"{actor} finished their move in #{room_id}. Your turn!"

    if reason == "game_started":
        body = f"Game #{room_id} has started and you have the opening move!"
    elif reason == "player_left":
        body = f"Turn advanced to you in #{room_id}."
    elif events:
        first = events[0]
        ev_type = first.get("type")
        if ev_type == "word_played":
            word = first.get("word", "")
            pts = first.get("word_points", 0)
            body = f'{actor} played "{word}" ({pts} pts). Your move!'
        elif ev_type == "turn_passed":
            body = f"{actor} passed their turn. Your move!"
        elif ev_type == "line_drawn":
            body = f"{actor} drew a line in #{room_id}. Your turn!"

    return {
        "title": title,
        "body": body,
        "url": f"/{game_slug}/{room_id}",
        "tag": f"turn-{room_id}",
        "room_id": room_id,
        "game_slug": game_slug,
    }


class WebPushService:
    """Manages VAPID keys and dispatches Web Push notifications to subscribed players."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._public_key: str | None = None
        self._private_key: str | None = None
        self._claims_sub: str = os.getenv("VAPID_CLAIMS_SUB", DEFAULT_VAPID_CLAIMS_SUB)
        self._init_lock = asyncio.Lock()

    async def ensure_keys(self) -> tuple[str, str]:
        """Load VAPID keys from environment or database, generating once if missing."""
        if self._public_key and self._private_key:
            return self._public_key, self._private_key

        async with self._init_lock:
            if self._public_key and self._private_key:
                return self._public_key, self._private_key

            env_pub = os.getenv("VAPID_PUBLIC_KEY", "").strip()
            env_priv = os.getenv("VAPID_PRIVATE_KEY", "").strip()
            if env_pub and env_priv:
                self._public_key = env_pub
                self._private_key = env_priv
                return env_pub, env_priv

            stored = await self.db.get_app_setting(VAPID_SETTINGS_KEY)
            if (
                stored
                and isinstance(stored.get("public_key"), str)
                and isinstance(stored.get("private_key"), str)
                and stored["public_key"]
                and stored["private_key"]
            ):
                self._public_key = stored["public_key"]
                self._private_key = stored["private_key"]
                return self._public_key, self._private_key

            pub, priv = generate_vapid_keypair()
            await self.db.set_app_setting(
                VAPID_SETTINGS_KEY,
                {"public_key": pub, "private_key": priv},
            )
            self._public_key = pub
            self._private_key = priv
            logger.info("Generated and persisted new VAPID keypair in PostgreSQL.")
            return pub, priv

    async def get_public_key(self) -> str:
        pub, _ = await self.ensure_keys()
        return pub

    async def send_to_player(
        self,
        *,
        room_id: str,
        player_id: str,
        payload: dict[str, Any],
    ) -> int:
        """Send a Web Push notification to all active endpoints for a player in a room."""
        subscriptions = await self.db.get_push_subscriptions(room_id, player_id)
        if not subscriptions:
            return 0

        _, private_key = await self.ensure_keys()
        data_str = json.dumps(payload)
        sent_count = 0

        for sub in subscriptions:
            endpoint = str(sub["endpoint"])
            subscription_info = {
                "endpoint": endpoint,
                "keys": {
                    "p256dh": str(sub["p256dh"]),
                    "auth": str(sub["auth"]),
                },
            }
            try:
                await asyncio.to_thread(
                    webpush,
                    subscription_info=subscription_info,
                    data=data_str,
                    vapid_private_key=private_key,
                    vapid_claims={"sub": self._claims_sub},
                    ttl=PUSH_TTL_SECONDS,
                    headers={"Topic": f"turn-{room_id}"},
                )
                sent_count += 1
            except WebPushException as e:
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                if status_code in EXPIRED_PUSH_STATUS_CODES:
                    logger.info(
                        "Pruning expired push subscription for player %s in room %s: %s",
                        player_id,
                        room_id,
                        repr(e),
                    )
                    await self.db.delete_push_subscriptions(
                        room_id=room_id,
                        player_id=player_id,
                        endpoint=endpoint,
                    )
                else:
                    logger.warning(
                        "WebPush delivery failed for player %s in room %s: %s",
                        player_id,
                        room_id,
                        repr(e),
                    )
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning(
                    "Unexpected error sending WebPush for player %s in room %s: %s",
                    player_id,
                    room_id,
                    repr(e),
                )

        return sent_count
