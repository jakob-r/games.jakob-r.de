/** Solution counting for Sudoku Zero (mirrors backend `sudoku_zero/scoring.py`). */

export const SOLUTION_CAP = 1000;
const FULL = 0x3fe; // bits 1..9

function popcount(mask: number): number {
	let n = 0;
	while (mask) {
		mask &= mask - 1;
		n++;
	}
	return n;
}

/** Count completions of a row-major 81-cell grid (0 = empty), stopping at `limit`. */
export function countSolutions(grid: readonly number[], limit = SOLUTION_CAP): number {
	const rows = new Int32Array(9);
	const cols = new Int32Array(9);
	const boxes = new Int32Array(9);
	const empties: number[] = [];
	for (let i = 0; i < 81; i++) {
		const v = grid[i] ?? 0;
		if (!v) {
			empties.push(i);
			continue;
		}
		const r = (i / 9) | 0;
		const c = i % 9;
		const b = ((r / 3) | 0) * 3 + ((c / 3) | 0);
		const bit = 1 << v;
		if (rows[r] & bit || cols[c] & bit || boxes[b] & bit) return 0;
		rows[r] |= bit;
		cols[c] |= bit;
		boxes[b] |= bit;
	}

	let count = 0;
	const cells = Int32Array.from(empties);

	// cells[0..depth) are filled; pick the most constrained of the rest (MRV).
	function search(depth: number): boolean {
		if (depth === cells.length) {
			count++;
			return count >= limit;
		}
		let bestI = -1;
		let bestMask = 0;
		let bestN = 10;
		for (let i = depth; i < cells.length; i++) {
			const cell = cells[i];
			const r = (cell / 9) | 0;
			const c = cell % 9;
			const mask = FULL & ~(rows[r] | cols[c] | boxes[((r / 3) | 0) * 3 + ((c / 3) | 0)]);
			const n = popcount(mask);
			if (n < bestN) {
				bestI = i;
				bestMask = mask;
				bestN = n;
				if (n <= 1) break;
			}
		}
		if (bestN === 0) return false;
		const cell = cells[bestI];
		cells[bestI] = cells[depth];
		cells[depth] = cell;
		const r = (cell / 9) | 0;
		const c = cell % 9;
		const b = ((r / 3) | 0) * 3 + ((c / 3) | 0);
		let mask = bestMask;
		let done = false;
		while (mask && !done) {
			const bit = mask & -mask;
			mask ^= bit;
			rows[r] |= bit;
			cols[c] |= bit;
			boxes[b] |= bit;
			done = search(depth + 1);
			rows[r] ^= bit;
			cols[c] ^= bit;
			boxes[b] ^= bit;
		}
		cells[depth] = cells[bestI];
		cells[bestI] = cell;
		return done;
	}

	search(0);
	return count;
}

/** True if `value` already appears in the row, column, or box of cell `index`. */
export function hasConflict(grid: readonly number[], index: number, value: number): boolean {
	const r = (index / 9) | 0;
	const c = index % 9;
	const br = r - (r % 3);
	const bc = c - (c % 3);
	for (let i = 0; i < 9; i++) {
		if (i !== c && grid[r * 9 + i] === value) return true;
		if (i !== r && grid[i * 9 + c] === value) return true;
		const rr = br + ((i / 3) | 0);
		const cc = bc + (i % 3);
		if ((rr !== r || cc !== c) && grid[rr * 9 + cc] === value) return true;
	}
	return false;
}

/** `round(100 × log2(min(before, 1000) / after))`; 1000→500 is worth the same as 10→5. */
export function placementBonus(before: number, after: number): number {
	const b = Math.min(before, SOLUTION_CAP);
	const a = Math.min(after, SOLUTION_CAP);
	if (a <= 0 || b <= a) return 0;
	return Math.round(100 * Math.log2(b / a));
}

/** `round(1000 × clamp((80 − clues) / 63, 0, 1)²)`: 17 clues → 1000, 80 → 0. */
export function endBonus(clues: number): number {
	const share = Math.max(0, Math.min(1, (80 - clues) / 63));
	return Math.round(1000 * share * share);
}

export function formatCount(n: number): string {
	return n >= SOLUTION_CAP ? `${SOLUTION_CAP}+` : String(n);
}
