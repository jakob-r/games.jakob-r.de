"""Sudoku Zero rules: capped solution counts, scoring formulas, and a bitmask solver.

The client counts solutions (``frontend/src/lib/games/sudoku-zero/solver.ts``); the
server only uses ``count_solutions`` to verify a claimed unique grid.
"""

from __future__ import annotations

import math

type Grid = list[list[int]]

SOLUTION_CAP = 1000
MIN_CLUES = 17
ZERO_CLUES = 80
MAX_END_BONUS = 1000
WRONG_CLUE_PENALTY = 50
POINTS_PER_CLUE = 1


def cap(solutions: int) -> int:
    """Counts above the cap are shown as "1000+" and scored as 1000."""
    return max(0, min(int(solutions), SOLUTION_CAP))


def clue_weight(clues: int) -> float:
    """``min(1, (17 / clues)²)``: cutting solutions early (few clues) is worth more."""
    return 1.0 if clues <= MIN_CLUES else (MIN_CLUES / clues) ** 2


def placement_bonus(before: int, after: int, clues: int) -> int:
    """``round(100 × log2(min(before, 1000) / after) × min(1, (17 / clues)²))``.

    ``clues`` counts the clues after this placement. At the same clue count, 1000→500
    equals 10→5.
    """
    b, a = cap(before), cap(after)
    if a <= 0 or b <= a:
        return 0
    return round(100 * math.log2(b / a) * clue_weight(clues))


def placement_points(before: int, after: int, clues: int) -> int:
    """+1 only while the count is still 1000+, plus the weighted bonus."""
    base = POINTS_PER_CLUE if cap(after) >= SOLUTION_CAP else 0
    return base + placement_bonus(before, after, clues)


def end_bonus(clues: int) -> int:
    """``round(1000 × clamp((80 − clues) / 63, 0, 1)²)``: 17 clues → 1000, 80 → 0."""
    share = max(0.0, min(1.0, (ZERO_CLUES - clues) / (ZERO_CLUES - MIN_CLUES)))
    return round(MAX_END_BONUS * share * share)


def has_conflict(grid: Grid, row: int, col: int, value: int) -> bool:
    """True if ``value`` already appears in the row, column, or box of (row, col)."""
    for i in range(9):
        if grid[row][i] == value and i != col:
            return True
        if grid[i][col] == value and i != row:
            return True
    br, bc = (row // 3) * 3, (col // 3) * 3
    for r in range(br, br + 3):
        for c in range(bc, bc + 3):
            if grid[r][c] == value and (r, c) != (row, col):
                return True
    return False


def count_solutions(grid: Grid, limit: int = 2) -> int:
    """Count completions up to ``limit`` (bitmask MRV backtracking)."""
    full = 0x3FE  # bits 1..9
    rows = [0] * 9
    cols = [0] * 9
    boxes = [0] * 9
    empties: list[int] = []
    for r in range(9):
        for c in range(9):
            v = grid[r][c]
            if v == 0:
                empties.append(r * 9 + c)
                continue
            bit = 1 << v
            b = (r // 3) * 3 + c // 3
            if rows[r] & bit or cols[c] & bit or boxes[b] & bit:
                return 0
            rows[r] |= bit
            cols[c] |= bit
            boxes[b] |= bit

    count = 0

    def search(remaining: list[int]) -> bool:
        """Returns True once ``limit`` is reached."""
        nonlocal count
        if not remaining:
            count += 1
            return count >= limit
        best_i = -1
        best_mask = 0
        best_n = 10
        for i, cell in enumerate(remaining):
            r, c = divmod(cell, 9)
            mask = full & ~(rows[r] | cols[c] | boxes[(r // 3) * 3 + c // 3])
            n = mask.bit_count()
            if n < best_n:
                best_i, best_mask, best_n = i, mask, n
                if n <= 1:
                    break
        if best_n == 0:
            return False
        cell = remaining[best_i]
        rest = remaining[:best_i] + remaining[best_i + 1 :]
        r, c = divmod(cell, 9)
        b = (r // 3) * 3 + c // 3
        mask = best_mask
        while mask:
            bit = mask & -mask
            mask ^= bit
            rows[r] |= bit
            cols[c] |= bit
            boxes[b] |= bit
            done = search(rest)
            rows[r] ^= bit
            cols[c] ^= bit
            boxes[b] ^= bit
            if done:
                return True
        return False

    search(empties)
    return count
