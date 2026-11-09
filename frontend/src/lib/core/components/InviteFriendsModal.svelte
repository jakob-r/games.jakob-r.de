<script lang="ts">
	import { friends, type Friend } from '$lib/core/friends.svelte';
	import ScribblyBox from './ScribblyBox.svelte';
	import ScribblyButton from './ScribblyButton.svelte';

	/** Pick friends to invite to the current room; they get a push (and a mail if they opted in). */
	let { open = false, onClose }: { open?: boolean; onClose: () => void } = $props();

	let list = $state<Friend[] | null>(null);
	let selected = $state<number[]>([]);
	let sending = $state(false);
	let message = $state('');
	let error = $state('');

	$effect(() => {
		if (!open) return;
		list = null;
		selected = [];
		message = error = '';
		void friends.overview().then((res) => {
			if (res.ok && res.data) list = res.data.friends;
			else error = res.error;
		});
	});

	function availability(friend: Friend): 'here' | 'invited' | null {
		if (friends.roomFriendsHere.includes(friend.user_id)) return 'here';
		if (friends.roomInvited.includes(friend.user_id)) return 'invited';
		return null;
	}

	function toggle(id: number) {
		selected = selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id];
	}

	async function send() {
		if (!selected.length || sending) return;
		sending = true;
		error = '';
		try {
			const res = await friends.invite(selected);
			if (!res.ok) {
				error = res.error;
				return;
			}
			const n = res.data?.invited.length ?? 0;
			message = n === 1 ? 'Invite sent.' : `${n} invites sent.`;
			selected = [];
		} finally {
			sending = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (open && !sending && e.key === 'Escape') {
			e.preventDefault();
			onClose();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-[#1a1917]/40 p-4"
		role="dialog"
		tabindex="-1"
		aria-modal="true"
		aria-labelledby="invite-friends-title"
		onclick={(e) => {
			if (e.target === e.currentTarget && !sending) onClose();
		}}
	>
		<ScribblyBox seed={59} class="w-full max-w-sm bg-[#faf8f4] p-5 sm:p-6">
			<h2 id="invite-friends-title" class="font-hand text-2xl">Invite friends</h2>

			{#if list === null && !error}
				<p class="mt-3 text-sm text-[#6e6a63]">Loading…</p>
			{:else if list && list.length === 0}
				<p class="mt-3 text-sm text-[#6e6a63]">
					No friends yet. Tap a co-player's name in a game to add them.
				</p>
			{:else if list}
				<ul class="mt-3 max-h-72 space-y-1 overflow-y-auto">
					{#each list as friend (friend.user_id)}
						{@const state = availability(friend)}
						<li>
							<label
								class="flex items-center gap-2.5 rounded px-1 py-1.5 text-sm {state
									? 'text-[#6e6a63]'
									: 'cursor-pointer hover:bg-[#1a1917]/5'}"
							>
								<input
									type="checkbox"
									class="h-4 w-4 accent-[#1a1917]"
									checked={state !== null || selected.includes(friend.user_id)}
									disabled={state !== null || sending}
									onchange={() => toggle(friend.user_id)}
								/>
								<span
									class="h-3 w-3 shrink-0 rounded-full border border-[#1a1917]"
									style="background-color: {friend.color || '#faf8f4'};"
								></span>
								<span class="flex-1 truncate font-medium">{friend.label}</span>
								{#if state === 'here'}
									<span class="text-xs">in this room</span>
								{:else if state === 'invited'}
									<span class="text-xs">invited</span>
								{/if}
							</label>
						</li>
					{/each}
				</ul>
			{/if}

			{#if error}
				<p class="mt-2 text-xs font-medium text-[#dc2626]" role="alert">{error}</p>
			{/if}
			{#if message}
				<p class="mt-2 text-xs font-medium text-[#15803d]" role="status">{message}</p>
			{/if}

			<div class="mt-5 flex flex-wrap justify-end gap-2">
				<ScribblyButton onclick={onClose} disabled={sending}>Close</ScribblyButton>
				{#if list && list.length > 0}
					<ScribblyButton variant="primary" onclick={send} disabled={!selected.length || sending}>
						{sending ? 'Sending…' : 'Invite'}
					</ScribblyButton>
				{/if}
			</div>
		</ScribblyBox>
	</div>
{/if}
