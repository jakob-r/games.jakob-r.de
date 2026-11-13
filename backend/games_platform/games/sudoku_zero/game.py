"""Sudoku Zero: place as few clues as possible until exactly one Sudoku remains.

Solution counting happens on the client (capped at 1000) and is sent with every
placement. The server checks the Sudoku rules itself, requires the count to never
grow, and verifies a claimed unique grid with its own solver. See ARCHITECTURE.md.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from games_platform.core.protocol import ActionOutcome
from games_platform.games.sudoku_zero.scoring import (
    SOLUTION_CAP,
    WRONG_CLUE_PENALTY,
    cap,
    count_solutions,
    end_bonus,
    has_conflict,
    placement_points,
)

MAX_PLAYERS = 2


class PlaceClueAction(BaseModel):
    type: Literal["place"] = "place"
    row: int = Field(ge=0, le=8)
    col: int = Field(ge=0, le=8)
    value: int = Field(ge=1, le=9)
    # Capped solution count the client computed for the grid including this clue.
    solutions: int = Field(ge=0)


class PassTurnAction(BaseModel):
    type: Literal["pass_turn"] = "pass_turn"


class GiveUpAction(BaseModel):
    type: Literal["give_up"] = "give_up"


type SudokuZeroAction = PlaceClueAction | PassTurnAction | GiveUpAction

ACTION_ADAPTER: TypeAdapter[SudokuZeroAction] = TypeAdapter(SudokuZeroAction)


def _reject(state: dict[str, Any], player_id: str, reason: str, **extra: Any) -> ActionOutcome:
    return ActionOutcome(
        state=state,
        events=[{"type": "clue_rejected", "player_id": player_id, "reason": reason, **extra}],
    )


class SudokuZeroGame:
    """Solo (config ``solo``) or 2-player turn-based Sudoku Zero."""

    slug: str = "sudoku-zero"
    title: str = "Sudoku Zero"
    description: str = (
        "Sudoku from scratch: start with an empty grid and place as few clues as possible "
        "until exactly one solution remains. Solo or two players taking turns."
    )
    solo_turn_goes_to_joiner: bool = True

    def default_config(self) -> dict[str, Any]:
        return {"solo": False, "scoring_enabled": True}

    def validate_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        return {
            # Solo: one seat (see max_players), so nobody else can join.
            "solo": bool(raw_config.get("solo", False)),
            "scoring_enabled": True,
        }

    def max_players(self, config: dict[str, Any]) -> int:
        return 1 if config.get("solo") else MAX_PLAYERS

    def create_initial_state(
        self,
        config: dict[str, Any],
        player_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        solo = bool(self.validate_config(config)["solo"])
        turn_order = list(player_ids or [])[: 1 if solo else MAX_PLAYERS]
        return {
            "solo": solo,
            "grid": [[0] * 9 for _ in range(9)],
            "owners": [[None] * 9 for _ in range(9)],
            "solutions": SOLUTION_CAP,
            "clues": 0,
            "turn_order": turn_order,
            "current_turn_index": 0,
            "current_player_id": turn_order[0] if turn_order else None,
            "consecutive_passes": 0,
            "consecutive_wrongs": 0,
            "move_count": 0,
            "last_move": None,
            # Solo: the clue that left no solution (shown in red, not part of the grid).
            "failed_cell": None,
            # unique | gave_up | contradiction | passed | wrong_clues
            "end_reason": None,
            "end_bonus": None,
        }

    def get_public_view(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        _ = config
        return state

    def _advance_turn(self, state: dict[str, Any], player_id: str) -> None:
        turn_order: list[str] = list(state.get("turn_order") or [])
        if not turn_order:
            return
        idx = (
            turn_order.index(player_id)
            if player_id in turn_order
            else int(state.get("current_turn_index", 0))
        )
        nxt = (idx + 1) % len(turn_order)
        state["current_turn_index"] = nxt
        state["current_player_id"] = turn_order[nxt]

    def apply_action(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
        action: dict[str, Any],
        player_multiplier: float,
    ) -> ActionOutcome:
        _ = config, player_multiplier  # own scoring, no platform streak multiplier
        parsed = ACTION_ADAPTER.validate_python(action)
        s = copy.deepcopy(state)
        solo = bool(s.get("solo"))

        turn_order: list[str] = list(s.get("turn_order") or [])
        if player_id not in turn_order and len(turn_order) < (1 if solo else MAX_PLAYERS):
            turn_order.append(player_id)
            s["turn_order"] = turn_order
        if s.get("current_player_id") is None and turn_order:
            s["current_player_id"] = turn_order[0]
            s["current_turn_index"] = 0

        if s.get("end_reason") is not None:
            return _reject(s, player_id, "finished")
        if player_id != s.get("current_player_id"):
            return _reject(s, player_id, "not_your_turn")

        match parsed:
            case GiveUpAction() | PassTurnAction() if solo:
                s["move_count"] = int(s.get("move_count", 0)) + 1
                s["last_move"] = {"type": "give_up", "player_id": player_id}
                s["end_reason"] = "gave_up"
                return ActionOutcome(
                    state=s,
                    events=[{"type": "gave_up", "player_id": player_id}],
                    is_finished=True,
                )
            case GiveUpAction():
                return _reject(s, player_id, "not_solo")
            case PassTurnAction():
                return self._pass(s, player_id)
            case PlaceClueAction():
                return self._place(s, player_id, parsed)

    def _pass(self, s: dict[str, Any], player_id: str) -> ActionOutcome:
        passes = int(s.get("consecutive_passes", 0)) + 1
        s["consecutive_passes"] = passes
        s["consecutive_wrongs"] = 0
        s["move_count"] = int(s.get("move_count", 0)) + 1
        s["last_move"] = {"type": "pass", "player_id": player_id}
        is_finished = passes >= max(2, len(s.get("turn_order") or []))
        if is_finished:
            s["end_reason"] = "passed"
        else:
            self._advance_turn(s, player_id)
        return ActionOutcome(
            state=s,
            events=[
                {
                    "type": "turn_passed",
                    "player_id": player_id,
                    "next_player_id": s["current_player_id"],
                }
            ],
            is_finished=is_finished,
        )

    def _place(self, s: dict[str, Any], player_id: str, act: PlaceClueAction) -> ActionOutcome:
        grid: list[list[int]] = s["grid"]
        row, col, value = act.row, act.col, act.value
        cell = {"row": row, "col": col, "value": value}
        before = int(s.get("solutions", SOLUTION_CAP))
        claimed = cap(act.solutions)

        if grid[row][col] != 0:
            return _reject(s, player_id, "occupied", **cell)
        if has_conflict(grid, row, col, value):
            return _reject(s, player_id, "conflict", **cell)
        if claimed > before:
            return _reject(s, player_id, "count_mismatch", **cell)

        if claimed == 0:
            return self._wrong_clue(s, player_id, cell)

        if claimed == 1:
            grid[row][col] = value
            if count_solutions(grid, limit=2) != 1:
                grid[row][col] = 0
                return _reject(s, player_id, "count_mismatch", **cell)
        else:
            grid[row][col] = value

        s["owners"][row][col] = player_id
        s["clues"] = int(s.get("clues", 0)) + 1
        s["solutions"] = claimed
        s["consecutive_passes"] = 0
        s["consecutive_wrongs"] = 0
        s["move_count"] = int(s.get("move_count", 0)) + 1
        points = placement_points(before, claimed)

        extra: dict[str, float] = {}
        bonus: int | None = None
        is_finished = claimed == 1
        if is_finished:
            bonus = end_bonus(s["clues"])
            s["end_bonus"] = bonus
            s["end_reason"] = "unique"
            players = list(s.get("turn_order") or [player_id])
            share = round(bonus / len(players))
            points += share
            extra = {pid: float(share) for pid in players if pid != player_id}
        else:
            self._advance_turn(s, player_id)

        s["last_move"] = {
            "type": "place",
            "player_id": player_id,
            **cell,
            "solutions_before": before,
            "solutions": claimed,
            "points": points,
            "end_bonus": bonus,
        }
        return ActionOutcome(
            state=s,
            events=[
                {
                    "type": "clue_placed",
                    "player_id": player_id,
                    **cell,
                    "solutions": claimed,
                    "points": points,
                    "next_player_id": s["current_player_id"],
                }
            ],
            points_delta=float(points),
            is_correct_entry=True,
            is_finished=is_finished,
            extra_score_deltas=extra,
        )

    def _wrong_clue(self, s: dict[str, Any], player_id: str, cell: dict[str, int]) -> ActionOutcome:
        """A clue that leaves no solution: solo ends the round, multiplayer rejects it."""
        s["move_count"] = int(s.get("move_count", 0)) + 1
        s["last_move"] = {"type": "wrong", "player_id": player_id, **cell}
        event = {
            "type": "clue_rejected",
            "player_id": player_id,
            "reason": "no_solution",
            "penalty": WRONG_CLUE_PENALTY,
            **cell,
        }
        if s.get("solo"):
            s["failed_cell"] = cell
            s["end_reason"] = "contradiction"
            is_finished = True
        else:
            wrongs = int(s.get("consecutive_wrongs", 0)) + 1
            s["consecutive_wrongs"] = wrongs
            s["consecutive_passes"] = 0
            is_finished = wrongs >= max(2, len(s.get("turn_order") or []))
            if is_finished:
                s["end_reason"] = "wrong_clues"
            else:
                self._advance_turn(s, player_id)
        return ActionOutcome(
            state=s,
            events=[event],
            points_delta=-float(WRONG_CLUE_PENALTY),
            is_mistake=True,
            is_finished=is_finished,
        )


sudoku_zero_game = SudokuZeroGame()
