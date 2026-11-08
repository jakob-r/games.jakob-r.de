/**
 * Client mirror of backend/games_platform/games/fragmentory/board.py, used for the board
 * colours, legal spots and the preview of a pending move. The server stays authoritative.
 *
 * Half-edges are numbered clockwise from the top-left: N = 0 (west half), 1 (east half),
 * E = 2, 3, S = 4 (east half), 5, W = 6 (south half), 7.
 */

export type CardType = 'straight' | 'curve' | 'cross' | 't' | 'end';

export interface Cell {
	type: CardType;
	rot: number;
	owners: (string | null)[];
	placed_by: string | null;
	claimed: number | null;
	move: number;
}

export type Cells = Record<string, Cell>;

export const GRAY = 'gray';

export const CARD_TYPES: Record<CardType, { lines: number[]; areas: number[][] }> = {
	straight: {
		lines: [0, 2],
		areas: [
			[1, 2, 3, 4],
			[5, 6, 7, 0]
		]
	},
	curve: {
		lines: [0, 1],
		areas: [
			[1, 2],
			[3, 4, 5, 6, 7, 0]
		]
	},
	cross: {
		lines: [0, 1, 2, 3],
		areas: [
			[1, 2],
			[3, 4],
			[5, 6],
			[7, 0]
		]
	},
	t: {
		lines: [1, 2, 3],
		areas: [
			[7, 0, 1, 2],
			[3, 4],
			[5, 6]
		]
	},
	end: { lines: [0], areas: [[0, 1, 2, 3, 4, 5, 6, 7]] }
};

export const CARD_ORDER: CardType[] = ['straight', 'curve', 'cross', 't', 'end'];

export const CARD_LABELS: Record<CardType, string> = {
	straight: 'Straight',
	curve: 'Curve',
	cross: 'Cross',
	t: 'T section',
	end: 'Line end'
};

const SIDE_OFFSETS: [number, number][] = [
	[-1, 0],
	[0, 1],
	[1, 0],
	[0, -1]
];

export function cellKey(row: number, col: number): string {
	return `${row},${col}`;
}

export function parseKey(key: string): [number, number] {
	const [r, c] = key.split(',').map(Number);
	return [r, c];
}

export function cardLines(type: CardType, rot: number): Set<number> {
	return new Set(CARD_TYPES[type].lines.map((s) => (s + rot) % 4));
}

export function cardAreas(type: CardType, rot: number): number[][] {
	return CARD_TYPES[type].areas.map((area) => area.map((h) => (h + 2 * rot) % 8));
}

function halfToArea(type: CardType, rot: number): number[] {
	const out = new Array<number>(8).fill(0);
	cardAreas(type, rot).forEach((area, idx) => area.forEach((h) => (out[h] = idx)));
	return out;
}

function neighborHalf(h: number): [number, number, number] {
	const side = Math.floor(h / 2);
	const opposite = (side + 2) % 4;
	const [dr, dc] = SIDE_OFFSETS[side];
	return [dr, dc, 2 * opposite + (h % 2 === 0 ? 1 : 0)];
}

export function boundingBox(
	keys: string[]
): { minR: number; maxR: number; minC: number; maxC: number } | null {
	if (keys.length === 0) return null;
	const coords = keys.map(parseKey);
	const rows = coords.map(([r]) => r);
	const cols = coords.map(([, c]) => c);
	return {
		minR: Math.min(...rows),
		maxR: Math.max(...rows),
		minC: Math.min(...cols),
		maxC: Math.max(...cols)
	};
}

export function boundingArea(cells: Cells): number {
	const box = boundingBox(Object.keys(cells));
	return box ? (box.maxR - box.minR + 1) * (box.maxC - box.minC + 1) : 0;
}

// --------------------------------------------------------------------------- regions

export interface Region {
	id: number;
	areas: [string, number][];
	cards: Set<string>;
	enclosed: boolean;
	ownerCards: Map<string, Set<string>>;
}

export function regionColor(region: Region): string | null {
	if (region.ownerCards.size === 0) return null;
	if (region.ownerCards.size === 1) return [...region.ownerCards.keys()][0];
	return GRAY;
}

export interface RegionMap {
	regions: Region[];
	/** `${cellKey}#${area}` -> region id */
	areaRegion: Map<string, number>;
}

