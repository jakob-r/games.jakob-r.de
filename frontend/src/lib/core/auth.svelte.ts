import { profile } from './profile.svelte';
import { apiUrl, crossOrigin } from './server';

// Cross-origin (native shell) only: the session token the server hands out in the JSON body
// when asked via `X-Session-Transport: token`. Browsers use the HttpOnly cookie and never
// see the token.
const SESSION_TOKEN_KEY = 'games_session_token';

function readSessionToken(): string | null {
	try {
		return localStorage.getItem(SESSION_TOKEN_KEY);
	} catch {
		return null;
	}
}

function writeSessionToken(token: string | null): void {
	try {
		if (token) localStorage.setItem(SESSION_TOKEN_KEY, token);
		else localStorage.removeItem(SESSION_TOKEN_KEY);
	} catch {
		// storage unavailable: the session just won't survive a restart
	}
}

function authHeaders(hasBody: boolean): Record<string, string> {
	const headers: Record<string, string> = {};
	if (hasBody) headers['Content-Type'] = 'application/json';
	if (crossOrigin) {
		headers['X-Session-Transport'] = 'token';
		const token = readSessionToken();
		if (token) headers['Authorization'] = `Bearer ${token}`;
	}
	return headers;
}

export interface AccountUser {
	id: number;
	email: string;
	name: string;
	player_id: string;
	email_verified: boolean;
	has_password: boolean;
}

export interface ApiResult<T> {
	ok: boolean;
	data: T | null;
	error: string;
}

export async function authRequest<T = unknown>(
	path: string,
	body?: unknown,
	method: 'GET' | 'POST' = 'POST'
): Promise<ApiResult<T>> {
	try {
		const res = await fetch(apiUrl(`/api/auth${path}`), {
			method,
			headers: authHeaders(body !== undefined),
			body: body === undefined ? undefined : JSON.stringify(body)
		});
		const data = res.status === 204 ? null : await res.json().catch(() => null);
		if (crossOrigin && typeof data?.session_token === 'string') {
			writeSessionToken(data.session_token);
			delete data.session_token;
		}
		if (!res.ok) {
			const detail = data?.detail;
			const error =
				typeof detail === 'string'
					? detail
					: Array.isArray(detail)
						? 'Please check your input.'
						: 'Something went wrong.';
			return { ok: false, data: null, error };
		}
		return { ok: true, data: data as T, error: '' };
	} catch {
		return { ok: false, data: null, error: 'Could not reach the server.' };
	}
}

class AuthStore {
	user = $state<AccountUser | null>(null);
	loaded = $state(false);
	googleEnabled = $state(false);

	async load(): Promise<void> {
		const [me, providers] = await Promise.all([
			authRequest<{ user: AccountUser | null }>('/me', undefined, 'GET'),
			authRequest<{ google: boolean }>('/providers', undefined, 'GET')
		]);
		this.googleEnabled = providers.data?.google ?? false;
		// Only a real answer signs out (and drops a stored token); a network error keeps it.
		if (me.ok) this.setUser(me.data?.user ?? null);
		this.loaded = true;
	}

	/** Adopt the account's identity for play, or drop it again on sign-out. */
	setUser(user: AccountUser | null): void {
		const wasSignedIn = this.user !== null;
		this.user = user;
		if (user) {
			profile.setPlayerId(user.player_id);
			if (user.name) profile.setName(user.name);
		} else {
			// Signed out, account deleted or the token expired: drop a stale token.
			writeSessionToken(null);
			if (wasSignedIn) profile.resetAnonymous();
		}
	}

	async logout(): Promise<void> {
		await authRequest('/logout');
		this.setUser(null);
	}
}

export const auth = new AuthStore();
