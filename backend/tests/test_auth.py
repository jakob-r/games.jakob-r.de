"""Account sign-up, login, email tokens and account management over the REST API."""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi.testclient import TestClient

from games_platform.core import mail, oauth
from games_platform.core.db import Database
from games_platform.main import create_app


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    outbox: list[dict[str, str]] = []

    async def fake_send(*, to: str, subject: str, body: str) -> None:
        outbox.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr("games_platform.core.auth.send_email", fake_send)
    return outbox


@pytest.fixture
def client():
    with TestClient(create_app(database=Database())) as c:
        yield c


def _email() -> str:
    return f"user-{uuid.uuid4().hex[:8]}@example.com"


def _token(outbox: list[dict[str, str]]) -> str:
    match = re.search(r"token=([\w-]+)", outbox[-1]["body"])
    assert match
    return match.group(1)


def test_register_login_logout_and_verify(client: TestClient, sent: list[dict[str, str]]) -> None:
    email = _email()
    res = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "hunter2hunter2",
            "name": "Ada",
            "player_id": "pid-" + email,
        },
    )
    assert res.status_code == 200
    user = res.json()
    assert user["player_id"] == "pid-" + email
    assert user["email_verified"] is False

    assert client.get("/api/auth/me").json()["user"]["email"] == email
    assert sent[-1]["to"] == email

    verified = client.post("/api/auth/verify-email", json={"token": _token(sent)})
    assert verified.json()["email_verified"] is True
    # Tokens are single use.
    assert client.post("/api/auth/verify-email", json={"token": _token(sent)}).status_code == 400

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").json()["user"] is None

    assert (
        client.post(
            "/api/auth/login", json={"email": email, "password": "wrong-password"}
        ).status_code
        == 401
    )
    ok = client.post("/api/auth/login", json={"email": email.upper(), "password": "hunter2hunter2"})
    assert ok.status_code == 200


def test_duplicate_and_weak_password(client: TestClient, sent: list[dict[str, str]]) -> None:
    email = _email()
    assert (
        client.post("/api/auth/register", json={"email": email, "password": "short"}).status_code
        == 400
    )
    body = {"email": email, "password": "long-enough-pw"}
    assert client.post("/api/auth/register", json=body).status_code == 200
    assert client.post("/api/auth/register", json=body).status_code == 400


def test_password_reset_revokes_sessions(client: TestClient, sent: list[dict[str, str]]) -> None:
    email = _email()
    client.post("/api/auth/register", json={"email": email, "password": "old-password-1"})
    unknown = client.post("/api/auth/forgot-password", json={"email": _email()})
    assert unknown.status_code == 200  # no enumeration
    assert client.post("/api/auth/forgot-password", json={"email": email}).status_code == 200
    token = _token(sent)
    res = client.post(
        "/api/auth/reset-password", json={"token": token, "password": "new-password-2"}
    )
    assert res.status_code == 200
    assert client.get("/api/auth/me").json()["user"] is None
    assert (
        client.post(
            "/api/auth/reset-password", json={"token": token, "password": "x" * 10}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": email, "password": "new-password-2"}
        ).status_code
        == 200
    )


def test_change_password_and_delete_account(client: TestClient, sent: list[dict[str, str]]) -> None:
    email = _email()
    client.post("/api/auth/register", json={"email": email, "password": "first-password"})
    bad = client.post(
        "/api/auth/account/password",
        json={"current_password": "nope", "new_password": "second-password"},
    )
    assert bad.status_code == 400
    good = client.post(
        "/api/auth/account/password",
        json={"current_password": "first-password", "new_password": "second-password"},
    )
    assert good.status_code == 200
    assert client.get("/api/auth/me").json()["user"]["email"] == email  # still signed in

    assert client.post("/api/auth/account/delete", json={"confirmation": "bad"}).status_code == 400
    assert (
        client.post(
            "/api/auth/account/delete", json={"confirmation": "second-password"}
        ).status_code
        == 204
    )
    assert client.get("/api/auth/me").json()["user"] is None
    assert (
        client.post(
            "/api/auth/login", json={"email": email, "password": "second-password"}
        ).status_code
        == 401
    )


