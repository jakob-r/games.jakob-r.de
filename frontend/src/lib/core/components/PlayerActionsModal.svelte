<script lang="ts">
	import { resolvePlayerColor } from '$lib/core/color';
	import { friends } from '$lib/core/friends.svelte';
	import type { PlayerInfo } from '$lib/core/ws.svelte';
	import ScribblyBox from './ScribblyBox.svelte';
	import ScribblyButton from './ScribblyButton.svelte';

	/**
	 * Opens when you click a co-player's name: add them as a friend (both need an
	 * account) and, for the room's host, remove them from the room.
	 */
	let {
		player = null,
		myPlayerId,
		myColor,
		players,
		canRemove = false,
		onRemove,
		onClose
	}: {
		player: PlayerInfo | null;
		myPlayerId: string;
		myColor: string;
		players: PlayerInfo[];
		canRemove?: boolean;
		onRemove?: (playerId: string) => Promise<unknown> | unknown;
		onClose: () => void;
	} = $props();

	let busy = $state(false);
	let removing = $state(false);
	let error = $state('');

	let displayColor = $derived(
		player ? resolvePlayerColor(player.player_id, myPlayerId, myColor, players) : '#1a1917'
	);
	let friendStatus = $derived(player ? friends.roomStatuses[player.player_id] : undefined);

	$effect(() => {
		if (!player) error = '';
	});

	async function handleRemove() {
		if (!player || busy || !onRemove) return;
		busy = removing = true;
		try {
			await onRemove(player.player_id);
			onClose();
		} finally {
			busy = removing = false;
		}
	}

	async function handleFriend() {
		if (!player || busy) return;
		busy = true;
		error = '';
		try {
			const res = await friends.request(friends.roomId, player.player_id);
			if (!res.ok) error = res.error;
		} finally {
			busy = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (!player || busy) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			onClose();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if player}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-[#1a1917]/40 p-4"
		role="dialog"
		tabindex="-1"
		aria-modal="true"
		aria-labelledby="player-actions-title"
		onclick={(e) => {
			if (e.target === e.currentTarget && !busy) onClose();
		}}
	>
		<ScribblyBox seed={73} class="w-full max-w-sm bg-[#faf8f4] p-5 sm:p-6">
			<h2
				id="player-actions-title"
				class="font-hand flex items-center gap-2 text-2xl"
				style="color: {displayColor};"
			>
				<span
					class="inline-block h-3.5 w-3.5 shrink-0 rounded-full border border-[#1a1917]"
					style="background-color: {displayColor};"
				></span>
				<span class="truncate">{player.name}</span>
			</h2>

			{#if friendStatus}
				<div class="mt-4 space-y-1.5">
					{#if friendStatus === 'friend'}
						<p class="text-sm">You are friends.</p>
					{:else if friendStatus === 'outgoing'}
						<p class="text-sm">Friend request sent.</p>
					{:else}
						<ScribblyButton onclick={handleFriend} disabled={busy}>
							{friendStatus === 'incoming' ? 'Accept friend request' : 'Add friend'}
						</ScribblyButton>
						{#if friendStatus === 'incoming'}
							<p class="text-xs text-[#6e6a63]">{player.name} asked to be friends.</p>
						{/if}
					{/if}
					{#if error}
						<p class="text-xs font-medium text-[#dc2626]" role="alert">{error}</p>
					{/if}
				</div>
			{/if}

			{#if canRemove}
				<div class="mt-4 space-y-2 border-t border-[#1a1917]/15 pt-4">
					<p class="text-sm text-[#6e6a63]">Remove {player.name} from this room?</p>
					<ScribblyButton variant="danger" onclick={handleRemove} disabled={busy}>
						{removing ? 'Removing…' : 'Remove Player'}
					</ScribblyButton>
				</div>
			{/if}

			<div class="mt-5 flex justify-end">
				<ScribblyButton onclick={onClose} disabled={busy}>Close</ScribblyButton>
			</div>
		</ScribblyBox>
	</div>
{/if}
