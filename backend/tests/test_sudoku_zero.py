"""Unit tests for Sudoku Zero."""

from __future__ import annotations

from typing import Any

from games_platform.games.sudoku_zero.game import SudokuZeroGame
from games_platform.games.sudoku_zero.scoring import (
    count_solutions,
    end_bonus,
    has_conflict,
    placement_bonus,
    placement_points,
)

# A known 17-clue puzzle with exactly one solution.
PUZZLE_17 = "000000010400000000020000000000050407008000300001090000300400200050100000000806000"


def puzzle_clues() -> list[tuple[int, int, int]]:
    return [(i // 9, i % 9, int(ch)) for i, ch in enumerate(PUZZLE_17) if ch != "0"]


def grid_of(clues: list[tuple[int, int, int]]) -> list[list[int]]:
    grid = [[0] * 9 for _ in range(9)]
    for r, c, v in clues:
        grid[r][c] = v
    return grid


def place(game: SudokuZeroGame, state: dict[str, Any], pid: str, r: int, c: int, v: int, n: int):
    return game.apply_action(
        state, {}, pid, {"type": "place", "row": r, "col": c, "value": v, "solutions": n}, 1.0
    )


def test_scoring_formulas() -> None:
    assert end_bonus(17) == 1000
    assert end_bonus(10) == 1000
    assert end_bonus(80) == 0
    assert end_bonus(81) == 0
    assert end_bonus(25) == round(1000 * (55 / 63) ** 2)
    assert placement_bonus(1000, 500) == 100
    assert placement_bonus(10, 5) == 100
    assert placement_bonus(5000, 500) == 100  # before is capped at 1000
    assert placement_bonus(1000, 1000) == 0
    assert placement_bonus(1000, 0) == 0
    assert placement_points(1000, 1000) == 1


def test_solver_counts() -> None:
    assert count_solutions(grid_of(puzzle_clues()), limit=2) == 1
    assert count_solutions([[0] * 9 for _ in range(9)], limit=1000) == 1000
    assert count_solutions(grid_of(puzzle_clues()[1:]), limit=2) == 2
    # Two 1s in a row: no solution.
    assert count_solutions(grid_of([(0, 0, 1), (0, 1, 1)]), limit=2) == 0
    assert has_conflict(grid_of([(0, 0, 5)]), 1, 1, 5)
    assert not has_conflict(grid_of([(0, 0, 5)]), 4, 4, 5)


def test_config_and_seats() -> None:
    game = SudokuZeroGame()
    assert game.max_players(game.validate_config({"solo": True})) == 1
    assert game.max_players(game.validate_config({})) == 2
    state = game.create_initial_state({"solo": True}, ["a", "b"])
    assert state["turn_order"] == ["a"]
    assert state["solutions"] == 1000


def test_solo_place_and_reach_unique() -> None:
    game = SudokuZeroGame()
    state = game.create_initial_state({"solo": True}, ["a"])
    clues = puzzle_clues()
    out = place(game, state, "a", *clues[0], 1000)
    assert out.is_correct_entry and out.points_delta == 1
    state = out.state
    for r, c, v in clues[1:-1]:
        state = place(game, state, "a", r, c, v, 1000).state
    assert state["clues"] == 16
    out = place(game, state, "a", *clues[-1], 1)
    assert out.is_finished
    assert out.state["end_reason"] == "unique"
    assert out.state["end_bonus"] == 1000
    # 1 point + log bonus 1000→1 + full end bonus
    assert out.points_delta == 1 + placement_bonus(1000, 1) + 1000


def test_rejections_without_penalty() -> None:
    game = SudokuZeroGame()
    state = game.create_initial_state({"solo": True}, ["a"])
    state = place(game, state, "a", 0, 0, 5, 1000).state
    for r, c, v, n, reason in [
        (0, 0, 3, 1000, "occupied"),
        (0, 5, 5, 1000, "conflict"),
        (4, 4, 5, 1, "count_mismatch"),  # false uniqueness claim
    ]:
        out = place(game, state, "a", r, c, v, n)
        assert out.points_delta == 0 and not out.is_finished
        assert out.events[0]["reason"] == reason
        assert out.state["clues"] == 1
    state = place(game, state, "a", 4, 4, 1, 300).state
    out = place(game, state, "a", 8, 8, 1, 500)  # count may never grow
    assert out.events[0]["reason"] == "count_mismatch"


def test_solo_contradiction_and_give_up() -> None:
    game = SudokuZeroGame()
    state = game.create_initial_state({"solo": True}, ["a"])
    out = place(game, state, "a", 0, 0, 1, 0)
    assert out.is_mistake and out.is_finished and out.points_delta == -50
    assert out.state["failed_cell"] == {"row": 0, "col": 0, "value": 1}
    assert out.state["grid"][0][0] == 0
    assert out.state["end_reason"] == "contradiction"

    state = game.create_initial_state({"solo": True}, ["a"])
    out = game.apply_action(state, {}, "a", {"type": "give_up"}, 1.0)
    assert out.is_finished and out.points_delta == 0
    assert out.state["end_reason"] == "gave_up"


def test_multiplayer_turns_wrong_clues_and_passes() -> None:
    game = SudokuZeroGame()
    state = game.create_initial_state({}, ["a", "b"])
    assert place(game, state, "b", 0, 0, 1, 1000).events[0]["reason"] == "not_your_turn"
    assert (
        game.apply_action(state, {}, "a", {"type": "give_up"}, 1.0).events[0]["reason"]
        == "not_solo"
    )

    out = place(game, state, "a", 0, 0, 1, 0)
    assert out.is_mistake and not out.is_finished and out.points_delta == -50
    assert out.state["grid"][0][0] == 0
    assert out.state["current_player_id"] == "b"
    out = place(game, out.state, "b", 0, 0, 2, 0)
    assert out.is_finished and out.state["end_reason"] == "wrong_clues"

    # A valid clue in between resets the wrong-clue streak.
    state = place(game, game.create_initial_state({}, ["a", "b"]), "a", 0, 0, 1, 0).state
    state = place(game, state, "b", 0, 0, 1, 1000).state
    out = place(game, state, "a", 1, 1, 1, 0)
    assert not out.is_finished

    state = game.create_initial_state({}, ["a", "b"])
    out = game.apply_action(state, {}, "a", {"type": "pass_turn"}, 1.0)
    assert not out.is_finished and out.state["current_player_id"] == "b"
    out = game.apply_action(out.state, {}, "b", {"type": "pass_turn"}, 1.0)
    assert out.is_finished and out.state["end_reason"] == "passed"


def test_multiplayer_end_bonus_split() -> None:
    game = SudokuZeroGame()
    state = game.create_initial_state({}, ["a", "b"])
    clues = puzzle_clues()
    players = ["a", "b"]
    for i, (r, c, v) in enumerate(clues[:-1]):
        state = place(game, state, players[i % 2], r, c, v, 1000).state
    # 16 clues placed, so it's a's turn again.
    assert state["current_player_id"] == "a"
    out = place(game, state, "a", *clues[-1], 1)
    assert out.is_finished
    assert out.extra_score_deltas == {"b": 500.0}
    assert out.points_delta == 1 + placement_bonus(1000, 1) + 500
