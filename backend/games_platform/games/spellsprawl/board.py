"""Pure board logic for Spellsprawl: sparse infinite grid, word runs, cross-words, scoring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

type Direction = Literal["right", "down"]
type Coord = tuple[int, int]

# Coordinates are unbounded in principle; clamp to keep state sane against abuse.
MAX_COORD = 1000
MAX_WORD_LENGTH = 30


def cell_key(row: int, col: int) -> str:
    return f"{row},{col}"


def parse_key(key: str) -> Coord:
    r, c = key.split(",")
    return int(r), int(c)


def letters_by_coord(cells: dict[str, dict[str, Any]]) -> dict[Coord, str]:
    return {parse_key(k): str(v["letter"]) for k, v in cells.items()}


def bounding_box(cells: dict[str, dict[str, Any]]) -> tuple[int, int, int, int] | None:
    """Return (min_row, min_col, max_row, max_col) or None for an empty grid."""
    if not cells:
        return None
    coords = [parse_key(k) for k in cells]
    rows = [r for r, _ in coords]
    cols = [c for _, c in coords]
    return min(rows), min(cols), max(rows), max(cols)


def bounding_area(cells: dict[str, dict[str, Any]]) -> int:
    box = bounding_box(cells)
    if box is None:
        return 0
    min_r, min_c, max_r, max_c = box
    return (max_r - min_r + 1) * (max_c - min_c + 1)


@dataclass
class FormedWord:
    word: str
    positions: list[Coord]
    # Indices into positions/word of letters that were already on the grid.
    existing: list[int]


@dataclass
class Placement:
    main: FormedWord
    cross_words: list[FormedWord] = field(default_factory=list)
    points: int = 0
    direction: Direction = "right"


@dataclass
class Rejection:
    reason: str
    word: str = ""


def _step(direction: Direction) -> Coord:
    return (0, 1) if direction == "right" else (1, 0)


def _other(direction: Direction) -> Direction:
    return "down" if direction == "right" else "right"


def _run(
    grid: dict[Coord, str],
    new: dict[Coord, str],
    start: Coord,
    direction: Direction,
) -> FormedWord:
    """Maximal contiguous run through `start` along `direction` over grid + new letters."""
    dr, dc = _step(direction)
    r, c = start
    while (r - dr, c - dc) in grid or (r - dr, c - dc) in new:
        r, c = r - dr, c - dc
    positions: list[Coord] = []
    chars: list[str] = []
    existing: list[int] = []
    while (r, c) in grid or (r, c) in new:
        if (r, c) in new:
            chars.append(new[(r, c)])
        else:
            existing.append(len(positions))
            chars.append(grid[(r, c)])
        positions.append((r, c))
        r, c = r + dr, c + dc
    return FormedWord(word="".join(chars), positions=positions, existing=existing)


def word_points(word: FormedWord, letter_score: Callable[[str], int]) -> int:
    return sum(letter_score(word.word[i]) for i in word.existing)


def evaluate_placement(
    cells: dict[str, dict[str, Any]],
    placements: list[tuple[int, int, str]],
    direction: Direction,
    letter_score: Callable[[str], int],
) -> Placement | Rejection:
    """
    Check geometry of new letters (row, col, letter) and collect the formed words.
    Dictionary validity is checked by the caller on main + cross words.
    """
    if not placements:
        return Rejection("empty")
    if len(placements) > MAX_WORD_LENGTH:
        return Rejection("too_long")

    grid = letters_by_coord(cells)
    new: dict[Coord, str] = {}
    for row, col, letter in placements:
        if abs(row) > MAX_COORD or abs(col) > MAX_COORD:
            return Rejection("out_of_bounds")
        if len(letter) != 1 or not ("A" <= letter <= "Z"):
            return Rejection("invalid_letter")
        if (row, col) in new:
            return Rejection("duplicate_cell")
        if (row, col) in grid:
            return Rejection("occupied")
        new[(row, col)] = letter

    rows = {r for r, _ in new}
    cols = {c for _, c in new}
    if len(new) > 1:
        if len(rows) == 1:
            direction = "right"
        elif len(cols) == 1:
            direction = "down"
        else:
            return Rejection("not_in_line")

    first = min(new)
    main = _run(grid, new, first, direction)
    if len(new) == 1 and len(main.word) < 2:
        # A single letter may only extend words in the other direction.
        direction = _other(direction)
        main = _run(grid, new, first, direction)

    if any(pos not in main.positions for pos in new):
        return Rejection("gap")
    if len(main.word) < 2:
        return Rejection("too_short")
    if len(main.word) > MAX_WORD_LENGTH:
        return Rejection("too_long", main.word)

    cross_direction = _other(direction)
    cross_words: list[FormedWord] = []
    for pos in main.positions:
        if pos not in new:
            continue
        cross = _run(grid, new, pos, cross_direction)
        if len(cross.word) >= 2:
            cross_words.append(cross)

    points = word_points(main, letter_score) + sum(
        word_points(w, letter_score) for w in cross_words
    )
    return Placement(main=main, cross_words=cross_words, points=points, direction=direction)
