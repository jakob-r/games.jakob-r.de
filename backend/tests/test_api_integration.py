"""End-to-end integration tests with PostgreSQL, FastAPI REST endpoints, and WebSockets."""

from __future__ import annotations

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
                (r, c)
                for r in range(9)
                for c in range(9)
                if cells[r][c]["value"] is None
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
            ws_url_spectator = f"/ws/sudoku/{room_id}?player_id=peer_idle&name=IdleSpectator&color=%239333ea"
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

        forbidden_peer_kick = client.delete(
            f"/api/rooms/{room_id}/players/host_1?actor_id=peer_2"
        )
        assert forbidden_peer_kick.status_code == 403

        # Join a third player and have host remove them
        ws_url_3 = f"/ws/sudoku/{room_id}?player_id=peer_3&name=Charlie&color=%2316a34a"
        with client.websocket_connect(ws_url_3) as ws3:
            _ = ws3.receive_json()
            non_host_kick = client.delete(
                f"/api/rooms/{room_id}/players/peer_3?actor_id=peer_2"
            )
            assert non_host_kick.status_code == 403

            host_kick = client.delete(
                f"/api/rooms/{room_id}/players/peer_3?actor_id=host_1"
            )
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
            json={"game_slug": "sudoku", "host_player_id": "u1", "host_name": "A", "host_color": "#2563eb"},
        ).json()["room_id"]
        r2 = client.post(
            "/api/rooms",
            json={"game_slug": "sudoku", "host_player_id": "u1", "host_name": "A", "host_color": "#2563eb"},
        ).json()["room_id"]
        r3 = client.post(
            "/api/rooms",
            json={"game_slug": "sudoku", "host_player_id": "u1", "host_name": "A", "host_color": "#2563eb"},
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
            return await app.state.room_manager.cleanup_expired_rooms()

        assert client.portal is not None
        deleted = client.portal.call(_backdate)
        assert r1 in deleted
        assert r3 in deleted
        assert r2 not in deleted

        assert client.get(f"/api/rooms/{r1}").status_code == 404
        assert client.get(f"/api/rooms/{r2}").status_code == 200
        assert client.get(f"/api/rooms/{r3}").status_code == 404
        client.delete(f"/api/rooms/{r2}?player_id=u1")


def test_turn_notifications_subscription_and_dispatch(monkeypatch) -> None:
    test_db = Database()
    app = create_app(database=test_db)
    dispatched: list[dict[str, object]] = []
    fail_with_401 = {"on": False}
    peer_endpoint = "https://fcm.googleapis.com/fcm/send/peer2"

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
                f"/api/rooms/{room_id}/notifications/subscribe",
                json={
                    "player_id": player_id,
                    "endpoint": endpoint,
                    "keys": {
                        "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQ",
                        "auth": "tBHItJI5svbpez7KI4CCXg",
                    },
                },
            )

        # 3. A player who has not joined cannot subscribe, even with a valid endpoint.
        stranger = subscribe("peer_2", peer_endpoint)
        assert stranger.status_code == 403

        status_before = client.get(
            f"/api/rooms/{room_id}/notifications/status?player_id=peer_2"
        )
        assert status_before.status_code == 200
        assert status_before.json()["subscribed"] is False

        ws_url_1 = f"/ws/silbenstreit/{room_id}?player_id=host_1&name=Alice&color=%232563eb"
        ws_url_2 = f"/ws/silbenstreit/{room_id}?player_id=peer_2&name=Bob&color=%23dc2626"

        # Join both players, then subscribe once peer_2 is a member.
        with client.websocket_connect(ws_url_1) as ws1, client.websocket_connect(ws_url_2) as ws2:
            _ = ws1.receive_json()
            _ = ws1.receive_json()
            _ = ws2.receive_json()

        assert subscribe("peer_2", "http://127.0.0.1/push").status_code == 400
        assert subscribe("peer_2", "https://evil.example/push").status_code == 400

        assert subscribe("peer_2", peer_endpoint).status_code == 200
        for index in range(2, 6):
            extra = subscribe("peer_2", f"https://fcm.googleapis.com/fcm/send/peer2-{index}")
            assert extra.status_code == 200
        sixth = subscribe("peer_2", "https://updates.push.services.mozilla.com/wpush/v2/extra")
        assert sixth.status_code == 409
        assert subscribe("peer_2", peer_endpoint).status_code == 200

        for index in range(2, 6):
            endpoint = quote(f"https://fcm.googleapis.com/fcm/send/peer2-{index}", safe="")
            removed = client.delete(
                f"/api/rooms/{room_id}/notifications/subscribe"
                f"?player_id=peer_2&endpoint={endpoint}"
            )
            assert removed.status_code == 200
            assert removed.json()["deleted"] == 1

        status_after = client.get(
            f"/api/rooms/{room_id}/notifications/status?player_id=peer_2"
        )
        assert status_after.status_code == 200
        assert status_after.json() == {
            "room_id": room_id,
            "player_id": "peer_2",
            "subscribed": True,
            "count": 1,
        }

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
        unsub_res = client.delete(
            f"/api/rooms/{room_id}/notifications/subscribe?player_id=peer_2"
        )
        assert unsub_res.status_code == 200
        assert unsub_res.json()["deleted"] == 1

        status_final = client.get(
            f"/api/rooms/{room_id}/notifications/status?player_id=peer_2"
        )
        assert status_final.json()["subscribed"] is False

        # 6. A 401 from the push service drops that endpoint.
        assert subscribe("peer_2", peer_endpoint).status_code == 200
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

        status_pruned = client.get(
            f"/api/rooms/{room_id}/notifications/status?player_id=peer_2"
        )
        assert status_pruned.json()["subscribed"] is False
        assert len(dispatched) == 1

        client.delete(f"/api/rooms/{room_id}?player_id=host_1")


