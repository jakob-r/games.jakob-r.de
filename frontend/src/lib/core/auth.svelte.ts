import { profile } from './profile.svelte';

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
		const res = await fetch(`/api/auth${path}`, {
			method,
			headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body)
		});
		const data = res.status === 204 ? null : await res.json().catch(() => null);
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
		this.setUser(me.data?.user ?? null);
		this.loaded = true;
	}

	/** Adopt the account's identity for play, or drop it again on sign-out. */
	setUser(user: AccountUser | null): void {
		const wasSignedIn = this.user !== null;
		this.user = user;
		if (user) {
			profile.setPlayerId(user.player_id);
			if (user.name) profile.setName(user.name);
		} else if (wasSignedIn) {
			profile.resetAnonymous();
		}
	}

	async logout(): Promise<void> {
		await authRequest('/logout');
		this.setUser(null);
	}
}

export const auth = new AuthStore();
