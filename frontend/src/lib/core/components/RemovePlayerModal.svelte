<script lang="ts">
	import { resolvePlayerColor } from '$lib/core/color';
	import type { PlayerInfo } from '$lib/core/ws.svelte';
	import ScribblyBox from './ScribblyBox.svelte';
	import ScribblyButton from './ScribblyButton.svelte';

	let {
		player = null,
		myPlayerId,
		myColor,
		players,
		onConfirm,
		onClose
	}: {
		player: PlayerInfo | null;
		myPlayerId: string;
		myColor: string;
		players: PlayerInfo[];
		onConfirm: (playerId: string) => Promise<unknown> | unknown;
		onClose: () => void;
	} = $props();

	let removing = $state(false);

	let displayColor = $derived(
		player ? resolvePlayerColor(player.player_id, myPlayerId, myColor, players) : '#1a1917'
	);

	async function handleRemove() {
		if (!player || removing) return;
		removing = true;
		try {
			await onConfirm(player.player_id);
			onClose();
		} finally {
			removing = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (!player || removing) return;
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
		aria-labelledby="remove-player-title"
		onclick={(e) => {
			if (e.target === e.currentTarget && !removing) onClose();
		}}
	>
		<ScribblyBox seed={73} class="w-full max-w-sm bg-[#faf8f4] p-5 sm:p-6">
			<h2 id="remove-player-title" class="font-hand text-2xl">Remove player?</h2>
			<p class="mt-2 flex flex-wrap items-center gap-1.5 text-sm text-[#6e6a63]">
				<span>Remove</span>
				<span class="inline-flex items-center gap-1.5 font-semibold" style="color: {displayColor};">
					<span
						class="inline-block h-3 w-3 shrink-0 rounded-full border border-[#1a1917]"
						style="background-color: {displayColor};"
					></span>
					<span>{player.name}</span>
				</span>
				<span>from this room?</span>
			</p>
			<div class="mt-5 flex flex-wrap justify-end gap-2">
				<ScribblyButton onclick={onClose} disabled={removing}>
					Cancel
				</ScribblyButton>
				<ScribblyButton variant="danger" onclick={handleRemove} disabled={removing}>
					{removing ? 'Removing…' : 'Remove Player'}
				</ScribblyButton>
			</div>
		</ScribblyBox>
	</div>
{/if}
