"""End-to-end integration tests with PostgreSQL, FastAPI REST endpoints, and WebSockets."""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi.testclient import TestClient
from pywebpush import WebPushException

from games_platform.core.db import Database
from games_platform.main import create_app


def test_full_multiplayer_sudoku_room_lifecycle() -> None:
    test_db = Database()
    app = create_app(database=test_db)

    with TestClient(app) as client:
        # 1. Check health & games list
        res = client.get("/api/games")
        assert res.status_code == 200
        games = res.json()
        assert any(g["slug"] == "sudoku" for g in games)
        assert all(isinstance(g["play_count"], int) for g in games)

        # 2. Host creates a Sudoku room
        create_res = client.post(
            "/api/rooms",
            json={
                "game_slug": "sudoku",
                "host_player_id": "host_1",
                "host_name": "Alice",
                "host_color": "#2563eb",
                "config": {"difficulty": "easy", "scoring_enabled": True},
            },
        )
        assert create_res.status_code == 200
        room_data = create_res.json()
        room_id = room_data["room_id"]
        assert room_data["status"] == "lobby"

        # 3. Connect two players over WebSockets
        ws_url_1 = f"/ws/sudoku/{room_id}?player_id=host_1&name=Alice&color=%232563eb"
        ws_url_2 = f"/ws/sudoku/{room_id}?player_id=peer_2&name=Bob&color=%23dc2626"

        with client.websocket_connect(ws_url_1) as ws1, client.websocket_connect(ws_url_2) as ws2:
            initial_1 = ws1.receive_json()
            assert initial_1["type"] == "room_state"
            # Receive broadcast from peer_2 joining
            join_broadcast_1 = ws1.receive_json()
            initial_2 = ws2.receive_json()
            assert len(join_broadcast_1["players"]) == 2
            assert len(initial_2["players"]) == 2

            # Peer sets ready
            ws2.send_json({"type": "set_ready", "is_ready": True})
            s1 = ws1.receive_json()
            _ = ws2.receive_json()
            bob = next(p for p in s1["players"] if p["player_id"] == "peer_2")
            assert bob["is_ready"] is True

            # Host starts the game
            ws1.send_json({"type": "start_game"})
            playing_1 = ws1.receive_json()
            _ = ws2.receive_json()
            assert playing_1["status"] == "playing"
            assert playing_1["state"]["total_cells"] == 81

            # Peer adds a corner note to an empty cell
            cells = playing_1["state"]["cells"]
            empty_cells = [
                (r, c) for r in range(9) for c in range(9) if cells[r][c]["value"] is None
            ]
            empty_r, empty_c = empty_cells[0]
            ws2.send_json(
                {
                    "type": "game_action",
                    "action": {
                        "type": "toggle_note",
                        "row": empty_r,
                        "col": empty_c,
                        "digit": 7,
                    },
                }
            )
            note_state_1 = ws1.receive_json()
            _ = ws2.receive_json()
            assert note_state_1["state"]["notes"][empty_r][empty_c] == {"7": "peer_2"}

            # Verify multiplier becomes 1.1 after first right entry and applies 1.1x on second right entry
            room_row = client.app.state.db
            # Fetch solution from db to make two valid moves
            assert client.portal is not None
            db_room = client.portal.call(room_row.get_room, room_id)
            assert db_room is not None
            solution = db_room["state"]["solution"]

            r1, c1 = empty_cells[0]
            ws2.send_json(
                {
                    "type": "game_action",
                    "action": {
                        "type": "set_value",
                        "row": r1,
                        "col": c1,
                        "value": solution[r1][c1],
                    },
                }
            )
            scored_ev_1 = ws1.receive_json()
            _ = ws2.receive_json()
            assert scored_ev_1["type"] == "cell_scored"
            assert scored_ev_1["multiplier"] == 1.0
            state_after_1 = ws1.receive_json()
            _ = ws2.receive_json()
            bob_after_1 = next(p for p in state_after_1["players"] if p["player_id"] == "peer_2")
            assert bob_after_1["multiplier"] == 1.1

            r2, c2 = empty_cells[1]
            ws2.send_json(
                {
                    "type": "game_action",
                    "action": {
                        "type": "set_value",
                        "row": r2,
                        "col": c2,
                        "value": solution[r2][c2],
                    },
                }
            )
            scored_ev_2 = ws1.receive_json()
            _ = ws2.receive_json()
            assert scored_ev_2["type"] == "cell_scored"
            assert scored_ev_2["multiplier"] == 1.1
            assert scored_ev_2["points_delta"] == round(scored_ev_2["base_points"] * 1.1, 2)
            state_after_2 = ws1.receive_json()
            _ = ws2.receive_json()
            bob_after_2 = next(p for p in state_after_2["players"] if p["player_id"] == "peer_2")
            assert bob_after_2["multiplier"] == 1.21

            # Join a new player into the running game, do nothing, and disconnect -> auto-leaves the room
            ws_url_spectator = (
                f"/ws/sudoku/{room_id}?player_id=peer_idle&name=IdleSpectator&color=%239333ea"
            )
            with client.websocket_connect(ws_url_spectator) as ws_idle:
                joined_snap_1 = ws1.receive_json()
                _ = ws2.receive_json()
                joined_snap_idle = ws_idle.receive_json()
                assert any(p["player_id"] == "peer_idle" for p in joined_snap_1["players"])
                assert any(p["player_id"] == "peer_idle" for p in joined_snap_idle["players"])

            left_snap_1 = ws1.receive_json()
            _ = ws2.receive_json()
            assert all(p["player_id"] != "peer_idle" for p in left_snap_1["players"])

        # 4. Check recent rooms & stats endpoints
        recent_res = client.get("/api/players/host_1/recent")
        assert recent_res.status_code == 200
        recent_list = recent_res.json()
        assert any(r["room_id"] == room_id for r in recent_list)

        stats_res = client.get("/api/players/host_1/stats")
        assert stats_res.status_code == 200
        assert stats_res.json()["summary"]["rooms_joined"] >= 1

        # 5. Non-host cannot delete the room or remove other players; creator can remove other players; creator cannot leave the room
        forbidden_del = client.delete(f"/api/rooms/{room_id}?player_id=peer_2")
        assert forbidden_del.status_code == 403

        forbidden_host_leave = client.delete(f"/api/rooms/{room_id}/players/host_1")
        assert forbidden_host_leave.status_code == 403

        forbidden_peer_kick = client.delete(f"/api/rooms/{room_id}/players/host_1?actor_id=peer_2")
        assert forbidden_peer_kick.status_code == 403

        # Join a third player and have host remove them
        ws_url_3 = f"/ws/sudoku/{room_id}?player_id=peer_3&name=Charlie&color=%2316a34a"
        with client.websocket_connect(ws_url_3) as ws3:
            _ = ws3.receive_json()
            non_host_kick = client.delete(f"/api/rooms/{room_id}/players/peer_3?actor_id=peer_2")
            assert non_host_kick.status_code == 403

            host_kick = client.delete(f"/api/rooms/{room_id}/players/peer_3?actor_id=host_1")
            assert host_kick.status_code == 200
            assert host_kick.json() == {
                "status": "removed",
                "room_id": room_id,
                "player_id": "peer_3",
            }
            removed_msg = ws3.receive_json()
            assert removed_msg == {
                "type": "player_removed",
                "room_id": room_id,
                "player_id": "peer_3",
            }

        leave_res = client.delete(f"/api/rooms/{room_id}/players/peer_2")
        assert leave_res.status_code == 200
        assert leave_res.json() == {"status": "left", "room_id": room_id, "player_id": "peer_2"}
        room_after_leave = client.get(f"/api/rooms/{room_id}").json()
        assert [p["player_id"] for p in room_after_leave["players"]] == ["host_1"]

        # 6. Host permanently deletes the room
        ok_del = client.delete(f"/api/rooms/{room_id}?player_id=host_1")
        assert ok_del.status_code == 200
        assert ok_del.json() == {"status": "deleted", "room_id": room_id}

        # Room is gone from GET /api/rooms/{room_id} and recent rooms
        missing_res = client.get(f"/api/rooms/{room_id}")
        assert missing_res.status_code == 404

        recent_after = client.get("/api/players/host_1/recent").json()
        assert all(r["room_id"] != room_id for r in recent_after)


