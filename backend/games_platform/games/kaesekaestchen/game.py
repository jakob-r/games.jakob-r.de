"""Multiplayer Käsekästchen (Dots and Boxes with custom board shapes) implementation."""

from __future__ import annotations

import copy
from collections import deque
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from games_platform.core.protocol import ActionOutcome

MIN_DIMENSION = 3
MAX_DIMENSION = 12
DEFAULT_WIDTH = 6
DEFAULT_HEIGHT = 6


class DrawLineAction(BaseModel):
    type: Literal["draw_line"] = "draw_line"
    orientation: Literal["h", "v"]
    row: int = Field(ge=0)
    col: int = Field(ge=0)


type KaesekaestchenAction = DrawLineAction

KAESEKAESTCHEN_ACTION_ADAPTER: TypeAdapter[KaesekaestchenAction] = TypeAdapter(
    KaesekaestchenAction
)


def parse_edge_key(key: str, width: int, height: int) -> tuple[str, int, int] | None:
    """Validate and parse an edge key like 'h:0:2' or 'v:1:3' within a width x height board."""
    parts = key.strip().split(":")
    if len(parts) != 3:
        return None
    orientation, r_str, c_str = parts
    if orientation not in ("h", "v"):
        return None
    try:
        r = int(r_str)
        c = int(c_str)
    except ValueError:
        return None

    if orientation == "h":
        if 0 <= r <= height and 0 <= c < width:
            return ("h", r, c)
    else:
        if 0 <= r < height and 0 <= c <= width:
            return ("v", r, c)
    return None


def format_edge_key(orientation: str, row: int, col: int) -> str:
    return f"{orientation}:{row}:{col}"


def compute_active_squares(
    width: int,
    height: int,
    border_edge_keys: set[str],
) -> list[list[bool]]:
    """
    Compute which squares in the width x height grid are active based on host-drawn border edges.

    - Flood-fill from outside the grid across open edges (edges not in `border_edge_keys`).
    - Any square not reachable from outside is enclosed by `border_edge_keys`.
    - If one or more squares are enclosed (`len(enclosed) > 0`), those enclosed squares form the
      custom board shape (excluding any single cell where all 4 sides are already pre-drawn).
    - If no squares are enclosed (`len(enclosed) == 0`), e.g. empty board or partial lines,
      all `width x height` squares are active (excluding any single square that has all 4 sides
      pre-drawn).
    """
    outside_reachable: list[list[bool]] = [[False] * width for _ in range(height)]
    queue: deque[tuple[int, int]] = deque()

    # Seed from outer boundary edges that are not blocked by border_edge_keys
    for c in range(width):
        if format_edge_key("h", 0, c) not in border_edge_keys and not outside_reachable[0][c]:
            outside_reachable[0][c] = True
            queue.append((0, c))
        if (
            format_edge_key("h", height, c) not in border_edge_keys
            and not outside_reachable[height - 1][c]
        ):
            outside_reachable[height - 1][c] = True
            queue.append((height - 1, c))

    for r in range(height):
        if format_edge_key("v", r, 0) not in border_edge_keys and not outside_reachable[r][0]:
            outside_reachable[r][0] = True
            queue.append((r, 0))
        if (
            format_edge_key("v", r, width) not in border_edge_keys
            and not outside_reachable[r][width - 1]
        ):
            outside_reachable[r][width - 1] = True
            queue.append((r, width - 1))

    while queue:
        r, c = queue.popleft()
        # Up (across h:r:c)
        if (
            r > 0
            and not outside_reachable[r - 1][c]
            and format_edge_key("h", r, c) not in border_edge_keys
        ):
            outside_reachable[r - 1][c] = True
            queue.append((r - 1, c))
        # Down (across h:r+1:c)
        if (
            r + 1 < height
            and not outside_reachable[r + 1][c]
            and format_edge_key("h", r + 1, c) not in border_edge_keys
        ):
            outside_reachable[r + 1][c] = True
            queue.append((r + 1, c))
        # Left (across v:r:c)
        if (
            c > 0
            and not outside_reachable[r][c - 1]
            and format_edge_key("v", r, c) not in border_edge_keys
        ):
            outside_reachable[r][c - 1] = True
            queue.append((r, c - 1))
        # Right (across v:r:c+1)
        if (
            c + 1 < width
            and not outside_reachable[r][c + 1]
            and format_edge_key("v", r, c + 1) not in border_edge_keys
        ):
            outside_reachable[r][c + 1] = True
            queue.append((r, c + 1))

    def is_all_four_sides_drawn(r: int, c: int) -> bool:
        return (
            format_edge_key("h", r, c) in border_edge_keys
            and format_edge_key("h", r + 1, c) in border_edge_keys
            and format_edge_key("v", r, c) in border_edge_keys
            and format_edge_key("v", r, c + 1) in border_edge_keys
        )

    enclosed_squares = [
        (r, c)
        for r in range(height)
        for c in range(width)
        if not outside_reachable[r][c] and not is_all_four_sides_drawn(r, c)
    ]

    active: list[list[bool]] = [[False] * width for _ in range(height)]
    if enclosed_squares:
        for r, c in enclosed_squares:
            active[r][c] = True
    else:
        for r in range(height):
            for c in range(width):
                if not is_all_four_sides_drawn(r, c):
                    active[r][c] = True

    return active


