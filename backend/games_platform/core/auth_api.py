"""REST routes for accounts (`/api/auth/*`)."""

import logging
import time
from collections import defaultdict, deque
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from games_platform.core import oauth
from games_platform.core.auth import (
    SESSION_COOKIE,
    SESSION_TTL,
    AuthError,
    AuthService,
    cookie_secure,
    public_base_url,
    public_user,
)

logger = logging.getLogger(__name__)


class RateLimiter:
    """In-memory sliding window. Keys are emails/routes, never IP addresses."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window: float = 60.0) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and hits[0] < now - window:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
        hits.append(now)
        if len(self._hits) > 10_000:
            self._hits = defaultdict(deque, {k: v for k, v in self._hits.items() if v})


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)
    name: str = Field(default="", max_length=64)
    player_id: str | None = Field(default=None, max_length=64)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class EmailBody(BaseModel):
    email: EmailStr


class TokenBody(BaseModel):
    token: str = Field(max_length=200)


class ResetBody(TokenBody):
    password: str = Field(max_length=256)


class NameBody(BaseModel):
    name: str = Field(max_length=64)


class ProfileBody(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class PasswordBody(BaseModel):
    current_password: str | None = Field(default=None, max_length=256)
    new_password: str = Field(max_length=256)


class DeleteBody(BaseModel):
    confirmation: str | None = Field(default=None, max_length=256)


def _set_session_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")


def create_auth_router(service: AuthService) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    limiter = RateLimiter()

    async def optional_user(
        raw: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any] | None:
        return await service.user_for_session(raw)

    async def require_user(
        user: Annotated[dict[str, Any] | None, Depends(optional_user)],
    ) -> dict[str, Any]:
        if user is None:
            raise HTTPException(status_code=401, detail="Not signed in")
        return user

    async def _login(response: Response, user: dict[str, Any]) -> dict[str, Any]:
        _set_session_cookie(response, await service.create_session(user["id"]))
        return public_user(user)

    @router.get("/providers")
    async def providers() -> dict[str, bool]:
        return {"google": oauth.google_enabled()}

    @router.get("/me")
    async def me(user: Annotated[dict[str, Any] | None, Depends(optional_user)]) -> dict[str, Any]:
        return {"user": public_user(user) if user else None}

    @router.post("/register")
    async def register(body: RegisterBody, response: Response) -> dict[str, Any]:
        limiter.check("register", 30)
        limiter.check(f"register:{body.email.lower()}", 5, 3600)
        try:
            user = await service.register(
                email=body.email, password=body.password, name=body.name, player_id=body.player_id
            )
        except AuthError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        await service.send_token_email("email_verification", user)
        return await _login(response, user)

    @router.post("/login")
    async def login(body: LoginBody, response: Response) -> dict[str, Any]:
        limiter.check("login", 120)
        limiter.check(f"login:{body.email.lower()}", 10, 300)
        user = await service.authenticate(body.email, body.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Wrong email or password")
        return await _login(response, user)

    @router.post("/logout", status_code=204)
    async def logout(
        response: Response, raw: str | None = Cookie(default=None, alias=SESSION_COOKIE)
    ) -> None:
        await service.delete_session(raw)
        _clear_session_cookie(response)

    @router.post("/verify-email")
    async def verify_email(body: TokenBody) -> dict[str, Any]:
        limiter.check("verify", 60)
        try:
            return public_user(await service.verify_email(body.token))
        except AuthError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/resend-verification")
    async def resend_verification(
        user: Annotated[dict[str, Any], Depends(require_user)],
    ) -> dict[str, str]:
        limiter.check(f"resend:{user['id']}", 3, 600)
        if user["email_verified_at"] is None:
            await service.send_token_email("email_verification", user)
        return {"message": "Verification email sent."}

    @router.post("/forgot-password")
    async def forgot_password(body: EmailBody) -> dict[str, str]:
        limiter.check("forgot", 60)
        limiter.check(f"forgot:{body.email.lower()}", 3, 3600)
        user = await service.get_user_by_email(body.email)
        if user is not None:
            await service.send_token_email("password_reset", user)
        return {"message": "If that email is registered, a reset link has been sent."}

    @router.post("/reset-password")
    async def reset_password(body: ResetBody) -> dict[str, str]:
        limiter.check("reset", 30)
        try:
            await service.reset_password(body.token, body.password)
        except AuthError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"message": "Password updated. You can sign in now."}

    # --- Google ------------------------------------------------------------

    @router.get("/oauth/google/start")
    async def google_start(next: str = "/", player_id: str | None = None) -> RedirectResponse:
        if not oauth.google_enabled():
            raise HTTPException(status_code=404, detail="Google sign-in is not configured")
        url, flow = oauth.start_flow(
            secret=service.secret,
            base_url=public_base_url(),
            next_path=next,
            player_id=player_id,
        )
        redirect = RedirectResponse(url, status_code=302)
        redirect.set_cookie(
            oauth.FLOW_COOKIE,
            flow,
            httponly=True,
            secure=cookie_secure(),
            samesite="lax",
            max_age=oauth.FLOW_TTL_SECONDS,
            path="/api/auth/oauth",
        )
        return redirect

    @router.get("/oauth/google/callback")
    async def google_callback(
        code: str | None = None,
        state: str | None = None,
        flow: str | None = Cookie(default=None, alias=oauth.FLOW_COOKIE),
    ) -> RedirectResponse:
        def failed() -> RedirectResponse:
            redirect = RedirectResponse(f"{public_base_url()}/login?error=google", status_code=302)
            redirect.delete_cookie(oauth.FLOW_COOKIE, path="/api/auth/oauth")
            return redirect

        if not oauth.google_enabled() or not code or not state:
            return failed()
        try:
            payload = oauth.read_flow(service.secret, flow)
            if payload.get("state") != state:
                raise oauth.OAuthError("State mismatch")
            identity = await oauth.exchange_code(
                code=code, verifier=str(payload["cv"]), base_url=public_base_url()
            )
            user = await service.upsert_google_user(
                subject=identity.subject,
                email=identity.email,
                name=identity.name,
                player_id=str(payload.get("pid") or "") or None,
            )
        except oauth.OAuthError as e:
            logger.warning("Google sign-in failed: %s", repr(e))
            return failed()
        redirect = RedirectResponse(
            f"{public_base_url()}{oauth.safe_next_path(str(payload.get('next')))}",
            status_code=302,
        )
        redirect.delete_cookie(oauth.FLOW_COOKIE, path="/api/auth/oauth")
        _set_session_cookie(redirect, await service.create_session(user["id"]))
        return redirect

    # --- account -----------------------------------------------------------

    @router.post("/account/name")
    async def change_name(
        body: NameBody, user: Annotated[dict[str, Any], Depends(require_user)]
    ) -> dict[str, Any]:
        return public_user(await service.update_name(user["id"], body.name))

    @router.post("/account/profile")
    async def change_profile(
        body: ProfileBody, user: Annotated[dict[str, Any], Depends(require_user)]
    ) -> dict[str, Any]:
        name = body.name if body.name and body.name.strip() else None
        color = body.color.lower() if body.color else None
        return public_user(await service.update_profile(user["id"], name=name, color=color))

    @router.post("/account/password")
    async def change_password(
        body: PasswordBody,
        response: Response,
        user: Annotated[dict[str, Any], Depends(require_user)],
    ) -> dict[str, str]:
        limiter.check(f"pw:{user['id']}", 10, 300)
        try:
            await service.change_password(user, body.current_password, body.new_password)
        except AuthError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        # All sessions were revoked; keep this browser signed in.
        _set_session_cookie(response, await service.create_session(user["id"]))
        return {"message": "Password updated."}

    @router.post("/account/delete", status_code=204)
    async def delete_account(
        body: DeleteBody,
        response: Response,
        user: Annotated[dict[str, Any], Depends(require_user)],
    ) -> None:
        limiter.check(f"delete:{user['id']}", 5, 300)
        try:
            await service.delete_account(user, body.confirmation)
        except AuthError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        _clear_session_cookie(response)

    return router
