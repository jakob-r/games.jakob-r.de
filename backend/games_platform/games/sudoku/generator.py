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


def generate_solved_grid(rng: random.Random | None = None) -> Grid:
    """Generate a uniformly varied, valid full 9x9 Sudoku solution grid.

    Uses a randomized backtracking fill (MRV, shuffled candidates) rather than a
    fixed base pattern, so rows are not shifted copies of each other.
    """
    r_gen = rng or random.Random()
    grid: Grid = [[0] * 9 for _ in range(9)]

    # The three diagonal boxes are independent of each other: fill them directly.
    for b in range(3):
        digits = list(range(1, 10))
        r_gen.shuffle(digits)
        for i, d in enumerate(digits):
            grid[b * 3 + i // 3][b * 3 + i % 3] = d

    def fill() -> bool:
        best: tuple[int, int] | None = None
        best_cands: list[int] = []
        for r in range(9):
            for c in range(9):
                if grid[r][c] == 0:
                    cands = get_candidates(grid, r, c)
                    if not cands:
                        return False
                    if best is None or len(cands) < len(best_cands):
                        best, best_cands = (r, c), list(cands)
        if best is None:
            return True
        r, c = best
        r_gen.shuffle(best_cands)
        for d in best_cands:
            grid[r][c] = d
            if fill():
                return True
        grid[r][c] = 0
        return False

    if not fill():  # pragma: no cover - diagonal boxes always extend to a full grid
        raise RuntimeError("Failed to generate a Sudoku solution grid")
    return grid


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
