/**
 * Perceptual OKLCH color math and `opponent_color(my_color, their_color)` implementation.
 *
 * Ensures every player's chosen color is visible against the paper background and
 * perceptually distinct from the local player's color (`my_color`).
 */

export interface Oklch {
	l: number; // 0..1
	c: number; // 0..0.4
	h: number; // 0..360
}

export const PRESET_PLAYER_COLORS: { name: string; hex: string }[] = [
	{ name: 'Cobalt Ink', hex: '#2563eb' },
	{ name: 'Vermilion', hex: '#dc2626' },
	{ name: 'Forest Moss', hex: '#15803d' },
	{ name: 'Plum Sketch', hex: '#7e22ce' },
	{ name: 'Amber Ochre', hex: '#b45309' },
	{ name: 'Teal Nib', hex: '#0f766e' },
	{ name: 'Magenta Pen', hex: '#be185d' },
	{ name: 'Indigo Quill', hex: '#4338ca' }
];

function srgbToLinear(channel: number): number {
	const c = channel / 255;
	return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function linearToSrgb(c: number): number {
	const clamped = Math.max(0, Math.min(1, c));
	const v =
		clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
	return Math.round(v * 255);
}

export function hexToRgb(hex: string): [number, number, number] {
	const clean = hex.trim().replace(/^#/, '');
	if (clean.length === 3) {
		const r = parseInt(clean[0] + clean[0], 16);
		const g = parseInt(clean[1] + clean[1], 16);
		const b = parseInt(clean[2] + clean[2], 16);
		return [isNaN(r) ? 37 : r, isNaN(g) ? 99 : g, isNaN(b) ? 235 : b];
	}
	const r = parseInt(clean.slice(0, 2), 16);
	const g = parseInt(clean.slice(2, 4), 16);
	const b = parseInt(clean.slice(4, 6), 16);
	return [isNaN(r) ? 37 : r, isNaN(g) ? 99 : g, isNaN(b) ? 235 : b];
}

export function rgbToHex(r: number, g: number, b: number): string {
	const toHex = (n: number) => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0');
	return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

export function hexToOklch(hex: string): Oklch {
	const [sr, sg, sb] = hexToRgb(hex);
	const r = srgbToLinear(sr);
	const g = srgbToLinear(sg);
	const b = srgbToLinear(sb);

	const l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b;
	const m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b;
	const s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b;

	const l_ = Math.cbrt(l);
	const m_ = Math.cbrt(m);
	const s_ = Math.cbrt(s);

	const L = 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_;
	const A = 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_;
	const B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_;

	const C = Math.sqrt(A * A + B * B);
	let h = (Math.atan2(B, A) * 180) / Math.PI;
	if (h < 0) h += 360;

	return { l: L, c: C, h };
}

export function oklchToHex({ l, c, h }: Oklch): string {
	const hRad = (h * Math.PI) / 180;
	const A = c * Math.cos(hRad);
	const B = c * Math.sin(hRad);

	const l_ = l + 0.3963377774 * A + 0.2158037573 * B;
	const m_ = l - 0.1055613458 * A - 0.0638541728 * B;
	const s_ = l - 0.0894841775 * A - 1.291485548 * B;

	const lCube = l_ * l_ * l_;
	const mCube = m_ * m_ * m_;
	const sCube = s_ * s_ * s_;

	const r = +4.0767416621 * lCube - 3.3077115913 * mCube + 0.2309699292 * sCube;
	const g = -1.2684380046 * lCube + 2.6097574011 * mCube - 0.3413193965 * sCube;
	const b = -0.0041960863 * lCube - 0.7034186147 * mCube + 1.707614701 * sCube;

	return rgbToHex(linearToSrgb(r), linearToSrgb(g), linearToSrgb(b));
}

function hueDistance(h1: number, h2: number): number {
	const diff = Math.abs(h1 - h2) % 360;
	return diff > 180 ? 360 - diff : diff;
}

export function perceptualDistance(a: Oklch, b: Oklch): number {
	const hRad1 = (a.h * Math.PI) / 180;
	const hRad2 = (b.h * Math.PI) / 180;
	const da = a.c * Math.cos(hRad1) - b.c * Math.cos(hRad2);
	const db = a.c * Math.sin(hRad1) - b.c * Math.sin(hRad2);
	const dl = a.l - b.l;
	return Math.sqrt(dl * dl + da * da + db * db);
}

/**
 * Compute an opponent color that is not too similar to `my_color` (and adjusted from `their_color`
 * when needed), as specified in `idea.md`:
 *
 * `opponent_color(my_color, their_color)` returns a color that is readable on the paper
 * canvas and perceptually distinct from `my_color`.
 */
export function opponent_color(my_color: string, their_color: string): string {
	const mine = hexToOklch(my_color);
	const theirs = hexToOklch(their_color);

	// Ensure readable lightness and vivid ink chroma on light paper (#faf8f4)
	const safeL = Math.max(0.42, Math.min(0.62, theirs.l));
	const safeC = Math.max(0.14, Math.min(0.24, theirs.c));

	const dist = perceptualDistance(mine, { l: safeL, c: safeC, h: theirs.h });
	const hDiff = hueDistance(mine.h, theirs.h);

	// If their color is already perceptually distinct from my_color, keep their hue!
	if (dist >= 0.14 && hDiff >= 42) {
		return oklchToHex({ l: safeL, c: safeC, h: theirs.h });
	}

	// Otherwise, shift their hue using the golden-angle offset (137.5 deg) so it is
	// guaranteed to be distinct from both `my_color` and the original `their_color`.
	let candidateHue = (theirs.h + 137.5) % 360;
	if (hueDistance(mine.h, candidateHue) < 48) {
		candidateHue = (mine.h + 137.5) % 360;
	}

	const altL = mine.l > 0.52 ? 0.45 : 0.56;
	return oklchToHex({
		l: altL,
		c: Math.max(0.16, safeC),
		h: candidateHue
	});
}

/**
 * Resolve display color for any player ID relative to the local user.
 */
export function resolvePlayerColor(
	targetPlayerId: string | null | undefined,
	myPlayerId: string,
	myColor: string,
	players: { player_id: string; color: string }[]
): string {
	if (!targetPlayerId) return '#1a1917';
	if (targetPlayerId === myPlayerId) return myColor;
	const found = players.find((p) => p.player_id === targetPlayerId);
	if (!found) return opponent_color(myColor, '#dc2626');
	return opponent_color(myColor, found.color);
}