def test_room_expiration_cleanup() -> None:
    test_db = Database()
    app = create_app(database=test_db)

    with TestClient(app) as client:
        # Create 3 rooms:
        # r_no_moves_old: lobby/no moves, 3 days old -> should be deleted
        # r_with_moves_recent: playing with moves, 10 days old -> should NOT be deleted
        # r_with_moves_old: playing with moves, 370 days old -> should be deleted
        r1 = client.post(
            "/api/rooms",
            json={
                "game_slug": "sudoku",
                "host_player_id": "u1",
                "host_name": "A",
                "host_color": "#2563eb",
            },
        ).json()["room_id"]
        r2 = client.post(
            "/api/rooms",
            json={
                "game_slug": "sudoku",
                "host_player_id": "u1",
                "host_name": "A",
                "host_color": "#2563eb",
            },
        ).json()["room_id"]
        r3 = client.post(
            "/api/rooms",
            json={
                "game_slug": "sudoku",
                "host_player_id": "u1",
                "host_name": "A",
                "host_color": "#2563eb",
            },
        ).json()["room_id"]

        async def _backdate() -> list[str]:
            pool = test_db._require_pool()
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "UPDATE rooms SET updated_at = NOW() - INTERVAL '3 days' WHERE id = %s",
                    (r1,),
                )
                await cur.execute(
                    "UPDATE rooms SET status = 'playing', state = '{\"history_count\": 2}'::jsonb, updated_at = NOW() - INTERVAL '10 days' WHERE id = %s",
                    (r2,),
                )
                await cur.execute(
                    "UPDATE rooms SET status = 'playing', state = '{\"history_count\": 5}'::jsonb, updated_at = NOW() - INTERVAL '370 days' WHERE id = %s",
                    (r3,),
                )
                await cur.execute(
                    """
                    INSERT INTO player_stats (player_id, game_slug, games_played, updated_at)
                    VALUES ('stats_old', 'sudoku', 1, NOW() - INTERVAL '370 days'),
                           ('stats_recent', 'sudoku', 1, NOW() - INTERVAL '10 days')
                    ON CONFLICT (player_id, game_slug)
                    DO UPDATE SET games_played = 1, updated_at = EXCLUDED.updated_at
                    """
                )
            return await app.state.room_manager.cleanup_expired_rooms()

        assert client.portal is not None
        deleted = client.portal.call(_backdate)
        assert r1 in deleted
        assert r3 in deleted
        assert r2 not in deleted

        assert client.get(f"/api/rooms/{r1}").status_code == 404
        assert client.get(f"/api/rooms/{r2}").status_code == 200
        assert client.get(f"/api/rooms/{r3}").status_code == 404
        assert client.get("/api/players/stats_old/stats").json()["summary"]["games_completed"] == 0
        assert (
            client.get("/api/players/stats_recent/stats").json()["summary"]["games_completed"] == 1
        )
        client.delete(f"/api/rooms/{r2}?player_id=u1")

        async def _drop_stats() -> None:
            pool = test_db._require_pool()
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute("DELETE FROM player_stats WHERE player_id = 'stats_recent'")

        client.portal.call(_drop_stats)


