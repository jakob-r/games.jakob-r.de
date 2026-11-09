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


def test_push_subscription_for_account_needs_its_session(client: TestClient) -> None:
    acc = Accounts(client)
    alice = acc.register("alice", "Alice")
    acc.register("bob", "Bob")
    body = {
        "player_id": alice["player_id"],
        "endpoint": f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4().hex}",
        "keys": {"p256dh": "k", "auth": "a"},
    }
    assert acc.act_as(None).post("/api/notifications/subscribe", json=body).status_code == 403
    assert acc.act_as("bob").post("/api/notifications/subscribe", json=body).status_code == 403
    assert acc.act_as("alice").post("/api/notifications/subscribe", json=body).status_code == 200
    # Anonymous ids need no session.
    anon = {**body, "player_id": f"anon-{uuid.uuid4().hex[:8]}"}
    assert acc.act_as(None).post("/api/notifications/subscribe", json=anon).status_code == 200


def _befriend(acc: Accounts, a: str, b: str, room_id: str) -> None:
    acc.act_as(a).post(
        "/api/friends/requests",
        json={"room_id": room_id, "player_id": acc.users[b]["player_id"]},
    )
    acc.act_as(b).post(f"/api/friends/requests/{acc.users[a]['id']}/accept")


def test_invite_friend_to_room_with_push_and_inbox(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pushed: list[dict] = []

    def fake_webpush(*, subscription_info, data, **_kwargs):
        pushed.append({"endpoint": subscription_info["endpoint"], "data": data})

    monkeypatch.setattr("games_platform.core.push.webpush", fake_webpush)
    acc = Accounts(client)
    alice = acc.register("alice", "Alice")
    bob = acc.register("bob", "Bob")
    carol = acc.register("carol", "Carol")
    met = _room_with(client, alice["player_id"], bob["player_id"])
    _befriend(acc, "alice", "bob", met)

    bob_endpoint = f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4().hex}"
    acc.act_as("bob").post(
        "/api/notifications/subscribe",
        json={
            "player_id": bob["player_id"],
            "endpoint": bob_endpoint,
            "keys": {"p256dh": "k", "auth": "a"},
        },
    )

    room_id = _room_with(client, alice["player_id"])
    c = acc.act_as("alice")
    # Carol is no friend, Bob is: only Bob gets invited, once.
    res = c.post(
        "/api/friends/invites", json={"room_id": room_id, "user_ids": [bob["id"], carol["id"]]}
    )
    assert res.json() == {"invited": [bob["id"]]}
    assert c.post(
        "/api/friends/invites", json={"room_id": room_id, "user_ids": [bob["id"]]}
    ).json() == {"invited": []}
    assert c.get(f"/api/friends/rooms/{room_id}").json()["invited"] == [bob["id"]]
    assert client.portal is not None
    client.portal.call(client.app.state.friends.flush)
    assert [p["endpoint"] for p in pushed] == [bob_endpoint]
    assert "Alice invites you" in pushed[0]["data"] and f"/sudoku/{room_id}" in pushed[0]["data"]

    # Only members can invite.
    c = acc.act_as("carol")
    assert (
        c.post(
            "/api/friends/invites", json={"room_id": room_id, "user_ids": [bob["id"]]}
        ).status_code
        == 404
    )

    c = acc.act_as("bob")
    invites = c.get("/api/friends/inbox").json()["invites"]
    assert invites == [
        {
            "room_id": room_id,
            "game_slug": "sudoku",
            "status": "lobby",
            "from": {"user_id": alice["id"], "label": "Alice", "color": alice["color"]},
        }
    ]
    # Joining hides it; dismissing deletes it.
    with client.websocket_connect(
        f"/ws/sudoku/{room_id}?player_id={bob['player_id']}&name=Bob&color=%23dc2626"
    ) as ws:
        ws.receive_json()
    assert c.get("/api/friends/inbox").json()["invites"] == []
    assert c.delete(f"/api/friends/invites/{room_id}").status_code == 200

    # Removing the friendship drops pending invites between the two.
    other = _room_with(client, alice["player_id"])
    acc.act_as("alice").post(
        "/api/friends/invites", json={"room_id": other, "user_ids": [bob["id"]]}
    )
    assert len(acc.act_as("bob").get("/api/friends/inbox").json()["invites"]) == 1
    acc.act_as("bob").delete(f"/api/friends/{alice['id']}")
    assert acc.act_as("bob").get("/api/friends/inbox").json()["invites"] == []

    for rid in (met, room_id, other):
        client.delete(f"/api/rooms/{rid}?player_id={alice['player_id']}")


def test_friends_lobbies_only_lists_friends_rooms_in_lobby(client: TestClient) -> None:
    acc = Accounts(client)
    alice = acc.register("alice", "Alice")
    bob = acc.register("bob", "Bob")
    acc.register("carol", "Carol")
    met = _room_with(client, alice["player_id"], bob["player_id"])
    _befriend(acc, "alice", "bob", met)
    stranger_room = _room_with(client, acc.users["carol"]["player_id"])

    lobbies = acc.act_as("bob").get("/api/friends/lobbies").json()["lobbies"]
    assert lobbies == [
        {
            "room_id": met,
            "game_slug": "sudoku",
            "host": {"user_id": alice["id"], "label": "Alice", "color": alice["color"]},
            "players": 2,
            "joined": True,
        }
    ]
    assert "created_at" not in lobbies[0]

    # Once the game runs it is no longer listed.
    with client.websocket_connect(
        f"/ws/sudoku/{met}?player_id={alice['player_id']}&name=Alice&color=%232563eb"
    ) as ws:
        ws.receive_json()
        ws.send_json({"type": "start_game"})
        ws.receive_json()
    assert acc.act_as("bob").get("/api/friends/lobbies").json()["lobbies"] == []

    client.delete(f"/api/rooms/{met}?player_id={alice['player_id']}")
    client.delete(f"/api/rooms/{stranger_room}?player_id={acc.users['carol']['player_id']}")


