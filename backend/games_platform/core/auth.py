"""User accounts: password hashing, sessions, single-use email tokens, Google linking."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from games_platform.core.db import Database
from games_platform.core.mail import MailError, send_email

logger = logging.getLogger(__name__)

SESSION_COOKIE = "games_session"
SESSION_TTL = timedelta(days=30)
AUTH_SECRET_KEY = "auth_secret"
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

TOKEN_TTLS = {
    "email_verification": timedelta(hours=48),
    "password_reset": timedelta(hours=1),
}
LINK_PATHS = {
    "email_verification": "/verify-email",
    "password_reset": "/reset-password",
}

_hasher = PasswordHasher()
# Verified against when the email is unknown, so login timing doesn't reveal accounts.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


class AuthError(Exception):
    pass


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def validate_password(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise AuthError(
            f"Password must be {MIN_PASSWORD_LENGTH}–{MAX_PASSWORD_LENGTH} characters long"
        )


def public_base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "http://localhost:5173").rstrip("/")


def cookie_secure() -> bool:
    return public_base_url().startswith("https://")


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["display_name"],
        "color": row.get("color") or "",
        "player_id": row["player_id"],
        "email_verified": row["email_verified_at"] is not None,
        "has_password": row["password_hash"] is not None,
        "mail_turn": bool(row.get("notify_mail_turn")),
        "mail_invite": bool(row.get("notify_mail_invite")),
    }


MAIL_KINDS = ("turn", "invite")


class AuthService:
    def __init__(self, database: Database) -> None:
        self.db = database
        self.secret: bytes = b""

    async def load_secret(self) -> None:
        """Signing key for OAuth flow cookies: `AUTH_SECRET`, else generated and kept in Postgres."""
        configured = os.getenv("AUTH_SECRET", "").strip()
        if configured:
            self.secret = configured.encode()
            return
        stored = await self.db.get_app_setting(AUTH_SECRET_KEY)
        if stored and stored.get("value"):
            self.secret = str(stored["value"]).encode()
            return
        generated = secrets.token_urlsafe(48)
        await self.db.set_app_setting(AUTH_SECRET_KEY, {"value": generated})
        self.secret = generated.encode()

    # --- users -------------------------------------------------------------

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM users WHERE email = %s", (email.strip().lower(),))
            return await cur.fetchone()

    async def player_id_has_account(self, player_id: str) -> bool:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT 1 FROM users WHERE player_id = %s", (player_id,))
            return await cur.fetchone() is not None

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return await cur.fetchone()

    async def _free_player_id(self, cur: Any, wanted: str | None) -> str:
        """Adopt the browser's anonymous player id (keeps its stats) unless it belongs to someone."""
        wanted = (wanted or "").strip()[:64]
        if wanted:
            await cur.execute("SELECT 1 FROM users WHERE player_id = %s", (wanted,))
            if await cur.fetchone() is None:
                return wanted
        return str(uuid.uuid4())

    async def register(
        self, *, email: str, password: str, name: str, player_id: str | None
    ) -> dict[str, Any]:
        validate_password(password)
        email = email.strip().lower()
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT password_hash FROM users WHERE email = %s", (email,))
            existing = await cur.fetchone()
            if existing is not None:
                if existing["password_hash"] is None:
                    raise AuthError("This email uses Google sign-in. Continue with Google instead.")
                raise AuthError("Email already registered")
            pid = await self._free_player_id(cur, player_id)
            await cur.execute(
                """
                INSERT INTO users (email, password_hash, display_name, player_id)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (email, hash_password(password), name.strip()[:32], pid),
            )
            row = await cur.fetchone()
            assert row is not None
            return row

    async def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        user = await self.get_user_by_email(email)
        ok = verify_password(password, user["password_hash"] if user else None)
        return user if user is not None and ok else None

    async def upsert_google_user(
        self, *, subject: str, email: str, name: str, player_id: str | None
    ) -> dict[str, Any]:
        async with self.db.connection() as conn, conn.cursor() as cur, conn.transaction():
            await cur.execute(
                """
                SELECT u.* FROM oauth_accounts o JOIN users u ON u.id = o.user_id
                WHERE o.provider = 'google' AND o.subject = %s
                """,
                (subject,),
            )
            linked = await cur.fetchone()
            if linked is not None:
                return linked
            await cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = await cur.fetchone()
            if user is None:
                pid = await self._free_player_id(cur, player_id)
                await cur.execute(
                    """
                    INSERT INTO users (email, display_name, player_id, email_verified_at)
                    VALUES (%s, %s, %s, NOW())
                    RETURNING *
                    """,
                    (email, name, pid),
                )
                row = await cur.fetchone()
            elif user["email_verified_at"] is None:
                # Whoever signed up with this address first never proved they own it, so
                # their password must not survive: drop it and trust the Google identity.
                await cur.execute(
                    """
                    UPDATE users SET email_verified_at = NOW(), password_hash = NULL
                    WHERE id = %s RETURNING *
                    """,
                    (user["id"],),
                )
                row = await cur.fetchone()
                await cur.execute("DELETE FROM auth_sessions WHERE user_id = %s", (user["id"],))
            else:
                row = user
            assert row is not None
            await cur.execute(
                "INSERT INTO oauth_accounts (provider, subject, user_id) VALUES ('google', %s, %s)",
                (subject, row["id"]),
            )
            return row

    async def update_profile(
        self, user_id: int, *, name: str | None = None, color: str | None = None
    ) -> dict[str, Any]:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE users SET
                    display_name = COALESCE(%s, display_name),
                    color = COALESCE(%s, color)
                WHERE id = %s RETURNING *
                """,
                (name.strip()[:32] if name is not None else None, color, user_id),
            )
            row = await cur.fetchone()
            assert row is not None
            return row

    async def update_mail_prefs(
        self, user_id: int, *, turn: bool | None = None, invite: bool | None = None
    ) -> dict[str, Any]:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE users SET
                    notify_mail_turn = COALESCE(%s, notify_mail_turn),
                    notify_mail_invite = COALESCE(%s, notify_mail_invite)
                WHERE id = %s RETURNING *
                """,
                (turn, invite, user_id),
            )
            row = await cur.fetchone()
            assert row is not None
            return row

    # --- unsubscribe links (no login needed) -------------------------------

    def _mail_signature(self, user_id: int, kind: str) -> str:
        digest = hmac.new(self.secret, f"unsubscribe:{user_id}:{kind}".encode(), hashlib.sha256)
        return digest.hexdigest()[:32]

    def unsubscribe_token(self, user_id: int, kind: str) -> str:
        """Token for turning off one kind of email ("turn" or "invite")."""
        return f"{user_id}.{kind}.{self._mail_signature(user_id, kind)}"

    async def unsubscribe(self, token: str) -> str | None:
        """Turn off the email kind the token is for. Returns that kind, or None if invalid."""
        try:
            raw_id, kind, signature = token.split(".")
            user_id = int(raw_id)
        except ValueError:
            return None
        if kind not in MAIL_KINDS or not hmac.compare_digest(
            signature, self._mail_signature(user_id, kind)
        ):
            return None
        column = "notify_mail_turn" if kind == "turn" else "notify_mail_invite"
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"UPDATE users SET {column} = FALSE WHERE id = %s", (user_id,))
        return kind

    async def update_name(self, user_id: int, name: str) -> dict[str, Any]:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET display_name = %s WHERE id = %s RETURNING *",
                (name.strip()[:32], user_id),
            )
            row = await cur.fetchone()
            assert row is not None
            return row

    async def change_password(
        self, user: dict[str, Any], current_password: str | None, new_password: str
    ) -> None:
        if user["password_hash"] is not None and not verify_password(
            current_password or "", user["password_hash"]
        ):
            raise AuthError("Current password is incorrect")
        validate_password(new_password)
        async with self.db.connection() as conn, conn.cursor() as cur, conn.transaction():
            await cur.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (hash_password(new_password), user["id"]),
            )
            await cur.execute("DELETE FROM auth_sessions WHERE user_id = %s", (user["id"],))

    async def delete_account(self, user: dict[str, Any], confirmation: str | None) -> None:
        if user["password_hash"] is not None:
            if not verify_password(confirmation or "", user["password_hash"]):
                raise AuthError("Password is incorrect")
        elif (confirmation or "").strip().lower() != user["email"]:
            raise AuthError("Type your email address to confirm")
        pid = user["player_id"]
        async with self.db.connection() as conn, conn.cursor() as cur, conn.transaction():
            await cur.execute("DELETE FROM rooms WHERE host_player_id = %s", (pid,))
            await cur.execute("DELETE FROM room_players WHERE player_id = %s", (pid,))
            await cur.execute("DELETE FROM push_subscriptions WHERE player_id = %s", (pid,))
            await cur.execute("DELETE FROM player_stats WHERE player_id = %s", (pid,))
            await cur.execute("DELETE FROM users WHERE id = %s", (user["id"],))

    # --- sessions ----------------------------------------------------------

    async def create_session(self, user_id: int) -> str:
        raw = new_token()
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO auth_sessions (token_hash, user_id, expires_at)
                VALUES (%s, %s, NOW() + %s)
                """,
                (hash_token(raw), user_id, SESSION_TTL),
            )
        return raw

    async def user_for_session(self, raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        digest = hash_token(raw)
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT u.* FROM auth_sessions s JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = %s AND s.expires_at > NOW()
                """,
                (digest,),
            )
            user = await cur.fetchone()
            if user is not None:
                # Sliding expiry, written at most hourly.
                await cur.execute(
                    """
                    UPDATE auth_sessions SET last_used_at = NOW(), expires_at = NOW() + %s
                    WHERE token_hash = %s AND last_used_at < NOW() - INTERVAL '1 hour'
                    """,
                    (SESSION_TTL, digest),
                )
            return user

    async def delete_session(self, raw: str | None) -> None:
        if not raw:
            return
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (hash_token(raw),))

    # --- email tokens ------------------------------------------------------

    async def create_email_token(self, purpose: str, user_id: int) -> str:
        raw = new_token()
        async with self.db.connection() as conn, conn.cursor() as cur, conn.transaction():
            await cur.execute(
                "DELETE FROM auth_email_tokens WHERE user_id = %s AND purpose = %s",
                (user_id, purpose),
            )
            await cur.execute(
                """
                INSERT INTO auth_email_tokens (token_hash, purpose, user_id, expires_at)
                VALUES (%s, %s, %s, NOW() + %s)
                """,
                (hash_token(raw), purpose, user_id, TOKEN_TTLS[purpose]),
            )
        return raw

    async def consume_email_token(self, purpose: str, raw: str) -> int:
        """Mark a token used and return its user id; raises `AuthError` if unusable."""
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE auth_email_tokens SET used_at = NOW()
                WHERE token_hash = %s AND purpose = %s AND used_at IS NULL AND expires_at > NOW()
                RETURNING user_id
                """,
                (hash_token(raw), purpose),
            )
            row = await cur.fetchone()
        if row is None:
            raise AuthError("This link is invalid or has expired")
        return int(row["user_id"])

    async def verify_email(self, raw: str) -> dict[str, Any]:
        user_id = await self.consume_email_token("email_verification", raw)
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE users SET email_verified_at = COALESCE(email_verified_at, NOW())
                WHERE id = %s RETURNING *
                """,
                (user_id,),
            )
            row = await cur.fetchone()
        if row is None:
            raise AuthError("This link is invalid or has expired")
        return row

    async def reset_password(self, raw: str, password: str) -> None:
        validate_password(password)
        user_id = await self.consume_email_token("password_reset", raw)
        async with self.db.connection() as conn, conn.cursor() as cur, conn.transaction():
            # Clicking the emailed link also proves ownership of the address.
            await cur.execute(
                """
                UPDATE users SET password_hash = %s,
                    email_verified_at = COALESCE(email_verified_at, NOW())
                WHERE id = %s
                """,
                (hash_password(password), user_id),
            )
            await cur.execute("DELETE FROM auth_sessions WHERE user_id = %s", (user_id,))

    async def send_token_email(self, purpose: str, user: dict[str, Any]) -> None:
        raw = await self.create_email_token(purpose, user["id"])
        link = f"{public_base_url()}{LINK_PATHS[purpose]}?token={raw}"
        if purpose == "email_verification":
            subject = "Confirm your email for games.jakob-r.de"
            intro = "Confirm your email address to finish setting up your account."
            expiry = "This link is valid for 48 hours."
        else:
            subject = "Reset your password for games.jakob-r.de"
            intro = "Use this link to choose a new password."
            expiry = "This link is valid for 1 hour and works once."
        body = (
            f"{intro}\n\n{link}\n\n{expiry}\n"
            "If you didn't request this, you can ignore this email.\n"
        )
        try:
            await send_email(to=user["email"], subject=subject, body=body)
        except MailError:
            # Don't fail the request (or leak whether the account exists); the user can retry.
            logger.error("Could not deliver %s email for user %s", purpose, user["id"])
