import { auth, type ApiResult } from './auth.svelte';

/** Relation to a co-player who has an account (players without one have no status). */
export type FriendStatus = 'none' | 'outgoing' | 'incoming' | 'friend';

export interface FriendPerson {
	user_id: number;
	name: string;
	color: string;
}

export interface Friend extends FriendPerson {
	/** Name shown to you; duplicates are numbered by when you added them. */
	label: string;
}

export interface FriendsOverview {
	friends: Friend[];
	incoming: FriendPerson[];
	outgoing: FriendPerson[];
}

async function friendsRequest<T>(
	path: string,
	method: 'GET' | 'POST' | 'DELETE' = 'GET',
	body?: unknown
): Promise<ApiResult<T>> {
	try {
		const res = await fetch(`/api/friends${path}`, {
			method,
			headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body)
		});
		const data = await res.json().catch(() => null);
		if (!res.ok) {
			const detail = data?.detail;
			return {
				ok: false,
				data: null,
				error: typeof detail === 'string' ? detail : 'Something went wrong.'
			};
		}
		return { ok: true, data: data as T, error: '' };
	} catch {
		return { ok: false, data: null, error: 'Could not reach the server.' };
	}
}

class FriendsStore {
	/** Friend status per player id for the room you're in (signed-in users only). */
	roomStatuses = $state<Record<string, FriendStatus>>({});
	/** Room the statuses belong to (set by RoomShell). */
	roomId = '';

	async loadRoom(roomId: string): Promise<void> {
		this.roomId = roomId;
		if (!auth.user) {
			this.roomStatuses = {};
			return;
		}
		const res = await friendsRequest<{ statuses: Record<string, FriendStatus> }>(
			`/rooms/${encodeURIComponent(roomId)}`
		);
		if (this.roomId === roomId) this.roomStatuses = res.data?.statuses ?? {};
	}

	clearRoom(): void {
		this.roomId = '';
		this.roomStatuses = {};
	}

	/** Ask a co-player to be friends (accepts their request if they already asked). */
	async request(roomId: string, playerId: string): Promise<ApiResult<{ status: FriendStatus }>> {
		const res = await friendsRequest<{ status: FriendStatus }>('/requests', 'POST', {
			room_id: roomId,
			player_id: playerId
		});
		if (res.ok && res.data && this.roomId === roomId) {
			this.roomStatuses = { ...this.roomStatuses, [playerId]: res.data.status };
		}
		return res;
	}

	overview(): Promise<ApiResult<FriendsOverview>> {
		return friendsRequest<FriendsOverview>('');
	}

	accept(userId: number): Promise<ApiResult<unknown>> {
		return friendsRequest(`/requests/${userId}/accept`, 'POST');
	}

	decline(userId: number): Promise<ApiResult<unknown>> {
		return friendsRequest(`/requests/${userId}/decline`, 'POST');
	}

	remove(userId: number): Promise<ApiResult<unknown>> {
		return friendsRequest(`/${userId}`, 'DELETE');
	}
}

export const friends = new FriendsStore();
