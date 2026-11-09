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

export interface RoomInvite {
	room_id: string;
	game_slug: string;
	status: 'lobby' | 'playing';
	from: { user_id: number; label: string; color: string };
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
	/** Friends you already invited to that room. */
	roomInvited = $state<number[]>([]);
	/** Friends who already play in that room. */
	roomFriendsHere = $state<number[]>([]);
	/** Room the statuses belong to (set by RoomShell). */
	roomId = '';

	async loadRoom(roomId: string): Promise<void> {
		this.roomId = roomId;
		if (!auth.user) {
			this.roomStatuses = {};
			this.roomInvited = [];
			this.roomFriendsHere = [];
			return;
		}
		const res = await friendsRequest<{
			statuses: Record<string, FriendStatus>;
			invited: number[];
			friends_here: number[];
		}>(`/rooms/${encodeURIComponent(roomId)}`);
		if (this.roomId === roomId) {
			this.roomStatuses = res.data?.statuses ?? {};
			this.roomInvited = res.data?.invited ?? [];
			this.roomFriendsHere = res.data?.friends_here ?? [];
		}
	}

	clearRoom(): void {
		this.roomId = '';
		this.roomStatuses = {};
		this.roomInvited = [];
		this.roomFriendsHere = [];
	}

	/** Invite friends to the current room (push to each; mail if they opted in). */
	async invite(userIds: number[]): Promise<ApiResult<{ invited: number[] }>> {
		const roomId = this.roomId;
		const res = await friendsRequest<{ invited: number[] }>('/invites', 'POST', {
			room_id: roomId,
			user_ids: userIds
		});
		if (res.ok && res.data && this.roomId === roomId) {
			this.roomInvited = [...new Set([...this.roomInvited, ...res.data.invited])];
		}
		return res;
	}

	inbox(): Promise<ApiResult<{ invites: RoomInvite[] }>> {
		return friendsRequest<{ invites: RoomInvite[] }>('/inbox');
	}

	dismissInvite(roomId: string): Promise<ApiResult<unknown>> {
		return friendsRequest(`/invites/${encodeURIComponent(roomId)}`, 'DELETE');
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
