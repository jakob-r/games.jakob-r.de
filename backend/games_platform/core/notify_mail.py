"""Opt-in notification emails: "a friend invites you" and "it's your turn"."""

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from games_platform.core.auth import AuthService, public_base_url
from games_platform.core.db import Database
from games_platform.core.mail import MailError, send_email

logger = logging.getLogger(__name__)

TURN_MAIL_DELAY = timedelta(minutes=15)
INVITE_MAIL_GAP = timedelta(hours=24)


class NotificationMailer:
    def __init__(
        self,
        database: Database,
        auth: AuthService,
        *,
        game_title: Callable[[str], str] = lambda slug: slug,
    ) -> None:
        self.db = database
        self.auth = auth
        self.game_title = game_title

    def _unsubscribe(self, user_id: int, kind: str) -> tuple[str, dict[str, str]]:
        token = quote(self.auth.unsubscribe_token(user_id, kind))
        base = public_base_url()
        page = f"{base}/unsubscribe?token={token}"
        one_click = f"{base}/api/mail/unsubscribe?token={token}"
        headers = {
            "List-Unsubscribe": f"<{one_click}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
        return page, headers

    async def _send(self, user: dict[str, Any], kind: str, subject: str, lines: list[str]) -> bool:
        page, headers = self._unsubscribe(int(user["id"]), kind)
        what = "invite" if kind == "invite" else "turn"
        body = "\n".join(
            [
                *lines,
                "",
                "--",
                f"You get this because you turned on {what} emails on games.jakob-r.de.",
                f"Turn them off: {page}",
            ]
        )
        try:
            await send_email(to=user["email"], subject=subject, body=body, headers=headers)
        except MailError:
            return False
        return True

    # --- invites -------------------------------------------------------------

    async def send_invite(
        self, *, to_user_id: int, from_user_id: int, inviter: str, game_slug: str, room_id: str
    ) -> bool:
        """Mail an invite if the friend opted in; at most one per inviter per day."""
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM users
                WHERE id = %s AND notify_mail_invite AND email_verified_at IS NOT NULL
                """,
                (to_user_id,),
            )
            user = await cur.fetchone()
            if user is None:
                return False
            await cur.execute(
                """
                SELECT 1 FROM room_invites
                WHERE from_user_id = %s AND to_user_id = %s AND mailed_at > NOW() - %s
                """,
                (from_user_id, to_user_id, INVITE_MAIL_GAP),
            )
            if await cur.fetchone() is not None:
                return False
            await cur.execute(
                """
                UPDATE room_invites SET mailed_at = NOW()
                WHERE room_id = %s AND to_user_id = %s
                """,
                (room_id, to_user_id),
            )
        title = self.game_title(game_slug)
        name = str(user["display_name"]).strip()
        return await self._send(
            user,
            "invite",
            f"{inviter} invites you to {title}",
            [
                f"Hi {name}," if name else "Hi,",
                "",
                f"{inviter} invites you to play {title}:",
                f"{public_base_url()}/{game_slug}/{room_id}",
            ],
        )

    # --- turns ---------------------------------------------------------------

    async def queue_turn(self, player_id: str, room_id: str) -> None:
        """Remember a turn; mailed later if it's still the player's turn and they're away."""
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO turn_mail_queue (player_id, room_id, due_at)
                SELECT %(pid)s, %(room)s, NOW() + %(delay)s
                WHERE EXISTS (
                    SELECT 1 FROM users
                    WHERE player_id = %(pid)s AND notify_mail_turn
                      AND email_verified_at IS NOT NULL
                )
                ON CONFLICT (player_id, room_id) DO UPDATE SET due_at = EXCLUDED.due_at
                """,
                {"pid": player_id, "room": room_id, "delay": TURN_MAIL_DELAY},
            )

    async def send_due_turns(self, is_connected: Callable[[str, str], bool]) -> int:
        """Send queued turn mails that are due. Each queued turn is mailed at most once."""
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM turn_mail_queue WHERE due_at <= NOW()
                RETURNING player_id, room_id
                """
            )
            due = await cur.fetchall()
        sent = 0
        for item in due:
            player_id, room_id = str(item["player_id"]), str(item["room_id"])
            room = await self.db.get_room(room_id)
            if room is None or room["status"] != "playing":
                continue
            state = room.get("state") or {}
            if not isinstance(state, dict) or state.get("current_player_id") != player_id:
                continue
            if is_connected(room_id, player_id):
                continue
            async with self.db.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT * FROM users
                    WHERE player_id = %s AND notify_mail_turn AND email_verified_at IS NOT NULL
                    """,
                    (player_id,),
                )
                user = await cur.fetchone()
            if user is None:
                continue
            slug = str(room["game_slug"])
            title = self.game_title(slug)
            if await self._send(
                user,
                "turn",
                f"Your turn in {title}",
                [
                    f"It's your turn in {title} (room #{room_id}):",
                    f"{public_base_url()}/{slug}/{room_id}",
                ],
            ):
                sent += 1
        return sent
