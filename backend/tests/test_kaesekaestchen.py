"""Unit and integration tests for Multiplayer Käsekästchen."""

from __future__ import annotations

from fastapi.testclient import TestClient

from games_platform.core.db import Database
from games_platform.games.kaesekaestchen.game import (
    KaesekaestchenGame,
    compute_active_squares,
)
from games_platform.main import create_app


def test_kaesekaestchen_open_board_and_turn_rotation() -> None:
    game = KaesekaestchenGame()
    config = game.validate_config({"width": 3, "height": 3, "border_edges": []})
    state = game.create_initial_state(config, player_ids=["p1", "p2"])

    assert state["total_squares"] == 9
    assert state["current_player_id"] == "p1"

    # p2 tries to move out of turn -> ignored
    wrong_turn = game.apply_action(
        state=state,
        config=config,
        player_id="p2",
        action={"type": "draw_line", "orientation": "h", "row": 0, "col": 0},
        player_multiplier=1.0,
    )
    assert wrong_turn.state["h_edges"][0][0] is None
    assert wrong_turn.state["current_player_id"] == "p1"

    # p1 draws top edge of (0,0) -> no square closed -> turn passes to p2
    m1 = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={"type": "draw_line", "orientation": "h", "row": 0, "col": 0},
        player_multiplier=1.0,
    )
    assert m1.state["h_edges"][0][0] == "p1"
    assert m1.points_delta == 0.0
    assert m1.state["current_player_id"] == "p2"

    # p2 draws bottom edge of (0,0) -> turn passes to p1
    m2 = game.apply_action(
        state=m1.state,
        config=config,
        player_id="p2",
        action={"type": "draw_line", "orientation": "h", "row": 1, "col": 0},
        player_multiplier=1.0,
    )
    assert m2.state["current_player_id"] == "p1"

    # p1 draws left edge of (0,0) -> turn passes to p2
    m3 = game.apply_action(
        state=m2.state,
        config=config,
        player_id="p1",
        action={"type": "draw_line", "orientation": "v", "row": 0, "col": 0},
        player_multiplier=1.0,
    )
    assert m3.state["current_player_id"] == "p2"

    # p2 draws right edge of (0,0) -> closes square (0,0)! Gets +1 point and keeps turn!
    m4 = game.apply_action(
        state=m3.state,
        config=config,
        player_id="p2",
        action={"type": "draw_line", "orientation": "v", "row": 0, "col": 1},
        player_multiplier=1.0,
    )
    assert m4.is_correct_entry is True
    assert m4.points_delta == 1.0
    assert m4.state["square_owners"][0][0] == "p2"
    assert m4.state["claimed_squares"] == 1
    assert m4.state["current_player_id"] == "p2"


def test_kaesekaestchen_double_square_closure_and_custom_shape() -> None:
    """Enclose a 2x1 custom shape inside a 4x4 grid using border_edges and complete both squares at once."""
    game = KaesekaestchenGame()
    # Enclose squares (1,1) and (1,2) with their outer 6 boundary segments
    border_edges = [
        "h:1:1",
        "h:1:2",
        "h:2:1",
        "h:2:2",
        "v:1:1",
        "v:1:3",
    ]
    active = compute_active_squares(4, 4, set(border_edges))
    assert active[1][1] is True
    assert active[1][2] is True
    assert sum(1 for r in range(4) for c in range(4) if active[r][c]) == 2

    config = game.validate_config({"width": 4, "height": 4, "border_edges": border_edges})
    state = game.create_initial_state(config, player_ids=["p1", "p2"])
    assert state["total_squares"] == 2

    # Only the shared middle vertical edge v:1:2 is left open; drawing it closes BOTH squares!
    outcome = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={"type": "draw_line", "orientation": "v", "row": 1, "col": 2},
        player_multiplier=1.0,
    )
    assert outcome.is_correct_entry is True
    assert outcome.points_delta == 2.0
    assert outcome.is_finished is True
    assert outcome.state["square_owners"][1][1] == "p1"
    assert outcome.state["square_owners"][1][2] == "p1"
    assert outcome.state["current_player_id"] == "p1"


def test_full_multiplayer_kaesekaestchen_websocket_lifecycle() -> None:
    test_db = Database()
    app = create_app(database=test_db)

    with TestClient(app) as client:
        res = client.get("/api/games")
        assert res.status_code == 200
        games = res.json()
        assert any(g["slug"] == "kaesekaestchen" for g in games)

        create_res = client.post(
            "/api/rooms",
            json={
                "game_slug": "kaesekaestchen",
                "host_player_id": "host_k1",
                "host_name": "Clara",
                "host_color": "#15803d",
                "config": {"width": 3, "height": 3, "border_edges": []},
            },
        )
        assert create_res.status_code == 200
        room_id = create_res.json()["room_id"]

        ws_url_1 = f"/ws/kaesekaestchen/{room_id}?player_id=host_k1&name=Clara&color=%2315803d"
        ws_url_2 = f"/ws/kaesekaestchen/{room_id}?player_id=peer_k2&name=Erik&color=%237e22ce"

        with client.websocket_connect(ws_url_1) as ws1, client.websocket_connect(ws_url_2) as ws2:
            _ = ws1.receive_json()
            _ = ws1.receive_json()
            _ = ws2.receive_json()

            # Host starts the game
            ws1.send_json({"type": "start_game"})
            playing_1 = ws1.receive_json()
            _ = ws2.receive_json()
            assert playing_1["status"] == "playing"
            assert playing_1["state"]["total_squares"] == 9
            assert playing_1["state"]["current_player_id"] == "host_k1"

            # Host draws a line
            ws1.send_json(
                {
                    "type": "game_action",
                    "action": {"type": "draw_line", "orientation": "h", "row": 0, "col": 0},
                }
            )
            ev1 = ws1.receive_json()
            assert ev1["type"] == "line_drawn"
            state_after = ws1.receive_json()
            assert state_after["state"]["h_edges"][0][0] == "host_k1"
            assert state_after["state"]["current_player_id"] == "peer_k2"