const ref = (key: string, idx: number) => `${key}#${idx}`;

export function computeRegions(cells: Cells): RegionMap {
	const parent = new Map<string, string>();
	const find = (x: string): string => {
		let cur = x;
		while (parent.get(cur) !== cur) {
			const up = parent.get(parent.get(cur)!)!;
			parent.set(cur, up);
			cur = up;
		}
		return cur;
	};
	const lookup = new Map<string, number[]>();
	for (const [key, cell] of Object.entries(cells)) {
		lookup.set(key, halfToArea(cell.type, cell.rot));
		cell.owners.forEach((_, idx) => parent.set(ref(key, idx), ref(key, idx)));
	}
	const open = new Set<string>();
	for (const [key, halves] of lookup) {
		const [r, c] = parseKey(key);
		for (let h = 0; h < 8; h++) {
			const [dr, dc, nh] = neighborHalf(h);
			const nkey = cellKey(r + dr, c + dc);
			const nhalves = lookup.get(nkey);
			if (!nhalves) {
				open.add(ref(key, halves[h]));
				continue;
			}
			const a = find(ref(key, halves[h]));
			const b = find(ref(nkey, nhalves[nh]));
			if (a !== b) parent.set(a, b);
		}
	}
	const roots = new Map<string, number>();
	const regions: Region[] = [];
	const areaRegion = new Map<string, number>();
	for (const id of parent.keys()) {
		const root = find(id);
		let rid = roots.get(root);
		if (rid === undefined) {
			rid = regions.length;
			roots.set(root, rid);
			regions.push({
				id: rid,
				areas: [],
				cards: new Set(),
				enclosed: true,
				ownerCards: new Map()
			});
		}
		const region = regions[rid];
		areaRegion.set(id, rid);
		const [key, idxStr] = id.split('#');
		const idx = Number(idxStr);
		region.areas.push([key, idx]);
		region.cards.add(key);
		if (open.has(id)) region.enclosed = false;
		const owner = cells[key].owners[idx];
		if (owner !== null && owner !== undefined) {
			if (!region.ownerCards.has(owner)) region.ownerCards.set(owner, new Set());
			region.ownerCards.get(owner)!.add(key);
		}
	}
	return { regions, areaRegion };
}

export function regionOf(map: RegionMap, key: string, idx: number): Region {
	return map.regions[map.areaRegion.get(ref(key, idx))!];
}

// --------------------------------------------------------------------------- placement

export function fits(cells: Cells, row: number, col: number, type: CardType, rot: number): boolean {
	if (cells[cellKey(row, col)]) return false;
	const lines = cardLines(type, rot);
	let hasNeighbor = false;
	for (let side = 0; side < 4; side++) {
		const [dr, dc] = SIDE_OFFSETS[side];
		const n = cells[cellKey(row + dr, col + dc)];
		if (!n) continue;
		hasNeighbor = true;
		if (lines.has(side) !== cardLines(n.type, n.rot).has((side + 2) % 4)) return false;
	}
	return hasNeighbor;
}

export function frontier(cells: Cells): [number, number][] {
	const seen = new Set<string>();
	const out: [number, number][] = [];
	for (const key of Object.keys(cells)) {
		const [r, c] = parseKey(key);
		for (const [dr, dc] of SIDE_OFFSETS) {
			const k = cellKey(r + dr, c + dc);
			if (!cells[k] && !seen.has(k)) {
				seen.add(k);
				out.push([r + dr, c + dc]);
			}
		}
	}
	return out;
}

export function claimAllowed(
	cells: Cells,
	regions: RegionMap,
	row: number,
	col: number,
	type: CardType,
	rot: number,
	area: number,
	playerId: string
): boolean {
	for (const h of cardAreas(type, rot)[area]) {
		const [dr, dc, nh] = neighborHalf(h);
		const nkey = cellKey(row + dr, col + dc);
		const n = cells[nkey];
		if (!n) continue;
		const color = regionColor(regionOf(regions, nkey, halfToArea(n.type, n.rot)[nh]));
		if (color !== null && color !== GRAY && color !== playerId) return false;
	}
	return true;
}

