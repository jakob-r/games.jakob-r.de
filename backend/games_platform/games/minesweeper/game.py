"""Cooperative multiplayer Minesweeper with scoring and flag challenges."""

from __future__ import annotations

import copy
import random
from collections import deque
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from games_platform.core.protocol import ActionOutcome

DIFFICULTY_PRESETS: dict[str, tuple[int, int, int]] = {
    # (width, height, mine_count)
    "easy": (9, 9, 10),
    "medium": (16, 16, 40),
    "hard": (30, 16, 99),
}

VALID_DIFFICULTIES = set(DIFFICULTY_PRESETS.keys())

POINTS_REVEAL = 1.0
POINTS_FLAG = 2.0
POINTS_UNFLAG = -3.0
POINTS_MINE_HIT = -10.0
POINTS_CHALLENGE = 5.0


class RevealAction(BaseModel):
    type: Literal["reveal"] = "reveal"
    row: int = Field(ge=0)
    col: int = Field(ge=0)


class FlagAction(BaseModel):
    type: Literal["flag"] = "flag"
    row: int = Field(ge=0)
    col: int = Field(ge=0)


class UnflagAction(BaseModel):
    type: Literal["unflag"] = "unflag"
    row: int = Field(ge=0)
    col: int = Field(ge=0)


class ChallengeFlagAction(BaseModel):
    type: Literal["challenge_flag"] = "challenge_flag"
    row: int = Field(ge=0)
    col: int = Field(ge=0)


type MinesweeperAction = RevealAction | FlagAction | UnflagAction | ChallengeFlagAction

MINESWEEPER_ACTION_ADAPTER: TypeAdapter[MinesweeperAction] = TypeAdapter(MinesweeperAction)


def _key(row: int, col: int) -> str:
    return f"{row},{col}"


