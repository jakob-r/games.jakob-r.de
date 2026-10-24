"""Unit and integration tests for Co-op Minesweeper."""

from __future__ import annotations

import random

from fastapi.testclient import TestClient

from games_platform.core.db import Database
from games_platform.games.minesweeper.game import (
    MinesweeperGame,
    _key,
    compute_adjacency,
    place_mines,
)
from games_platform.main import create_app


def _force_mines(state: dict, mines: set[str]) -> dict:
    """Inject a known mine layout for deterministic tests."""
    width = int(state["width"])
    height = int(state["height"])
    adjacency = compute_adjacency(width, height, mines)
    cells = state["cells"]
    for r in range(height):
        for c in range(width):
            cells[r][c]["adjacent"] = adjacency[r][c]
    state["mines"] = sorted(mines)
    state["mines_placed"] = True
    state["mine_count"] = len(mines)
    return state


def test_place_mines_avoids_first_click_neighborhood() -> None:
    rng = random.Random(0)
    mines = place_mines(9, 9, 10, safe_row=4, safe_col=4, rng=rng)
    assert _key(4, 4) not in mines
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            assert _key(4 + dr, 4 + dc) not in mines
    assert len(mines) == 10


def test_public_view_hides_mines() -> None:
    game = MinesweeperGame()
    config = game.validate_config({"difficulty": "easy"})
    state = game.create_initial_state(config)
    state = _force_mines(state, {_key(0, 0), _key(1, 1)})
    view = game.get_public_view(state, config)
    assert "mines" not in view
    assert view["cells"][0][0]["status"] == "hidden"
    assert "adjacent" not in view["cells"][0][0]


def test_reveal_scores_flood_and_first_click_safe() -> None:
    game = MinesweeperGame()
    config = game.validate_config({"difficulty": "easy", "scoring_enabled": True})
    state = game.create_initial_state(config)

    outcome = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={"type": "reveal", "row": 4, "col": 4},
        player_multiplier=1.0,
    )
    assert outcome.state["mines_placed"] is True
    assert _key(4, 4) not in set(outcome.state["mines"])
    assert outcome.is_correct_entry is True
    assert outcome.points_delta == float(outcome.events[0]["revealed_count"])
    assert outcome.points_delta >= 1.0
    assert outcome.state["cells"][4][4]["status"] == "revealed"
    assert "mines" not in game.get_public_view(outcome.state, config)


def test_mine_hit_penalty_and_continue() -> None:
    game = MinesweeperGame()
    config = game.validate_config({"difficulty": "easy"})
    state = game.create_initial_state(config)
    # Two mines so revealing one does not finish via "all mines secured"
    state = _force_mines(state, {_key(0, 0), _key(8, 8)})

    outcome = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={"type": "reveal", "row": 0, "col": 0},
        player_multiplier=1.0,
    )
    assert outcome.is_mistake is True
    assert outcome.points_delta == -10.0
    assert outcome.state["cells"][0][0]["status"] == "mine_revealed"
    assert outcome.is_finished is False
    assert outcome.events[0]["type"] == "mine_hit"


def test_flag_unflag_scoring() -> None:
    game = MinesweeperGame()
    config = game.validate_config({"difficulty": "easy"})
    state = game.create_initial_state(config)

    flagged = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={"type": "flag", "row": 0, "col": 0},
        player_multiplier=1.0,
    )
    assert flagged.points_delta == 2.0
    assert flagged.is_correct_entry is True
    assert flagged.state["cells"][0][0]["flag_owner_id"] == "p1"

    # Other player cannot unflag
    denied = game.apply_action(
        state=flagged.state,
        config=config,
        player_id="p2",
        action={"type": "unflag", "row": 0, "col": 0},
        player_multiplier=1.0,
    )
    assert denied.state["cells"][0][0]["status"] == "flagged"
    assert denied.points_delta == 0.0

    removed = game.apply_action(
        state=flagged.state,
        config=config,
        player_id="p1",
        action={"type": "unflag", "row": 0, "col": 0},
        player_multiplier=1.0,
    )
    assert removed.is_mistake is True
    assert removed.points_delta == -3.0
    assert removed.state["cells"][0][0]["status"] == "hidden"


