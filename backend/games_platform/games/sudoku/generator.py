"""Sudoku board generator, uniqueness solver, and cell difficulty classifier."""

from __future__ import annotations

import random
from typing import Literal

type Difficulty = Literal["easy", "medium", "hard", "expert"]
type Grid = list[list[int]]

CLUES_BY_DIFFICULTY: dict[Difficulty, int] = {
    "easy": 42,
    "medium": 34,
    "hard": 28,
    "expert": 24,
}


def _pattern(r: int, c: int) -> int:
    return (3 * (r % 3) + r // 3 + c) % 9


def _shuffled(seq: list[int], rng: random.Random) -> list[int]:
    copy = list(seq)
    rng.shuffle(copy)
    return copy


def generate_solved_grid(rng: random.Random | None = None) -> Grid:
    """Generate a valid full 9x9 Sudoku solution grid."""
    r_gen = rng or random.Random()
    r_base = [0, 1, 2]
    rows = [g * 3 + r for g in _shuffled(r_base, r_gen) for r in _shuffled(r_base, r_gen)]
    cols = [g * 3 + c for g in _shuffled(r_base, r_gen) for c in _shuffled(r_base, r_gen)]
    nums = _shuffled(list(range(1, 10)), r_gen)
    return [[nums[_pattern(r, c)] for c in cols] for r in rows]


def get_candidates(grid: Grid, row: int, col: int) -> set[int]:
    """Return valid digits (1..9) that can be placed at (row, col) on the current grid."""
    if grid[row][col] != 0:
        return set()
    used: set[int] = set(grid[row])
    for r in range(9):
        used.add(grid[r][col])
    br, bc = (row // 3) * 3, (col // 3) * 3
    for r in range(br, br + 3):
        for c in range(bc, bc + 3):
            used.add(grid[r][c])
    return {d for d in range(1, 10) if d not in used}


def count_solutions(grid: Grid, limit: int = 2) -> int:
    """Count solutions up to `limit` using MRV (minimum remaining values) backtracking."""
    work = [list(row) for row in grid]

    def backtrack() -> int:
        best_r, best_c = -1, -1
        best_cands: set[int] | None = None
        for r in range(9):
            for c in range(9):
                if work[r][c] == 0:
                    cands = get_candidates(work, r, c)
                    if not cands:
                        return 0
                    if best_cands is None or len(cands) < len(best_cands):
                        best_r, best_c = r, c
                        best_cands = cands
                        if len(best_cands) == 1:
                            break
            if best_cands is not None and len(best_cands) == 1:
                break

        if best_cands is None:
            return 1

        total = 0
        for val in best_cands:
            work[best_r][best_c] = val
            total += backtrack()
            if total >= limit:
                work[best_r][best_c] = 0
                return total
        work[best_r][best_c] = 0
        return total

    return backtrack()


def compute_cell_difficulty(givens: Grid) -> list[list[bool]]:
    """Classify each cell as 'difficult' (True) vs standard/easy (False).

    A cell is marked as a 'more difficult cell' (worth 5 * multiplier points) if in the
    initial puzzle it has >= 3 candidates and is not a trivial naked single.
    """
    hard_cells: list[list[bool]] = [[False for _ in range(9)] for _ in range(9)]
    for r in range(9):
        for c in range(9):
            if givens[r][c] == 0:
                cands = get_candidates(givens, r, c)
                hard_cells[r][c] = len(cands) >= 3
    return hard_cells


def generate_sudoku_puzzle(
    difficulty: Difficulty = "medium",
    seed: int | None = None,
) -> tuple[Grid, Grid, list[list[bool]]]:
    """Generate (givens, solution, hard_cells) with a guaranteed unique solution."""
    rng = random.Random(seed)
    solution = generate_solved_grid(rng)
    givens = [list(row) for row in solution]

    target_clues = CLUES_BY_DIFFICULTY.get(difficulty, 34)
    positions = [(r, c) for r in range(9) for c in range(9)]
    rng.shuffle(positions)

    current_clues = 81
    for r, c in positions:
        if current_clues <= target_clues:
            break
        backup = givens[r][c]
        givens[r][c] = 0
        if count_solutions(givens, limit=2) != 1:
            givens[r][c] = backup
        else:
            current_clues -= 1

    hard_cells = compute_cell_difficulty(givens)
    return givens, solution, hard_cells