def _verify(client: TestClient, user_id: int) -> None:
    async def run() -> None:
        async with client.app.state.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET email_verified_at = NOW() WHERE id = %s", (user_id,)
            )

    assert client.portal is not None
    client.portal.call(run)


@pytest.fixture
def mails(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    outbox: list[dict] = []

    async def fake_send(*, to: str, subject: str, body: str, headers=None) -> None:
        outbox.append({"to": to, "subject": subject, "body": body, "headers": headers or {}})

    monkeypatch.setattr("games_platform.core.notify_mail.send_email", fake_send)
    return outbox


def test_mail_prefs_and_unsubscribe_link(client: TestClient) -> None:
    acc = Accounts(client)
    alice = acc.register("alice", "Alice")
    assert alice["mail_turn"] is False and alice["mail_invite"] is False
    c = acc.act_as("alice")
    res = c.post("/api/auth/account/notifications", json={"mail_turn": True, "mail_invite": True})
    assert res.json()["mail_turn"] is True and res.json()["mail_invite"] is True

    token = client.app.state.auth.unsubscribe_token(alice["id"], "turn")
    assert acc.act_as(None).post(f"/api/mail/unsubscribe?token={token}").json() == {
        "status": "unsubscribed",
        "kind": "turn",
    }
    me = acc.act_as("alice").get("/api/auth/me").json()["user"]
    assert me["mail_turn"] is False and me["mail_invite"] is True

    forged = f"{alice['id']}.invite.{'0' * 32}"
    assert client.post(f"/api/mail/unsubscribe?token={forged}").status_code == 400
    assert client.post("/api/mail/unsubscribe?token=garbage").status_code == 400


def test_invite_mail_only_when_opted_in_and_once_a_day(
    client: TestClient, mails: list[dict]
) -> None:
    acc = Accounts(client)
    alice = acc.register("alice", "Alice")
    bob = acc.register("bob", "Bob")
    met = _room_with(client, alice["player_id"], bob["player_id"])
    _befriend(acc, "alice", "bob", met)
    friends_service = client.app.state.friends

    def invite_to_new_room() -> str:
        room_id = _room_with(client, alice["player_id"])
        acc.act_as("alice").post(
            "/api/friends/invites", json={"room_id": room_id, "user_ids": [bob["id"]]}
        )
        client.portal.call(friends_service.flush)
        return room_id

    first = invite_to_new_room()  # not opted in
    acc.act_as("bob").post("/api/auth/account/notifications", json={"mail_invite": True})
    second = invite_to_new_room()  # opted in, but not verified
    _verify(client, bob["id"])
    third = invite_to_new_room()
    fourth = invite_to_new_room()  # same inviter within a day
    assert len(mails) == 1
    assert mails[0]["subject"] == "Alice invites you to Multiplayer Sudoku"
    assert f"/sudoku/{third}" in mails[0]["body"] and "/unsubscribe?token=" in mails[0]["body"]
    assert mails[0]["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    for rid in (met, first, second, third, fourth):
        client.delete(f"/api/rooms/{rid}?player_id={alice['player_id']}")


def test_turn_mail_waits_and_is_sent_once(client: TestClient, mails: list[dict]) -> None:
    acc = Accounts(client)
    bob = acc.register("bob", "Bob")
    pid = bob["player_id"]
    room_id = _room_with(client, pid)
    db = client.app.state.db
    mailer = client.app.state.mailer
    call = client.portal.call

    async def make_due() -> None:
        async with db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE turn_mail_queue SET due_at = NOW() - INTERVAL '1 second' WHERE room_id = %s",
                (room_id,),
            )

    async def set_turn(player_id: str) -> None:
        await db.update_room(room_id, status="playing", state={"current_player_id": player_id})

    call(set_turn, pid)
    away = lambda _room, _player: False
    here = lambda _room, _player: True

    # Not opted in: nothing is queued.
    call(mailer.queue_turn, pid, room_id)
    call(make_due)
    assert call(mailer.send_due_turns, away) == 0

    acc.act_as("bob").post("/api/auth/account/notifications", json={"mail_turn": True})
    _verify(client, bob["id"])

    call(mailer.queue_turn, pid, room_id)
    assert call(mailer.send_due_turns, away) == 0  # not due yet
    call(make_due)
    assert call(mailer.send_due_turns, here) == 0  # connected: no mail, and it's used up
    assert call(mailer.send_due_turns, away) == 0

    call(mailer.queue_turn, pid, room_id)
    call(make_due)
    call(set_turn, "someone-else")
    assert call(mailer.send_due_turns, away) == 0  # turn moved on

    call(set_turn, pid)
    call(mailer.queue_turn, pid, room_id)
    call(make_due)
    assert call(mailer.send_due_turns, away) == 1
    assert call(mailer.send_due_turns, away) == 0
    assert mails[-1]["subject"] == "Your turn in Multiplayer Sudoku"
    assert f"/sudoku/{room_id}" in mails[-1]["body"]

    client.delete(f"/api/rooms/{room_id}?player_id={pid}")
