"""Tests for Multiplayer Sudoku generator, game state machine, scoring, and RoomManager."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from games_platform.core.room_manager import compute_effective_multiplier
from games_platform.games.sudoku.game import SudokuGame
from games_platform.games.sudoku.generator import count_solutions, generate_sudoku_puzzle


def test_sudoku_generator_produces_unique_solution() -> None:
    givens, solution, hard_cells = generate_sudoku_puzzle(difficulty="medium", seed=42)
    assert len(givens) == 9
    assert len(solution) == 9
    assert len(hard_cells) == 9
    assert count_solutions(givens, limit=2) == 1

    for r in range(9):
        for c in range(9):
            if givens[r][c] != 0:
                assert givens[r][c] == solution[r][c]


def test_sudoku_notes_and_moves_and_scoring() -> None:
    game = SudokuGame()
    config = game.validate_config({"difficulty": "easy", "scoring_enabled": True})
    state = game.create_initial_state(config)

    # Find an empty cell
    empty_r, empty_c = -1, -1
    for r in range(9):
        for c in range(9):
            if state["cells"][r][c]["value"] is None:
                empty_r, empty_c = r, c
                break
        if empty_r != -1:
            break

    assert empty_r != -1

    # 1. Toggle corner note
    note_outcome = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={"type": "toggle_note", "row": empty_r, "col": empty_c, "digit": 5},
        player_multiplier=1.0,
    )
    assert note_outcome.state["notes"][empty_r][empty_c] == {"5": "p1"}

    # 2. Make a mistake -> cell remains empty, -10 points, mistake_flash event emitted
    correct_val = state["solution"][empty_r][empty_c]
    wrong_val = 1 if correct_val != 1 else 2

    mistake_outcome = game.apply_action(
        state=note_outcome.state,
        config=config,
        player_id="p1",
        action={"type": "set_value", "row": empty_r, "col": empty_c, "value": wrong_val},
        player_multiplier=1.21,
    )
    assert mistake_outcome.is_mistake is True
    assert mistake_outcome.points_delta == -10.0
    assert mistake_outcome.state["cells"][empty_r][empty_c]["value"] is None
    assert mistake_outcome.events[0]["type"] == "mistake_flash"

    # 3. Enter correct value with 1.1x multiplier -> cell filled in player's id, note cleared
    correct_outcome = game.apply_action(
        state=mistake_outcome.state,
        config=config,
        player_id="p1",
        action={"type": "set_value", "row": empty_r, "col": empty_c, "value": correct_val},
        player_multiplier=1.1,
    )
    assert correct_outcome.is_correct_entry is True
    assert correct_outcome.points_delta in (2.2, 5.5)
    assert correct_outcome.state["cells"][empty_r][empty_c]["value"] == correct_val
    assert correct_outcome.state["cells"][empty_r][empty_c]["author_id"] == "p1"
    assert correct_outcome.state["notes"][empty_r][empty_c] == {}

    # 4. Public view hides solution
    pub = game.get_public_view(correct_outcome.state, config)
    assert "solution" not in pub
    assert pub["cells"][empty_r][empty_c]["value"] == correct_val


def test_last_cell_in_row_scores_2_times_multiplier() -> None:
    game = SudokuGame()
    config = {"difficulty": "easy", "scoring_enabled": True}
    state = game.create_initial_state(config)

    # Fill all cells in row 0 except col 0
    for c in range(1, 9):
        state["cells"][0][c]["value"] = state["solution"][0][c]
        state["cells"][0][c]["author_id"] = "p2"
    state["cells"][0][0]["value"] = None
    state["cells"][0][0]["given"] = False

    outcome = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={"type": "set_value", "row": 0, "col": 0, "value": state["solution"][0][0]},
        player_multiplier=1.21,
    )
    assert outcome.is_correct_entry is True
    assert outcome.points_delta == round(2.0 * 1.21, 2)


def test_multiplier_decay_after_10_seconds() -> None:
    now = datetime.now(UTC)
    within = now - timedelta(seconds=6.5)
    expired = now - timedelta(seconds=10.5)

    assert compute_effective_multiplier(1.331, within, now) == 1.331
    assert compute_effective_multiplier(1.331, expired, now) == 1.0
    assert compute_effective_multiplier(1.331, None, now) == 1.0