def test_requires_login(client: TestClient) -> None:
    assert client.post("/api/auth/account/name", json={"name": "x"}).status_code == 401


def test_google_disabled_without_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert client.get("/api/auth/providers").json() == {"google": False}
    assert client.get("/api/auth/oauth/google/start", follow_redirects=False).status_code == 404


def test_google_flow_links_and_creates_accounts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, sent: list[dict[str, str]]
) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    email = _email()
    identity = oauth.GoogleIdentity(subject="sub-" + email, email=email, name="Grace")

    async def fake_exchange(**_: str) -> oauth.GoogleIdentity:
        return identity

    monkeypatch.setattr(oauth, "exchange_code", fake_exchange)

    # Someone pre-registers the address with a password but never verifies it.
    client.post("/api/auth/register", json={"email": email, "password": "attacker-pw-1"})
    client.post("/api/auth/logout")

    start = client.get("/api/auth/oauth/google/start?next=/account", follow_redirects=False)
    assert start.status_code == 302
    state = re.search(r"state=([\w-]+)", start.headers["location"]).group(1)

    bad = client.get("/api/auth/oauth/google/callback?code=c&state=wrong", follow_redirects=False)
    assert bad.headers["location"].endswith("/login?error=google")

    start = client.get("/api/auth/oauth/google/start?next=/account", follow_redirects=False)
    state = re.search(r"state=([\w-]+)", start.headers["location"]).group(1)
    done = client.get(
        f"/api/auth/oauth/google/callback?code=c&state={state}", follow_redirects=False
    )
    assert done.status_code == 302
    assert done.headers["location"].endswith("/account")
    me = client.get("/api/auth/me").json()["user"]
    assert me["email"] == email and me["email_verified"] is True
    # The unverified password was dropped, so the pre-registrant can't log in.
    assert me["has_password"] is False
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/login", json={"email": email, "password": "attacker-pw-1"}
        ).status_code
        == 401
    )


def test_safe_next_path() -> None:
    assert oauth.safe_next_path("/account") == "/account"
    for bad in ("//evil.com", "https://evil.com", "evil", "/\\evil.com", ""):
        assert oauth.safe_next_path(bad) == "/"


def test_mail_console_backend_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    import asyncio

    asyncio.run(mail.send_email(to="a@example.com", subject="s", body="b"))


def test_token_transport_for_native_clients(client: TestClient, sent: list[dict[str, str]]) -> None:
    """Native shells get the session token in the body and authenticate with a bearer header."""
    email = _email()
    native = {"X-Session-Transport": "token"}
    res = client.post(
        "/api/auth/register",
        json={"email": email, "password": "hunter2hunter2", "name": "Nat", "player_id": None},
        headers=native,
    )
    assert res.status_code == 200
    token = res.json()["session_token"]
    assert "games_session" not in res.cookies
    client.cookies.clear()

    bearer = {**native, "Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me").json()["user"] is None
    assert client.get("/api/auth/me", headers=bearer).json()["user"]["email"] == email

    # Password change revokes all sessions and hands out a fresh token.
    changed = client.post(
        "/api/auth/account/password",
        json={"current_password": "hunter2hunter2", "new_password": "correct-horse-battery"},
        headers=bearer,
    )
    assert changed.status_code == 200
    new_token = changed.json()["session_token"]
    assert client.get("/api/auth/me", headers=bearer).json()["user"] is None
    bearer = {**native, "Authorization": f"Bearer {new_token}"}
    assert client.get("/api/auth/me", headers=bearer).json()["user"]["email"] == email

    assert client.post("/api/auth/logout", headers=bearer).status_code == 204
    assert client.get("/api/auth/me", headers=bearer).json()["user"] is None

    # Login in token mode; browsers (no header) still get the cookie and no token.
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "correct-horse-battery"},
        headers=native,
    )
    assert login.json()["session_token"]
    client.cookies.clear()
    browser = client.post(
        "/api/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    assert "session_token" not in browser.json()
    assert client.get("/api/auth/me").json()["user"]["email"] == email