def test_turn_notifications_subscription_and_dispatch(monkeypatch) -> None:
    # First game of a room opens with a random player; pin it to the host.
    monkeypatch.setattr("games_platform.core.room_manager.random.choice", lambda seq: seq[0])
    test_db = Database()
    app = create_app(database=test_db)
    dispatched: list[dict[str, object]] = []
    fail_with_401 = {"on": False}
    peer_endpoint = "https://fcm.googleapis.com/fcm/send/peer2"
    # Push subscriptions outlive rooms, so use fresh ids per run.
    peer = f"peer_{uuid.uuid4().hex[:8]}"
    account = f"account_{uuid.uuid4().hex[:8]}"

    def fake_webpush(
        *,
        subscription_info,
        data,
        vapid_private_key,
        vapid_claims,
        ttl=300,
        headers=None,
    ):
        if fail_with_401["on"]:
            response = type("Resp", (), {"status_code": 401, "text": "unauthorized"})()
            raise WebPushException("unauthorized", response=response)
        dispatched.append(
            {
                "subscription_info": subscription_info,
                "data": data,
                "vapid_private_key": vapid_private_key,
                "vapid_claims": vapid_claims,
                "ttl": ttl,
                "headers": headers,
            }
        )

    monkeypatch.setattr("games_platform.core.push.webpush", fake_webpush)

    with TestClient(app) as client:
        # 1. Fetch VAPID public key
        key_res = client.get("/api/notifications/vapid-public-key")
        assert key_res.status_code == 200
        pub_key = key_res.json()["public_key"]
        assert isinstance(pub_key, str) and len(pub_key) >= 80

        # 2. Create a Silbenstreit room
        room_res = client.post(
            "/api/rooms",
            json={
                "game_slug": "silbenstreit",
                "host_player_id": "host_1",
                "host_name": "Alice",
                "host_color": "#2563eb",
                "config": {"size": 5, "language": "de"},
            },
        )
        assert room_res.status_code == 200
        room_id = room_res.json()["room_id"]

        def subscribe(player_id: str, endpoint: str):
            return client.post(
                "/api/notifications/subscribe",
                json={
                    "player_id": player_id,
                    "endpoint": endpoint,
                    "keys": {
                        "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQ",
                        "auth": "tBHItJI5svbpez7KI4CCXg",
                    },
                },
            )

        def status(player_id: str) -> dict[str, object]:
            res = client.get(f"/api/notifications/status?player_id={player_id}")
            assert res.status_code == 200
            return res.json()

        # 3. Subscriptions are per player and device, not per room.
        assert status(peer)["subscribed"] is False

        ws_url_1 = f"/ws/silbenstreit/{room_id}?player_id=host_1&name=Alice&color=%232563eb"
        ws_url_2 = f"/ws/silbenstreit/{room_id}?player_id={peer}&name=Bob&color=%23dc2626"

        # Join both players; subscribing does not depend on room membership.
        with client.websocket_connect(ws_url_1) as ws1, client.websocket_connect(ws_url_2) as ws2:
            _ = ws1.receive_json()
            _ = ws1.receive_json()
            _ = ws2.receive_json()

        assert subscribe(peer, "http://127.0.0.1/push").status_code == 400
        assert subscribe(peer, "https://evil.example/push").status_code == 400

        assert subscribe(peer, peer_endpoint).status_code == 200
        for index in range(2, 6):
            extra = subscribe(peer, f"https://fcm.googleapis.com/fcm/send/peer2-{index}")
            assert extra.status_code == 200
        sixth = subscribe(peer, "https://updates.push.services.mozilla.com/wpush/v2/extra")
        assert sixth.status_code == 409
        assert subscribe(peer, peer_endpoint).status_code == 200

        for index in range(2, 6):
            endpoint = quote(f"https://fcm.googleapis.com/fcm/send/peer2-{index}", safe="")
            removed = client.delete(
                f"/api/notifications/subscribe?player_id={peer}&endpoint={endpoint}"
            )
            assert removed.status_code == 200
            assert removed.json()["deleted"] == 1

        assert status(peer) == {"player_id": peer, "subscribed": True, "count": 1}
        # Unsubscribing needs the device's endpoint.
        assert client.delete(f"/api/notifications/subscribe?player_id={peer}").status_code == 422

        # Signing in on that browser moves the device to the account's id, and back.
        assert subscribe(account, peer_endpoint).status_code == 200
        assert status(peer)["subscribed"] is False
        assert status(account)["count"] == 1
        assert subscribe(peer, peer_endpoint).status_code == 200
        assert status(account)["subscribed"] is False

        # 4. Start the game and have host_1 pass -> peer_2 gets one notification.
        with client.websocket_connect(ws_url_1) as ws1, client.websocket_connect(ws_url_2) as ws2:
            _ = ws1.receive_json()
            _ = ws1.receive_json()
            _ = ws2.receive_json()

            ws1.send_json({"type": "start_game"})
            _ = ws1.receive_json()
            _ = ws2.receive_json()

            ws1.send_json({"type": "game_action", "action": {"type": "pass_turn"}})
            _ = ws1.receive_json()  # turn_passed event
            _ = ws2.receive_json()
            _ = ws1.receive_json()  # room_state
            _ = ws2.receive_json()

            assert client.portal is not None
            client.portal.call(app.state.room_manager.flush_push_tasks)

        assert len(dispatched) == 1
        assert (
            dispatched[0]["subscription_info"]["endpoint"]  # type: ignore[index]
            == peer_endpoint
        )
        assert dispatched[0]["ttl"] == 300
        assert dispatched[0]["headers"] == {"Topic": f"turn-{room_id}"}  # type: ignore[index]
        assert "Alice passed their turn" in str(dispatched[0]["data"])
        assert f"/{room_id}" in str(dispatched[0]["data"])

        # 5. Unsubscribe peer_2 and verify status
        peer_q = quote(peer_endpoint, safe="")
        unsub_res = client.delete(
            f"/api/notifications/subscribe?player_id={peer}&endpoint={peer_q}"
        )
        assert unsub_res.status_code == 200
        assert unsub_res.json()["deleted"] == 1
        assert status(peer)["subscribed"] is False

        # 6. A 401 from the push service drops that endpoint.
        assert subscribe(peer, peer_endpoint).status_code == 200
        fail_with_401["on"] = True
        with client.websocket_connect(ws_url_1) as ws1, client.websocket_connect(ws_url_2) as ws2:
            _ = ws1.receive_json()
            _ = ws1.receive_json()
            _ = ws2.receive_json()

            # peer_2 still has the turn from the earlier pass, so hand it back, then return it.
            ws2.send_json({"type": "game_action", "action": {"type": "pass_turn"}})
            _ = ws1.receive_json()
            _ = ws2.receive_json()
            _ = ws1.receive_json()
            _ = ws2.receive_json()

            ws1.send_json({"type": "game_action", "action": {"type": "pass_turn"}})
            _ = ws1.receive_json()
            _ = ws2.receive_json()
            _ = ws1.receive_json()
            _ = ws2.receive_json()

            client.portal.call(app.state.room_manager.flush_push_tasks)

        assert status(peer)["subscribed"] is False
        assert len(dispatched) == 1

        client.delete(f"/api/rooms/{room_id}?player_id=host_1")