def _neighbors(row: int, col: int, width: int, height: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            rr, cc = row + dr, col + dc
            if 0 <= rr < height and 0 <= cc < width:
                out.append((rr, cc))
    return out


def _empty_cell() -> dict[str, Any]:
    return {
        "status": "hidden",
        "adjacent": 0,
        "flag_owner_id": None,
        "revealed_by": None,
    }


def place_mines(
    width: int,
    height: int,
    mine_count: int,
    safe_row: int,
    safe_col: int,
    *,
    rng: random.Random | None = None,
) -> set[str]:
    """Place mines avoiding the first-click cell and its neighbors."""
    rng = rng or random.Random()
    forbidden = {_key(safe_row, safe_col)}
    for rr, cc in _neighbors(safe_row, safe_col, width, height):
        forbidden.add(_key(rr, cc))

    candidates = [
        _key(r, c)
        for r in range(height)
        for c in range(width)
        if _key(r, c) not in forbidden
    ]
    count = min(mine_count, len(candidates))
    if count <= 0:
        return set()
    return set(rng.sample(candidates, count))


def compute_adjacency(
    width: int,
    height: int,
    mines: set[str],
) -> list[list[int]]:
    grid = [[0 for _ in range(width)] for _ in range(height)]
    for r in range(height):
        for c in range(width):
            if _key(r, c) in mines:
                continue
            grid[r][c] = sum(
                1 for rr, cc in _neighbors(r, c, width, height) if _key(rr, cc) in mines
            )
    return grid


class MinesweeperGame:
    """Self-contained cooperative Minesweeper game implementation."""

    slug: str = "minesweeper"
    title: str = "Co-op Minesweeper"
    description: str = (
        "Clear a shared minefield together. Dig for points, plant flags, and challenge "
        "suspect opponent flags — boom flashes cost points but the team plays on."
    )

    def default_config(self) -> dict[str, Any]:
        return {
            "difficulty": "easy",
            "scoring_enabled": True,
        }

    def validate_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        difficulty = str(raw_config.get("difficulty", "easy")).lower()
        if difficulty not in VALID_DIFFICULTIES:
            difficulty = "easy"
        return {
            "difficulty": difficulty,
            "scoring_enabled": bool(raw_config.get("scoring_enabled", True)),
        }

    def create_initial_state(
        self,
        config: dict[str, Any],
        player_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        _ = player_ids
        difficulty = str(config.get("difficulty", "easy"))
        width, height, mine_count = DIFFICULTY_PRESETS.get(
            difficulty, DIFFICULTY_PRESETS["easy"]
        )
        cells = [[_empty_cell() for _ in range(width)] for _ in range(height)]
        return {
            "width": width,
            "height": height,
            "mine_count": mine_count,
            "mines": [],  # placed on first reveal; never exposed in public view
            "mines_placed": False,
            "cells": cells,
            "safe_revealed": 0,
            "mines_hit": 0,
            "move_count": 0,
        }

    def get_public_view(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        width = int(state["width"])
        height = int(state["height"])
        cells_in = state["cells"]
        public_cells: list[list[dict[str, Any]]] = []
        for r in range(height):
            row_out: list[dict[str, Any]] = []
            for c in range(width):
                cell = cells_in[r][c]
                status = cell["status"]
                if status == "hidden":
                    row_out.append({"status": "hidden"})
                elif status == "flagged":
                    row_out.append(
                        {
                            "status": "flagged",
                            "flag_owner_id": cell.get("flag_owner_id"),
                        }
                    )
                elif status == "revealed":
                    row_out.append(
                        {
                            "status": "revealed",
                            "adjacent": int(cell.get("adjacent", 0)),
                            "revealed_by": cell.get("revealed_by"),
                        }
                    )
                elif status == "mine_revealed":
                    row_out.append(
                        {
                            "status": "mine_revealed",
                            "revealed_by": cell.get("revealed_by"),
                        }
                    )
                else:
                    row_out.append({"status": "hidden"})
            public_cells.append(row_out)

        mine_count = int(state["mine_count"])
        flagged_count = sum(
            1
            for r in range(height)
            for c in range(width)
            if cells_in[r][c]["status"] == "flagged"
        )
        mine_revealed_count = sum(
            1
            for r in range(height)
            for c in range(width)
            if cells_in[r][c]["status"] == "mine_revealed"
        )

        return {
            "width": width,
            "height": height,
            "mine_count": mine_count,
            "mines_placed": bool(state.get("mines_placed", False)),
            "cells": public_cells,
            "safe_revealed": int(state.get("safe_revealed", 0)),
            "safe_total": width * height - mine_count,
            "flagged_count": flagged_count,
            "mines_hit": int(state.get("mines_hit", 0)),
            "mines_secured_visible": flagged_count + mine_revealed_count,
            "difficulty": config.get("difficulty", "easy"),
            "scoring_enabled": bool(config.get("scoring_enabled", True)),
        }

    def _ensure_mines(
        self,
        state: dict[str, Any],
        safe_row: int,
        safe_col: int,
        *,
        rng: random.Random | None = None,
    ) -> None:
        if state.get("mines_placed"):
            return
        width = int(state["width"])
        height = int(state["height"])
        mine_count = int(state["mine_count"])
        mines = place_mines(width, height, mine_count, safe_row, safe_col, rng=rng)
        adjacency = compute_adjacency(width, height, mines)
        cells = state["cells"]
        for r in range(height):
            for c in range(width):
                cells[r][c]["adjacent"] = adjacency[r][c]
        state["mines"] = sorted(mines)
        state["mines_placed"] = True

    def _mine_set(self, state: dict[str, Any]) -> set[str]:
        return set(state.get("mines") or [])

    def _is_finished(self, state: dict[str, Any]) -> bool:
        width = int(state["width"])
        height = int(state["height"])
        mine_count = int(state["mine_count"])
        cells = state["cells"]
        mines = self._mine_set(state)

        if not state.get("mines_placed"):
            return False

        safe_total = width * height - mine_count
        if int(state.get("safe_revealed", 0)) >= safe_total:
            return True

        # All mines secured: correctly flagged or already revealed
        for mine_key in mines:
            r_s, c_s = mine_key.split(",", 1)
            r, c = int(r_s), int(c_s)
            status = cells[r][c]["status"]
            if status == "mine_revealed":
                continue
            if status == "flagged":
                continue
            return False
        return len(mines) == mine_count and len(mines) > 0

    def _flood_reveal(
        self,
        state: dict[str, Any],
        start_row: int,
        start_col: int,
        player_id: str,
    ) -> list[tuple[int, int, int]]:
        """Reveal cells starting at (start_row, start_col). Returns list of (r, c, adjacent)."""
        width = int(state["width"])
        height = int(state["height"])
        cells = state["cells"]
        mines = self._mine_set(state)
        revealed: list[tuple[int, int, int]] = []
        queue: deque[tuple[int, int]] = deque()
        queue.append((start_row, start_col))
        visited: set[str] = set()

        while queue:
            r, c = queue.popleft()
            k = _key(r, c)
            if k in visited:
                continue
            visited.add(k)
            cell = cells[r][c]
            if cell["status"] in ("revealed", "mine_revealed", "flagged"):
                continue
            if k in mines:
                continue

            cell["status"] = "revealed"
            cell["revealed_by"] = player_id
            cell["flag_owner_id"] = None
            adj = int(cell.get("adjacent", 0))
            revealed.append((r, c, adj))
            state["safe_revealed"] = int(state.get("safe_revealed", 0)) + 1

            if adj == 0:
                for rr, cc in _neighbors(r, c, width, height):
                    nk = _key(rr, cc)
                    if nk not in visited and cells[rr][cc]["status"] == "hidden":
                        queue.append((rr, cc))

        return revealed

    def apply_action(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
        action: dict[str, Any],
        player_multiplier: float,
    ) -> ActionOutcome:
        _ = player_multiplier  # fixed scoring; ignore streak multiplier
        parsed = MINESWEEPER_ACTION_ADAPTER.validate_python(action)
        next_state = copy.deepcopy(state)
        width = int(next_state["width"])
        height = int(next_state["height"])
        scoring_enabled = bool(config.get("scoring_enabled", True))

        row = parsed.row
        col = parsed.col
        if not (0 <= row < height and 0 <= col < width):
            return ActionOutcome(state=next_state)

        cells = next_state["cells"]
        cell = cells[row][col]

        match parsed:
            case RevealAction():
                return self._apply_reveal(
                    next_state, cell, row, col, player_id, scoring_enabled
                )
            case FlagAction():
                return self._apply_flag(
                    next_state, cell, row, col, player_id, scoring_enabled
                )
            case UnflagAction():
                return self._apply_unflag(
                    next_state, cell, row, col, player_id, scoring_enabled
                )
            case ChallengeFlagAction():
                return self._apply_challenge(
                    next_state, cell, row, col, player_id, scoring_enabled
                )

        return ActionOutcome(state=next_state)

    def _apply_reveal(
        self,
        state: dict[str, Any],
        cell: dict[str, Any],
        row: int,
        col: int,
        player_id: str,
        scoring_enabled: bool,
    ) -> ActionOutcome:
        if cell["status"] != "hidden":
            return ActionOutcome(state=state)

        self._ensure_mines(state, row, col)
        mines = self._mine_set(state)

        if _key(row, col) in mines:
            cell["status"] = "mine_revealed"
            cell["revealed_by"] = player_id
            cell["flag_owner_id"] = None
            state["mines_hit"] = int(state.get("mines_hit", 0)) + 1
            state["move_count"] = int(state.get("move_count", 0)) + 1
            pts = POINTS_MINE_HIT if scoring_enabled else 0.0
            return ActionOutcome(
                state=state,
                events=[
                    {
                        "type": "mine_hit",
                        "row": row,
                        "col": col,
                        "player_id": player_id,
                        "points_delta": pts,
                    }
                ],
                points_delta=pts,
                is_mistake=True,
                is_finished=self._is_finished(state),
            )

        revealed = self._flood_reveal(state, row, col, player_id)
        count = len(revealed)
        if count > 0:
            state["move_count"] = int(state.get("move_count", 0)) + 1
        pts = (POINTS_REVEAL * count) if scoring_enabled else 0.0
        return ActionOutcome(
            state=state,
            events=[
                {
                    "type": "cell_revealed",
                    "row": row,
                    "col": col,
                    "player_id": player_id,
                    "revealed_count": count,
                    "cells": [
                        {"row": r, "col": c, "adjacent": adj} for r, c, adj in revealed
                    ],
                    "points_delta": pts,
                }
            ],
            points_delta=pts,
            is_correct_entry=count > 0,
            is_finished=self._is_finished(state),
        )

    def _apply_flag(
        self,
        state: dict[str, Any],
        cell: dict[str, Any],
        row: int,
        col: int,
        player_id: str,
        scoring_enabled: bool,
    ) -> ActionOutcome:
        if cell["status"] != "hidden":
            return ActionOutcome(state=state)

        # Flags allowed before mines are placed (first dig places mines)
        cell["status"] = "flagged"
        cell["flag_owner_id"] = player_id
        state["move_count"] = int(state.get("move_count", 0)) + 1
        pts = POINTS_FLAG if scoring_enabled else 0.0
        finished = self._is_finished(state) if state.get("mines_placed") else False
        return ActionOutcome(
            state=state,
            events=[
                {
                    "type": "flag_placed",
                    "row": row,
                    "col": col,
                    "player_id": player_id,
                    "points_delta": pts,
                }
            ],
            points_delta=pts,
            is_correct_entry=True,
            is_finished=finished,
        )

    def _apply_unflag(
        self,
        state: dict[str, Any],
        cell: dict[str, Any],
        row: int,
        col: int,
        player_id: str,
        scoring_enabled: bool,
    ) -> ActionOutcome:
        if cell["status"] != "flagged":
            return ActionOutcome(state=state)
        if cell.get("flag_owner_id") != player_id:
            return ActionOutcome(state=state)

        cell["status"] = "hidden"
        cell["flag_owner_id"] = None
        state["move_count"] = int(state.get("move_count", 0)) + 1
        pts = POINTS_UNFLAG if scoring_enabled else 0.0
        return ActionOutcome(
            state=state,
            events=[
                {
                    "type": "flag_removed",
                    "row": row,
                    "col": col,
                    "player_id": player_id,
                    "points_delta": pts,
                }
            ],
            points_delta=pts,
            is_mistake=True,
            is_finished=self._is_finished(state) if state.get("mines_placed") else False,
        )

    def _apply_challenge(
        self,
        state: dict[str, Any],
        cell: dict[str, Any],
        row: int,
        col: int,
        player_id: str,
        scoring_enabled: bool,
    ) -> ActionOutcome:
        if cell["status"] != "flagged":
            return ActionOutcome(state=state)
        owner_id = cell.get("flag_owner_id")
        if owner_id is None or owner_id == player_id:
            return ActionOutcome(state=state)

        # Need mines placed to know correctness; place avoiding this cell if somehow not yet
        if not state.get("mines_placed"):
            self._ensure_mines(state, row, col)

        state["move_count"] = int(state.get("move_count", 0)) + 1
        mines = self._mine_set(state)
        was_correct = _key(row, col) in mines
        transfer = POINTS_CHALLENGE if scoring_enabled else 0.0

        if was_correct:
            cell["status"] = "mine_revealed"
            cell["revealed_by"] = owner_id
            cell["flag_owner_id"] = None
            return ActionOutcome(
                state=state,
                events=[
                    {
                        "type": "flag_challenged",
                        "row": row,
                        "col": col,
                        "player_id": player_id,
                        "owner_id": owner_id,
                        "was_correct": True,
                        "challenger_delta": -transfer,
                        "owner_delta": transfer,
                    }
                ],
                points_delta=-transfer,
                is_mistake=True,
                extra_score_deltas={owner_id: transfer} if transfer else {},
                is_finished=self._is_finished(state),
            )

        # Wrong flag: remove flag and reveal as safe (flood if zero). Challenge ±5 only.
        cell["status"] = "hidden"
        cell["flag_owner_id"] = None
        revealed = self._flood_reveal(state, row, col, player_id)
        return ActionOutcome(
            state=state,
            events=[
                {
                    "type": "flag_challenged",
                    "row": row,
                    "col": col,
                    "player_id": player_id,
                    "owner_id": owner_id,
                    "was_correct": False,
                    "challenger_delta": transfer,
                    "owner_delta": -transfer,
                    "revealed_count": len(revealed),
                    "cells": [
                        {"row": r, "col": c, "adjacent": adj} for r, c, adj in revealed
                    ],
                }
            ],
            points_delta=transfer,
            is_correct_entry=True,
            extra_score_deltas={owner_id: -transfer} if transfer else {},
            is_finished=self._is_finished(state),
        )


minesweeper_game = MinesweeperGame()
