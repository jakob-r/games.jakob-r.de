"""Multiplayer Sudoku game state machine and scoring implementation."""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from games_platform.core.protocol import ActionOutcome
from games_platform.games.sudoku.generator import (
    Difficulty,
    generate_sudoku_puzzle,
    get_candidates,
)

VALID_DIFFICULTIES: set[str] = {"easy", "medium", "hard", "expert"}


class SetCellValueAction(BaseModel):
    type: Literal["set_value"] = "set_value"
    row: int = Field(ge=0, le=8)
    col: int = Field(ge=0, le=8)
    value: int = Field(ge=1, le=9)


class ClearCellAction(BaseModel):
    type: Literal["clear_cell"] = "clear_cell"
    row: int = Field(ge=0, le=8)
    col: int = Field(ge=0, le=8)


class ToggleNoteAction(BaseModel):
    type: Literal["toggle_note"] = "toggle_note"
    row: int = Field(ge=0, le=8)
    col: int = Field(ge=0, le=8)
    digit: int = Field(ge=1, le=9)


type SudokuAction = SetCellValueAction | ClearCellAction | ToggleNoteAction

SUDOKU_ACTION_ADAPTER: TypeAdapter[SudokuAction] = TypeAdapter(SudokuAction)


class SudokuGame:
    """Self-contained Multiplayer Sudoku game implementation."""

    slug: str = "sudoku"
    title: str = "Multiplayer Sudoku"
    description: str = (
        "Collaborative & competitive 9x9 Sudoku. Share corner notes, race for streak "
        "multipliers, and see every teammate's strokes in their color."
    )

    def default_config(self) -> dict[str, Any]:
        return {
            "difficulty": "medium",
            "scoring_enabled": True,
        }

    def validate_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        difficulty = str(raw_config.get("difficulty", "medium")).lower()
        if difficulty not in VALID_DIFFICULTIES:
            difficulty = "medium"
        scoring_enabled = bool(raw_config.get("scoring_enabled", True))
        return {
            "difficulty": difficulty,
            "scoring_enabled": scoring_enabled,
        }

    def create_initial_state(
        self,
        config: dict[str, Any],
        player_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        _ = player_ids
        difficulty: Difficulty = config.get("difficulty", "medium")
        givens, solution, hard_cells = generate_sudoku_puzzle(difficulty=difficulty)

        cells: list[list[dict[str, Any]]] = []
        notes: list[list[dict[str, str]]] = []
        for r in range(9):
            row_cells: list[dict[str, Any]] = []
            row_notes: list[dict[str, str]] = []
            for c in range(9):
                val = givens[r][c]
                row_cells.append(
                    {
                        "value": val if val != 0 else None,
                        "given": val != 0,
                        "author_id": None,
                    }
                )
                row_notes.append({})
            cells.append(row_cells)
            notes.append(row_notes)

        return {
            "givens": givens,
            "solution": solution,
            "hard_cells": hard_cells,
            "cells": cells,
            "notes": notes,
            "history_count": 0,
        }

    def get_public_view(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        """Return client-safe state without exposing `solution`."""
        cells = state.get("cells", [])
        notes = state.get("notes", [])
        hard_cells = state.get("hard_cells", [])

        filled_count = 0
        total_cells = 81
        for r in range(len(cells)):
            for c in range(len(cells[r])):
                if cells[r][c].get("value") is not None:
                    filled_count += 1

        return {
            "cells": cells,
            "notes": notes,
            "hard_cells": hard_cells,
            "filled_count": filled_count,
            "total_cells": total_cells,
            "difficulty": config.get("difficulty", "medium"),
            "scoring_enabled": bool(config.get("scoring_enabled", True)),
        }

    def _current_grid(self, cells: list[list[dict[str, Any]]]) -> list[list[int]]:
        return [[int(cells[r][c]["value"] or 0) for c in range(9)] for r in range(9)]

    def _completes_last_in_unit(
        self,
        grid_before: list[list[int]],
        row: int,
        col: int,
    ) -> tuple[bool, list[str]]:
        """Check if (row, col) is the last empty cell in its row, column, or 3x3 block."""
        completed_units: list[str] = []

        # Row check
        row_empty = [c for c in range(9) if grid_before[row][c] == 0]
        if row_empty == [col]:
            completed_units.append("row")

        # Column check
        col_empty = [r for r in range(9) if grid_before[r][col] == 0]
        if col_empty == [row]:
            completed_units.append("column")

        # Block check
        br, bc = (row // 3) * 3, (col // 3) * 3
        block_empty = [
            (r, c)
            for r in range(br, br + 3)
            for c in range(bc, bc + 3)
            if grid_before[r][c] == 0
        ]
        if block_empty == [(row, col)]:
            completed_units.append("block")

        return (len(completed_units) > 0, completed_units)

    def _clear_peer_notes(
        self,
        notes: list[list[dict[str, str]]],
        row: int,
        col: int,
        digit: int,
    ) -> None:
        """Clear `digit` from notes in the same row, column, and 3x3 block, and all notes in (row, col)."""
        notes[row][col] = {}
        key = str(digit)
        for i in range(9):
            notes[row][i].pop(key, None)
            notes[i][col].pop(key, None)
        br, bc = (row // 3) * 3, (col // 3) * 3
        for r in range(br, br + 3):
            for c in range(bc, bc + 3):
                notes[r][c].pop(key, None)

    def apply_action(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
        action: dict[str, Any],
        player_multiplier: float,
    ) -> ActionOutcome:
        parsed = SUDOKU_ACTION_ADAPTER.validate_python(action)
        next_state = copy.deepcopy(state)
        cells: list[list[dict[str, Any]]] = next_state["cells"]
        notes: list[list[dict[str, str]]] = next_state["notes"]
        solution: list[list[int]] = next_state["solution"]
        hard_cells: list[list[bool]] = next_state.get(
            "hard_cells", [[False] * 9 for _ in range(9)]
        )
        scoring_enabled = bool(config.get("scoring_enabled", True))

        match parsed:
            case ToggleNoteAction(row=r, col=c, digit=d):
                cell = cells[r][c]
                if cell["value"] is not None:
                    return ActionOutcome(state=next_state)
                cell_notes = notes[r][c]
                key = str(d)
                if key in cell_notes and cell_notes[key] == player_id:
                    del cell_notes[key]
                elif key in cell_notes:
                    # Another player had this note; toggle it off or claim it:
                    # In collaborative play, toggling an existing note removes it
                    del cell_notes[key]
                else:
                    cell_notes[key] = player_id
                return ActionOutcome(state=next_state)

            case ClearCellAction(row=r, col=c):
                cell = cells[r][c]
                if cell["given"]:
                    return ActionOutcome(state=next_state)
                # Since only correct entries are placed on the board, clearing a solved cell is a no-op,
                # but if notes exist on an empty cell, clear notes for that cell.
                if cell["value"] is None and notes[r][c]:
                    notes[r][c] = {}
                return ActionOutcome(state=next_state)

            case SetCellValueAction(row=r, col=c, value=val):
                cell = cells[r][c]
                if cell["given"] or cell["value"] is not None:
                    return ActionOutcome(state=next_state)

                expected = solution[r][c]
                if val != expected:
                    # Mistake: reject digit, flash error, deduct 10 points, reset multiplier
                    pts_delta = -10.0 if scoring_enabled else 0.0
                    return ActionOutcome(
                        state=next_state,
                        events=[
                            {
                                "type": "mistake_flash",
                                "row": r,
                                "col": c,
                                "value": val,
                                "player_id": player_id,
                                "points_delta": pts_delta,
                            }
                        ],
                        points_delta=pts_delta,
                        is_mistake=True,
                    )

                # Correct entry!
                grid_before = self._current_grid(cells)
                completes_last, completed_units = self._completes_last_in_unit(grid_before, r, c)
                cands_now = get_candidates(grid_before, r, c)
                is_hard = bool(hard_cells[r][c]) and len(cands_now) >= 2 and not completes_last

                # Scoring rules from idea.md:
                # - For filling out the last cell in a row, column or block the user gets 2 points * multiplier
                # - For filling out more difficult cells the user gets 5 points * multiplier
                if completes_last:
                    base_points = 2.0
                    reason = f"last in {' & '.join(completed_units)}"
                elif is_hard:
                    base_points = 5.0
                    reason = "difficult cell"
                else:
                    base_points = 2.0 if len(cands_now) == 1 else 5.0
                    reason = "single candidate" if base_points == 2.0 else "difficult cell"

                points_delta = round(base_points * player_multiplier, 2) if scoring_enabled else 0.0

                cell["value"] = val
                cell["author_id"] = player_id
                self._clear_peer_notes(notes, r, c, val)
                next_state["history_count"] = int(next_state.get("history_count", 0)) + 1

                is_finished = all(
                    cells[row_idx][col_idx]["value"] is not None
                    for row_idx in range(9)
                    for col_idx in range(9)
                )

                return ActionOutcome(
                    state=next_state,
                    events=[
                        {
                            "type": "cell_scored",
                            "row": r,
                            "col": c,
                            "value": val,
                            "player_id": player_id,
                            "points_delta": points_delta,
                            "base_points": base_points,
                            "multiplier": player_multiplier,
                            "reason": reason,
                        }
                    ],
                    points_delta=points_delta,
                    is_correct_entry=True,
                    is_finished=is_finished,
                )


sudoku_game = SudokuGame()