def test_per_room_push_subscriptions_migrate_to_one_per_device() -> None:
    test_db = Database()
    app = create_app(database=test_db)
    old_endpoint = "https://fcm.googleapis.com/fcm/send/migrate-old"
    new_endpoint = "https://fcm.googleapis.com/fcm/send/migrate-new"

    async def setup_legacy_table() -> None:
        async with test_db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DROP TABLE push_subscriptions")
            await cur.execute(
                """
                CREATE TABLE push_subscriptions (
                    id BIGSERIAL PRIMARY KEY,
                    room_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (room_id, player_id, endpoint)
                )
                """
            )
            await cur.execute(
                "CREATE INDEX idx_push_subscriptions_room_player"
                " ON push_subscriptions(room_id, player_id)"
            )
            await cur.execute(
                """
                INSERT INTO push_subscriptions (room_id, player_id, endpoint, p256dh, auth, updated_at)
                VALUES ('r1', 'mig_anon', %s, 'k', 'a', NOW() - INTERVAL '2 days'),
                       ('r2', 'mig_anon', %s, 'k', 'a', NOW() - INTERVAL '1 day'),
                       ('r3', 'mig_account', %s, 'k2', 'a2', NOW()),
                       ('r1', 'mig_anon', %s, 'k', 'a', NOW())
                """,
                (old_endpoint, old_endpoint, old_endpoint, new_endpoint),
            )

    with TestClient(app) as client:
        assert client.portal is not None
        client.portal.call(setup_legacy_table)
        client.portal.call(test_db.init_schema)

        account = client.portal.call(test_db.get_push_subscriptions, "mig_account")
        anon = client.portal.call(test_db.get_push_subscriptions, "mig_anon")
        # Each device is kept once, for the player who used it last.
        assert [(s["endpoint"], s["p256dh"]) for s in account] == [(old_endpoint, "k2")]
        assert [s["endpoint"] for s in anon] == [new_endpoint]

        for player_id, endpoint in (("mig_account", old_endpoint), ("mig_anon", new_endpoint)):
            client.portal.call(
                lambda p=player_id, e=endpoint: test_db.delete_push_subscription(
                    player_id=p, endpoint=e
                )
            )


