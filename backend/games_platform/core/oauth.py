"""Google sign-in (OpenID Connect authorization-code flow with PKCE)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
FLOW_COOKIE = "games_oauth"
FLOW_TTL_SECONDS = 600


class OAuthError(Exception):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    name: str


def google_enabled() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def callback_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/auth/oauth/google/callback"


def safe_next_path(path: str | None) -> str:
    """Only allow same-site relative redirects after login."""
    value = (path or "").strip() or "/"
    if not value.startswith("/") or value.startswith("//") or "\\" in value or "://" in value:
        return "/"
    return value


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_flow(secret: bytes, payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_flow(secret: bytes, cookie: str | None) -> dict:
    if not cookie or "." not in cookie:
        raise OAuthError("Missing sign-in state")
    body, sig = cookie.rsplit(".", 1)
    expected = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise OAuthError("Invalid sign-in state")
    try:
        payload = json.loads(_unb64(body))
    except ValueError as e:
        raise OAuthError("Invalid sign-in state") from e
    if not isinstance(payload, dict) or float(payload.get("exp", 0)) < time.time():
        raise OAuthError("Sign-in expired")
    return payload


def start_flow(*, secret: bytes, base_url: str, next_path: str, player_id: str | None):
    """Return `(authorize_url, signed_cookie_value)`; the cookie binds the flow to this browser."""
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    cookie = sign_flow(
        secret,
        {
            "state": state,
            "cv": verifier,
            "next": safe_next_path(next_path),
            "pid": player_id or "",
            "exp": time.time() + FLOW_TTL_SECONDS,
        },
    )
    query = urlencode(
        {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "redirect_uri": callback_url(base_url),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    return f"{GOOGLE_AUTH_URL}?{query}", cookie


async def exchange_code(*, code: str, verifier: str, base_url: str) -> GoogleIdentity:
    """Trade the code for an ID token. It arrives straight from Google over TLS, so its
    signature need not be checked; issuer, audience and expiry still are."""
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                    "redirect_uri": callback_url(base_url),
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
            )
            response.raise_for_status()
            token = response.json()
    except (httpx.HTTPError, ValueError) as e:
        raise OAuthError(f"Token exchange failed: {e!r}") from e
    id_token = token.get("id_token") if isinstance(token, dict) else None
    if not isinstance(id_token, str) or id_token.count(".") != 2:
        raise OAuthError("Missing id_token")
    try:
        claims = json.loads(_unb64(id_token.split(".")[1]))
    except ValueError as e:
        raise OAuthError("Invalid id_token") from e
    if not isinstance(claims, dict):
        raise OAuthError("Invalid id_token")
    if claims.get("aud") != client_id or claims.get("iss") not in GOOGLE_ISSUERS:
        raise OAuthError("Invalid id_token audience or issuer")
    if float(claims.get("exp", 0)) < time.time():
        raise OAuthError("Expired id_token")
    subject, email = claims.get("sub"), claims.get("email")
    if not isinstance(subject, str) or not isinstance(email, str) or not email:
        raise OAuthError("Missing account details")
    if claims.get("email_verified") not in (True, "true"):
        raise OAuthError("Email not verified by Google")
    name = claims.get("name")
    return GoogleIdentity(
        subject=subject,
        email=email.strip().lower(),
        name=name.strip()[:32] if isinstance(name, str) else "",
    )
