// Client-side mirror of backend/games_platform/games/spellsprawl/board.py, used only for the
// live preview while composing. The server stays the authority on validity and scoring.

export type Direction = 'right' | 'down';
export type Coord = [number, number];

export interface Cell {
	letter: string;
	player_id: string;
	move: number;
}

export type Cells = Record<string, Cell>;

export interface FormedWord {
	word: string;
	positions: Coord[];
	/** Indices of letters that were already on the grid. */
	existing: number[];
}

export interface Preview {
	main: FormedWord;
	cross: FormedWord[];
	points: number;
	direction: Direction;
}

export const cellKey = (row: number, col: number): string => `${row},${col}`;

export function parseKey(key: string): Coord {
	const [r, c] = key.split(',').map(Number);
	return [r, c];
}

export const step = (direction: Direction): Coord => (direction === 'right' ? [0, 1] : [1, 0]);
const other = (direction: Direction): Direction => (direction === 'right' ? 'down' : 'right');

/** Fold typed text to the A–Z letters the grid accepts (accents stripped, ß → SS). */
export function foldLetters(text: string): string {
	return text
		.replace(/ß/g, 'ss')
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.toUpperCase()
		.replace(/[^A-Z]/g, '');
}

function run(
	cells: Cells,
	pending: Map<string, string>,
	start: Coord,
	direction: Direction
): FormedWord {
	const [dr, dc] = step(direction);
	const has = (r: number, c: number) => cellKey(r, c) in cells || pending.has(cellKey(r, c));
	let [r, c] = start;
	while (has(r - dr, c - dc)) {
		r -= dr;
		c -= dc;
	}
	const positions: Coord[] = [];
	const existing: number[] = [];
	let word = '';
	while (has(r, c)) {
		const key = cellKey(r, c);
		const placed = pending.get(key);
		if (placed !== undefined) {
			word += placed;
		} else {
			existing.push(positions.length);
			word += cells[key].letter;
		}
		positions.push([r, c]);
		r += dr;
		c += dc;
	}
	return { word, positions, existing };
}

function wordPoints(word: FormedWord, scores: Record<string, number>): number {
	return word.existing.reduce((sum, i) => sum + (scores[word.word[i]] ?? 1), 0);
}

/** Returns the formed words and projected points, or a rejection reason. */
export function previewPlacement(
	cells: Cells,
	pending: Map<string, string>,
	direction: Direction,
	scores: Record<string, number>
): Preview | { reason: string } {
	if (pending.size === 0) return { reason: 'empty' };
	const coords = [...pending.keys()].map(parseKey);
	const rows = new Set(coords.map(([r]) => r));
	const cols = new Set(coords.map(([, c]) => c));
	if (pending.size > 1) {
		if (rows.size === 1) direction = 'right';
		else if (cols.size === 1) direction = 'down';
		else return { reason: 'not_in_line' };
	}
	const first = coords.reduce((a, b) => (a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]) ? a : b));
	let main = run(cells, pending, first, direction);
	if (pending.size === 1 && main.word.length < 2) {
		direction = other(direction);
		main = run(cells, pending, first, direction);
	}
	const onMain = new Set(main.positions.map(([r, c]) => cellKey(r, c)));
	if (coords.some(([r, c]) => !onMain.has(cellKey(r, c)))) return { reason: 'gap' };
	if (main.word.length < 2) return { reason: 'too_short' };

	const cross: FormedWord[] = [];
	for (const [r, c] of main.positions) {
		if (!pending.has(cellKey(r, c))) continue;
		const w = run(cells, pending, [r, c], other(direction));
		if (w.word.length >= 2) cross.push(w);
	}
	const points = wordPoints(main, scores) + cross.reduce((s, w) => s + wordPoints(w, scores), 0);
	return { main, cross, points, direction };
}