def test_player_stats_split_best_score_single_and_multi() -> None:
    test_db = Database()
    app = create_app(database=test_db)

    with TestClient(app) as client:
        rooms: list[str] = []
        for host in ("split_a", "split_a", "split_a"):
            res = client.post(
                "/api/rooms",
                json={
                    "game_slug": "sudoku",
                    "host_player_id": host,
                    "host_name": "A",
                    "host_color": "#2563eb",
                    "config": {"difficulty": "easy"},
                },
            )
            rooms.append(res.json()["room_id"])
        solo_hi, solo_lo, multi = rooms

        async def _finish() -> None:
            pool = test_db._require_pool()
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM player_stats WHERE player_id IN ('split_a', 'split_b')"
                )
                await cur.execute(
                    """
                    INSERT INTO room_players (room_id, player_id, name, color, score)
                    VALUES (%s, 'split_b', 'B', '#dc2626', 99)
                    """,
                    (multi,),
                )
                for room_id, score in ((solo_hi, 40), (solo_lo, 10), (multi, 25)):
                    await cur.execute(
                        "UPDATE room_players SET score = %s WHERE room_id = %s AND player_id = 'split_a'",
                        (score, room_id),
                    )
                    await test_db.record_game_finished(room_id, "sudoku")
                    if room_id == multi:
                        # split_a (25) lost to split_b (99) and opens the next game.
                        assert await test_db.get_next_starter_id(room_id) == "split_a"
                    await cur.execute("DELETE FROM rooms WHERE id = %s", (room_id,))

        assert client.portal is not None
        before = client.get("/api/players/split_a/stats").json()["server"]
        client.portal.call(_finish)

        data = client.get("/api/players/split_a/stats").json()
        assert data["summary"]["games_completed"] == 3
        (sudoku,) = data["by_game"]
        assert sudoku["games_played"] == 3
        assert sudoku["best_score_single"] == 40
        assert sudoku["best_score_multi"] == 25
        # Rooms were deleted after finishing, yet the running totals still went up.
        assert data["server"]["rounds_played"] == before["rounds_played"] + 3
        assert data["server"]["points_scored"] == before["points_scored"] + 40 + 10 + 25 + 99

        b = client.get("/api/players/split_b/stats").json()["by_game"][0]
        assert b["best_score_single"] is None
        assert b["best_score_multi"] == 99

        async def _cleanup() -> None:
            pool = test_db._require_pool()
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM player_stats WHERE player_id IN ('split_a', 'split_b')"
                )

        client.portal.call(_cleanup)


def test_websocket_to_unknown_room_closes_with_4004() -> None:
    import pytest
    from starlette.websockets import WebSocketDisconnect

    from games_platform.core.db import Database
    from games_platform.main import create_app

    with TestClient(create_app(database=Database())) as client:
        # Accepted, then closed, so browsers see 4004 instead of 1006.
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            client.websocket_connect("/ws/silbenstreit/nosuchroom?player_id=p") as ws,
        ):
            ws.receive_json()
        assert exc.value.code == 4004
