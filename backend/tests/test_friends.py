"""Friend requests from a shared room, accept/decline/remove and name numbering."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from games_platform.core.auth import SESSION_COOKIE
from games_platform.core.db import Database
from games_platform.core.friends import friend_labels
from games_platform.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    async def fake_send(*, to: str, subject: str, body: str) -> None:
        return None

    monkeypatch.setattr("games_platform.core.auth.send_email", fake_send)
    with TestClient(create_app(database=Database())) as c:
        yield c


class Accounts:
    """Registers users and switches the client's session cookie between them."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.sessions: dict[str, str] = {}
        self.users: dict[str, dict] = {}

    def register(self, key: str, name: str) -> dict:
        self.client.cookies.clear()
        email = f"{key}-{uuid.uuid4().hex[:8]}@example.com"
        res = self.client.post(
            "/api/auth/register",
            json={"email": email, "password": "hunter2hunter2", "name": name},
        )
        assert res.status_code == 200
        self.sessions[key] = res.cookies[SESSION_COOKIE]
        self.users[key] = res.json()
        return self.users[key]

    def act_as(self, key: str | None) -> TestClient:
        self.client.cookies.clear()
        if key is not None:
            self.client.cookies.set(SESSION_COOKIE, self.sessions[key])
        return self.client


def _room_with(client: TestClient, host_pid: str, *others: str) -> str:
    res = client.post(
        "/api/rooms",
        json={
            "game_slug": "sudoku",
            "host_player_id": host_pid,
            "host_name": "Host",
            "host_color": "#2563eb",
            "config": {},
        },
    )
    assert res.status_code == 200
    room_id = res.json()["room_id"]
    for pid in others:
        with client.websocket_connect(
            f"/ws/sudoku/{room_id}?player_id={pid}&name=P&color=%23dc2626"
        ) as ws:
            ws.receive_json()
    return room_id


def test_friend_request_accept_and_remove(client: TestClient) -> None:
    acc = Accounts(client)
    alice = acc.register("alice", "Alice")
    bob = acc.register("bob", "Bob")
    carol = acc.register("carol", "Carol")
    anon = f"anon-{uuid.uuid4().hex[:8]}"
    room_id = _room_with(client, alice["player_id"], bob["player_id"], anon)

    # Not signed in: nothing.
    assert acc.act_as(None).get(f"/api/friends/rooms/{room_id}").status_code == 401

    # Alice sees Bob (account) but not the anonymous player. Carol isn't in the room.
    statuses = acc.act_as("alice").get(f"/api/friends/rooms/{room_id}").json()["statuses"]
    assert statuses == {bob["player_id"]: "none"}
    assert acc.act_as("carol").get(f"/api/friends/rooms/{room_id}").json()["statuses"] == {}

    # Only co-players with an account can be asked.
    c = acc.act_as("alice")
    assert (
        c.post("/api/friends/requests", json={"room_id": room_id, "player_id": anon}).status_code
        == 404
    )
    carol_req = {"room_id": room_id, "player_id": carol["player_id"]}
    assert c.post("/api/friends/requests", json=carol_req).status_code == 404

    bob_req = {"room_id": room_id, "player_id": bob["player_id"]}
    assert c.post("/api/friends/requests", json=bob_req).json() == {"status": "outgoing"}
    assert c.get("/api/friends").json()["outgoing"][0]["name"] == "Bob"

    c = acc.act_as("bob")
    statuses = c.get(f"/api/friends/rooms/{room_id}").json()["statuses"]
    assert statuses == {alice["player_id"]: "incoming"}
    incoming = c.get("/api/friends").json()["incoming"]
    assert [p["name"] for p in incoming] == ["Alice"]
    assert "email" not in incoming[0] and "player_id" not in incoming[0]

    assert c.post(f"/api/friends/requests/{alice['id']}/accept").status_code == 200
    bob_view = c.get("/api/friends").json()
    assert [f["label"] for f in bob_view["friends"]] == ["Alice"]
    assert bob_view["incoming"] == []

    c = acc.act_as("alice")
    alice_view = c.get("/api/friends").json()
    assert [f["name"] for f in alice_view["friends"]] == ["Bob"]
    assert alice_view["outgoing"] == []
    assert c.get(f"/api/friends/rooms/{room_id}").json()["statuses"] == {bob["player_id"]: "friend"}

    # Either side can remove; it is gone for both.
    assert c.delete(f"/api/friends/{bob['id']}").status_code == 200
    assert acc.act_as("bob").get("/api/friends").json()["friends"] == []

    client.delete(f"/api/rooms/{room_id}?player_id={alice['player_id']}")


def test_declined_request_stays_pending_for_sender(client: TestClient) -> None:
    acc = Accounts(client)
    alice = acc.register("alice", "Alice")
    bob = acc.register("bob", "Bob")
    room_id = _room_with(client, alice["player_id"], bob["player_id"])

    req = {"room_id": room_id, "player_id": bob["player_id"]}
    acc.act_as("alice").post("/api/friends/requests", json=req)
    assert acc.act_as("bob").post(f"/api/friends/requests/{alice['id']}/decline").status_code == 200
    assert acc.act_as("bob").get("/api/friends").json()["incoming"] == []

    # Alice can't tell, and asking again changes nothing.
    c = acc.act_as("alice")
    assert c.post("/api/friends/requests", json=req).json() == {"status": "outgoing"}
    assert [p["name"] for p in c.get("/api/friends").json()["outgoing"]] == ["Bob"]

    # Bob changes his mind: adding Alice accepts her old request.
    c = acc.act_as("bob")
    assert c.get(f"/api/friends/rooms/{room_id}").json()["statuses"] == {alice["player_id"]: "none"}
    back = {"room_id": room_id, "player_id": alice["player_id"]}
    assert c.post("/api/friends/requests", json=back).json() == {"status": "friend"}
    assert [f["name"] for f in acc.act_as("alice").get("/api/friends").json()["friends"]] == ["Bob"]

    client.delete(f"/api/rooms/{room_id}?player_id={alice['player_id']}")


def test_deleting_account_removes_friendships(client: TestClient) -> None:
    acc = Accounts(client)
    alice = acc.register("alice", "Alice")
    bob = acc.register("bob", "Bob")
    room_id = _room_with(client, alice["player_id"], bob["player_id"])
    acc.act_as("alice").post(
        "/api/friends/requests", json={"room_id": room_id, "player_id": bob["player_id"]}
    )
    acc.act_as("bob").post(f"/api/friends/requests/{alice['id']}/accept")

    res = acc.act_as("bob").post(
        "/api/auth/account/delete", json={"confirmation": "hunter2hunter2"}
    )
    assert res.status_code == 204
    assert acc.act_as("alice").get("/api/friends").json()["friends"] == []

    client.delete(f"/api/rooms/{room_id}?player_id={alice['player_id']}")


def test_friend_labels_number_duplicates_by_when_added() -> None:
    friends = [{"name": "Anna"}, {"name": "Ben"}, {"name": "anna "}, {"name": "Jakob"}]
    assert friend_labels("Jakob", friends) == ["Anna", "Ben", "anna (2)", "Jakob (2)"]
    assert friend_labels("Ben", [{"name": ""}]) == ["Player"]
