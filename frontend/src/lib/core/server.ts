/**
 * Where the backend lives.
 *
 * In the browser the frontend is served by the backend itself, so every URL stays
 * relative / same-origin. A native shell (e.g. Capacitor, where the page origin is
 * `capacitor://localhost`) sets `VITE_SERVER_ORIGIN=https://games.jakob-r.de` at build
 * time so API calls, WebSockets and share links point at the real server.
 */
const SERVER_ORIGIN: string = (import.meta.env.VITE_SERVER_ORIGIN ?? '').replace(/\/+$/, '');

/**
 * True when the page runs on a different origin than the API (native shell). The
 * SameSite=Lax session cookie does not work there, so auth uses a bearer token instead.
 */
export const crossOrigin = SERVER_ORIGIN !== '';

/** Absolute URL for an API path like `/api/rooms` (relative when same-origin). */
export function apiUrl(path: string): string {
	return `${SERVER_ORIGIN}${path}`;
}

/** WebSocket URL for a path like `/ws/sudoku/abc`. */
export function wsUrl(path: string): string {
	const origin = SERVER_ORIGIN || window.location.origin;
	return `${origin.replace(/^http/, 'ws')}${path}`;
}

/** Public, shareable URL for an app path (what other players open in their browser). */
export function publicUrl(path: string): string {
	return `${SERVER_ORIGIN || window.location.origin}${path}`;
}

/** Shareable URL of the page currently open. */
export function currentPublicUrl(): string {
	const { pathname, search, hash } = window.location;
	return publicUrl(`${pathname}${search}${hash}`);
}
