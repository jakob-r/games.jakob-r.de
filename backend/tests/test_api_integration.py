"""End-to-end integration tests with PostgreSQL, FastAPI REST endpoints, and WebSockets."""

from __future__ import annotations

from fastapi.testclient import TestClient

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
            empty_r, empty_c = next(
                (r, c)
                for r in range(9)
                for c in range(9)
                if cells[r][c]["value"] is None
            )
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

        # 4. Check recent rooms & stats endpoints
        recent_res = client.get("/api/players/host_1/recent")
        assert recent_res.status_code == 200
        recent_list = recent_res.json()
        assert any(r["room_id"] == room_id for r in recent_list)

        stats_res = client.get("/api/players/host_1/stats")
        assert stats_res.status_code == 200
        assert stats_res.json()["summary"]["rooms_joined"] >= 1

        # 5. Non-host cannot delete the room
        forbidden_del = client.delete(f"/api/rooms/{room_id}?player_id=peer_2")
        assert forbidden_del.status_code == 403

        # 6. Host permanently deletes the room
        ok_del = client.delete(f"/api/rooms/{room_id}?player_id=host_1")
        assert ok_del.status_code == 200
        assert ok_del.json() == {"status": "deleted", "room_id": room_id}

        # Room is gone from GET /api/rooms/{room_id} and recent rooms
        missing_res = client.get(f"/api/rooms/{room_id}")
        assert missing_res.status_code == 404

        recent_after = client.get("/api/players/host_1/recent").json()
        assert all(r["room_id"] != room_id for r in recent_after)