def edge_touches_active_square(
    orientation: str,
    row: int,
    col: int,
    active_squares: list[list[bool]],
    width: int,
    height: int,
) -> bool:
    if orientation == "h":
        return bool(
            (row > 0 and active_squares[row - 1][col])
            or (row < height and active_squares[row][col])
        )
    return bool(
        (col > 0 and active_squares[row][col - 1])
        or (col < width and active_squares[row][col])
    )


class KaesekaestchenGame:
    """Self-contained Multiplayer Käsekästchen game implementation."""

    slug: str = "kaesekaestchen"
    title: str = "Käsekästchen"
    description: str = (
        "Round-based Dots & Boxes on a customizable grid. Draw lines in your color, "
        "close squares to score a point and earn an extra turn!"
    )

    def default_config(self) -> dict[str, Any]:
        return {
            "width": DEFAULT_WIDTH,
            "height": DEFAULT_HEIGHT,
            "border_edges": [],
            "scoring_enabled": True,
        }

    def validate_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        try:
            width = int(raw_config.get("width", DEFAULT_WIDTH))
        except (TypeError, ValueError):
            width = DEFAULT_WIDTH
        try:
            height = int(raw_config.get("height", DEFAULT_HEIGHT))
        except (TypeError, ValueError):
            height = DEFAULT_HEIGHT

        width = max(MIN_DIMENSION, min(MAX_DIMENSION, width))
        height = max(MIN_DIMENSION, min(MAX_DIMENSION, height))

        raw_edges = raw_config.get("border_edges", [])
        valid_edges: list[str] = []
        seen: set[str] = set()
        if isinstance(raw_edges, list):
            for item in raw_edges:
                if not isinstance(item, str):
                    continue
                parsed = parse_edge_key(item, width, height)
                if parsed is not None:
                    canonical = format_edge_key(*parsed)
                    if canonical not in seen:
                        seen.add(canonical)
                        valid_edges.append(canonical)

        return {
            "width": width,
            "height": height,
            "border_edges": valid_edges,
            "scoring_enabled": True,
        }

    def create_initial_state(
        self,
        config: dict[str, Any],
        player_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        validated = self.validate_config(config)
        width: int = validated["width"]
        height: int = validated["height"]
        border_edges_list: list[str] = validated["border_edges"]
        border_edge_keys = set(border_edges_list)

        active_squares = compute_active_squares(width, height, border_edge_keys)

        # Ensure at least one square is active (fallback to full rectangle if all squares were 1x1 blocked)
        total_active = sum(
            1 for r in range(height) for c in range(width) if active_squares[r][c]
        )
        if total_active == 0:
            active_squares = [[True] * width for _ in range(height)]
            border_edge_keys = set()
            total_active = width * height

        h_edges: list[list[str | None]] = [
            [None for _ in range(width)] for _ in range(height + 1)
        ]
        v_edges: list[list[str | None]] = [
            [None for _ in range(width + 1)] for _ in range(height)
        ]

        # Pre-populate valid border edges that touch at least one active square
        for key in border_edge_keys:
            parsed = parse_edge_key(key, width, height)
            if parsed is None:
                continue
            ori, r, c = parsed
            if not edge_touches_active_square(ori, r, c, active_squares, width, height):
                continue
            if ori == "h":
                h_edges[r][c] = "border"
            else:
                v_edges[r][c] = "border"

        square_owners: list[list[str | None]] = [
            [None for _ in range(width)] for _ in range(height)
        ]

        turn_order: list[str] = list(player_ids or [])
        current_player_id: str | None = turn_order[0] if turn_order else None

        return {
            "width": width,
            "height": height,
            "active_squares": active_squares,
            "h_edges": h_edges,
            "v_edges": v_edges,
            "square_owners": square_owners,
            "turn_order": turn_order,
            "current_turn_index": 0,
            "current_player_id": current_player_id,
            "total_squares": total_active,
            "claimed_squares": 0,
            "move_count": 0,
            "last_move": None,
        }

    def get_public_view(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        _ = config
        return state

    def _is_square_closed(
        self,
        r: int,
        c: int,
        h_edges: list[list[str | None]],
        v_edges: list[list[str | None]],
    ) -> bool:
        return (
            h_edges[r][c] is not None
            and h_edges[r + 1][c] is not None
            and v_edges[r][c] is not None
            and v_edges[r][c + 1] is not None
        )

    def apply_action(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
        action: dict[str, Any],
        player_multiplier: float,
    ) -> ActionOutcome:
        _ = config, player_multiplier
        parsed = KAESEKAESTCHEN_ACTION_ADAPTER.validate_python(action)
        next_state = copy.deepcopy(state)

        width: int = int(next_state["width"])
        height: int = int(next_state["height"])
        active_squares: list[list[bool]] = next_state["active_squares"]
        h_edges: list[list[str | None]] = next_state["h_edges"]
        v_edges: list[list[str | None]] = next_state["v_edges"]
        square_owners: list[list[str | None]] = next_state["square_owners"]
        turn_order: list[str] = list(next_state.get("turn_order") or [])

        if player_id not in turn_order:
            turn_order.append(player_id)
            next_state["turn_order"] = turn_order

        current_player_id = next_state.get("current_player_id")
        if current_player_id is None:
            current_player_id = player_id
            next_state["current_player_id"] = current_player_id
            next_state["current_turn_index"] = turn_order.index(player_id)

        # Enforce round-based turn order
        if player_id != current_player_id:
            return ActionOutcome(state=next_state)

        ori = parsed.orientation
        r = parsed.row
        c = parsed.col

        # Bounds check
        if ori == "h":
            if not (0 <= r <= height and 0 <= c < width):
                return ActionOutcome(state=next_state)
            if h_edges[r][c] is not None:
                return ActionOutcome(state=next_state)
        else:
            if not (0 <= r < height and 0 <= c <= width):
                return ActionOutcome(state=next_state)
            if v_edges[r][c] is not None:
                return ActionOutcome(state=next_state)

        # Edge must touch at least one active square
        if not edge_touches_active_square(ori, r, c, active_squares, width, height):
            return ActionOutcome(state=next_state)

        # Place line in player's ID
        if ori == "h":
            h_edges[r][c] = player_id
            adjacent_coords = [(r - 1, c), (r, c)]
        else:
            v_edges[r][c] = player_id
            adjacent_coords = [(r, c - 1), (r, c)]

        newly_closed: list[dict[str, int]] = []
        for sr, sc in adjacent_coords:
            if (
                0 <= sr < height
                and 0 <= sc < width
                and active_squares[sr][sc]
                and square_owners[sr][sc] is None
                and self._is_square_closed(sr, sc, h_edges, v_edges)
            ):
                square_owners[sr][sc] = player_id
                newly_closed.append({"row": sr, "col": sc})

        next_state["move_count"] = int(next_state.get("move_count", 0)) + 1
        next_state["last_move"] = {
            "orientation": ori,
            "row": r,
            "col": c,
            "player_id": player_id,
            "closed_squares": newly_closed,
        }

        claimed_squares = sum(
            1
            for row_idx in range(height)
            for col_idx in range(width)
            if active_squares[row_idx][col_idx] and square_owners[row_idx][col_idx] is not None
        )
        total_squares = int(next_state.get("total_squares", width * height))
        next_state["claimed_squares"] = claimed_squares
        is_finished = claimed_squares >= total_squares

        if newly_closed:
            # Player closed at least one square: gets 1 point per closed square and keeps their turn!
            points_delta = float(len(newly_closed))
            is_correct = True
        else:
            # Did not close a square: advance to next player's turn
            points_delta = 0.0
            is_correct = False
            if turn_order:
                curr_idx = (
                    turn_order.index(player_id)
                    if player_id in turn_order
                    else int(next_state.get("current_turn_index", 0))
                )
                next_idx = (curr_idx + 1) % len(turn_order)
                next_state["current_turn_index"] = next_idx
                next_state["current_player_id"] = turn_order[next_idx]

        event = {
            "type": "line_drawn",
            "orientation": ori,
            "row": r,
            "col": c,
            "player_id": player_id,
            "closed_squares": newly_closed,
            "points_delta": points_delta,
            "next_player_id": next_state["current_player_id"],
        }

        return ActionOutcome(
            state=next_state,
            events=[event],
            points_delta=points_delta,
            is_correct_entry=is_correct,
            is_finished=is_finished,
        )


kaesekaestchen_game = KaesekaestchenGame()