export function placeCard(
	cells: Cells,
	row: number,
	col: number,
	type: CardType,
	rot: number,
	claim: number | null,
	playerId: string
): { cells: Cells; penalty: number } | null {
	if (!fits(cells, row, col, type, rot)) return null;
	const before = computeRegions(cells);
	if (claim !== null && !claimAllowed(cells, before, row, col, type, rot, claim, playerId))
		return null;
	const key = cellKey(row, col);
	const next: Cells = {};
	for (const [k, v] of Object.entries(cells)) next[k] = { ...v, owners: [...v.owners] };
	const n = CARD_TYPES[type].areas.length;
	const owners: (string | null)[] = new Array(n).fill(null);
	if (claim !== null) owners[claim] = playerId;
	next[key] = {
		type,
		rot,
		owners,
		placed_by: playerId,
		claimed: claim,
		move: 0
	};

	const after = computeRegions(next);
	const touched = new Set<number>();
	for (let i = 0; i < n; i++) touched.add(after.areaRegion.get(ref(key, i))!);
	for (const rid of [...touched].sort((a, b) => a - b)) {
		const region = after.regions[rid];
		if (region.ownerCards.size === 0) continue;
		const priorGray = region.areas.some(
			([k, i]) => k !== key && regionColor(regionOf(before, k, i)) === GRAY
		);
		const ranked = [...region.ownerCards.entries()]
			.map(([pid, cards]) => [pid, cards.size] as const)
			.sort((a, b) => b[1] - a[1]);
		let winner: string | null = ranked[0][0];
		if (ranked.length > 1 && ranked[0][1] - ranked[1][1] < (priorGray ? 2 : 1)) winner = null;
		if (winner !== null) for (const [k, i] of region.areas) next[k].owners[i] = winner;
	}
	return {
		cells: next,
		penalty: Math.max(0, boundingArea(next) - boundingArea(cells))
	};
}

// --------------------------------------------------------------------------- scoring

export function territoryScores(cells: Cells): Record<string, number> {
	const scores: Record<string, number> = {};
	for (const region of computeRegions(cells).regions) {
		const color = regionColor(region);
		if (color === null || color === GRAY || region.cards.size < 2) continue;
		scores[color] = (scores[color] ?? 0) + region.cards.size * (region.enclosed ? 2 : 1);
	}
	return scores;
}

// --------------------------------------------------------------------------- drawing

/** Area shapes and line paths in the unit square, base orientation (rotate around 0.5, 0.5). */
export const CARD_SHAPES: Record<
	CardType,
	{ areas: string[]; lines: string; labels: [number, number][] }
> = {
	straight: {
		areas: ['M.5 0H1V1H.5Z', 'M0 0H.5V1H0Z'],
		lines: 'M.5 0V1',
		labels: [
			[0.75, 0.5],
			[0.25, 0.5]
		]
	},
	curve: {
		areas: ['M.5 0A.5 .5 0 0 0 1 .5V0Z', 'M0 0H.5A.5 .5 0 0 0 1 .5V1H0Z'],
		lines: 'M.5 0A.5 .5 0 0 0 1 .5',
		labels: [
			[0.84, 0.16],
			[0.36, 0.64]
		]
	},
	cross: {
		areas: ['M.5 0H1V.5H.5Z', 'M.5 .5H1V1H.5Z', 'M0 .5H.5V1H0Z', 'M0 0H.5V.5H0Z'],
		lines: 'M.5 0V1M0 .5H1',
		labels: [
			[0.75, 0.25],
			[0.75, 0.75],
			[0.25, 0.75],
			[0.25, 0.25]
		]
	},
	t: {
		areas: ['M0 0H1V.5H0Z', 'M.5 .5H1V1H.5Z', 'M0 .5H.5V1H0Z'],
		lines: 'M0 .5H1M.5 .5V1',
		labels: [
			[0.5, 0.25],
			[0.75, 0.75],
			[0.25, 0.75]
		]
	},
	end: {
		areas: ['M0 0H1V1H0Z'],
		lines: 'M.5 0V.45',
		labels: [[0.5, 0.72]]
	}
};

/** Label position of an area after rotating the card. */
export function labelPoint(type: CardType, rot: number, area: number): [number, number] {
	let [x, y] = CARD_SHAPES[type].labels[area];
	for (let i = 0; i < rot; i++) [x, y] = [1 - y, x];
	return [x, y];
}