def test_challenge_correct_and_wrong_flag() -> None:
    game = MinesweeperGame()
    config = game.validate_config({"difficulty": "easy"})
    state = game.create_initial_state(config)
    # Mine at (0,0); (0,1) safe
    state = _force_mines(state, {_key(0, 0)})

    # p1 flags the real mine
    s1 = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={"type": "flag", "row": 0, "col": 0},
        player_multiplier=1.0,
    ).state
    # p1 flags a safe cell
    s2 = game.apply_action(
        state=s1,
        config=config,
        player_id="p1",
        action={"type": "flag", "row": 0, "col": 1},
        player_multiplier=1.0,
    ).state

    correct = game.apply_action(
        state=s2,
        config=config,
        player_id="p2",
        action={"type": "challenge_flag", "row": 0, "col": 0},
        player_multiplier=1.0,
    )
    assert correct.is_mistake is True
    assert correct.points_delta == -5.0
    assert correct.extra_score_deltas == {"p1": 5.0}
    assert correct.state["cells"][0][0]["status"] == "mine_revealed"
    assert correct.events[0]["was_correct"] is True

    wrong = game.apply_action(
        state=correct.state,
        config=config,
        player_id="p2",
        action={"type": "challenge_flag", "row": 0, "col": 1},
        player_multiplier=1.0,
    )
    assert wrong.is_correct_entry is True
    assert wrong.points_delta == 5.0
    assert wrong.extra_score_deltas == {"p1": -5.0}
    assert wrong.events[0]["was_correct"] is False
    assert wrong.state["cells"][0][1]["status"] == "revealed"


def test_win_all_mines_flagged() -> None:
    game = MinesweeperGame()
    config = game.validate_config({"difficulty": "easy"})
    state = game.create_initial_state(config)
    state["width"] = 2
    state["height"] = 2
    state["cells"] = [
        [
            {"status": "hidden", "adjacent": 0, "flag_owner_id": None, "revealed_by": None},
            {"status": "hidden", "adjacent": 0, "flag_owner_id": None, "revealed_by": None},
        ],
        [
            {"status": "hidden", "adjacent": 0, "flag_owner_id": None, "revealed_by": None},
            {"status": "hidden", "adjacent": 0, "flag_owner_id": None, "revealed_by": None},
        ],
    ]
    state = _force_mines(state, {_key(0, 0), _key(1, 1)})

    s1 = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={"type": "flag", "row": 0, "col": 0},
        player_multiplier=1.0,
    ).state
    assert game._is_finished(s1) is False

    done = game.apply_action(
        state=s1,
        config=config,
        player_id="p1",
        action={"type": "flag", "row": 1, "col": 1},
        player_multiplier=1.0,
    )
    assert done.is_finished is True


def test_win_all_safe_revealed() -> None:
    game = MinesweeperGame()
    config = game.validate_config({"difficulty": "easy"})
    state = game.create_initial_state(config)
    state["width"] = 2
    state["height"] = 1
    state["cells"] = [
        [
            {"status": "hidden", "adjacent": 1, "flag_owner_id": None, "revealed_by": None},
            {"status": "hidden", "adjacent": 0, "flag_owner_id": None, "revealed_by": None},
        ]
    ]
    state = _force_mines(state, {_key(0, 0)})

    outcome = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={"type": "reveal", "row": 0, "col": 1},
        player_multiplier=1.0,
    )
    assert outcome.state["safe_revealed"] == 1
    assert outcome.is_finished is True


def test_minesweeper_ws_lifecycle() -> None:
    app = create_app(database=Database(), enabled_games=["minesweeper"])
    with TestClient(app) as client:
        create = client.post(
            "/api/rooms",
            json={
                "game_slug": "minesweeper",
                "host_player_id": "host1",
                "host_name": "Host",
                "host_color": "#2563eb",
                "config": {"difficulty": "easy", "scoring_enabled": True},
            },
        )
        assert create.status_code == 200
        room = create.json()
        room_id = room["room_id"]

        with client.websocket_connect(
            f"/ws/minesweeper/{room_id}?player_id=host1&name=Host&color=%232563eb"
        ) as ws:
            snapshot = ws.receive_json()
            assert snapshot["type"] == "room_state"
            assert snapshot["status"] == "lobby"

            ws.send_json({"type": "set_ready", "is_ready": True})
            ready_state = ws.receive_json()
            assert ready_state["type"] == "room_state"
            assert ready_state["players"][0]["is_ready"] is True

            ws.send_json({"type": "start_game"})
            playing = ws.receive_json()
            assert playing["type"] == "room_state"
            assert playing["status"] == "playing"
            assert playing["state"]["width"] == 9
            assert "mines" not in playing["state"]

            ws.send_json(
                {
                    "type": "game_action",
                    "action": {"type": "reveal", "row": 4, "col": 4},
                }
            )
            # Events then room_state
            first = ws.receive_json()
            assert first["type"] in ("cell_revealed", "mine_hit", "room_state")
            if first["type"] != "room_state":
                after = ws.receive_json()
                assert after["type"] == "room_state"
                assert after["state"]["cells"][4][4]["status"] in (
                    "revealed",
                    "mine_revealed",
                )
