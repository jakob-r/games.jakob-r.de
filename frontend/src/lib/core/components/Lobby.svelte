<script lang="ts">
	import type { Snippet } from 'svelte';
	import { resolvePlayerColor } from '$lib/core/color';
	import type { PlayerInfo } from '$lib/core/ws.svelte';
	import ScribblyBox from './ScribblyBox.svelte';
	import ScribblyButton from './ScribblyButton.svelte';

	let {
		hostPlayerId,
		myPlayerId,
		myColor,
		players,
		onToggleReady,
		onStartGame,
		startLabel = 'Start Game →',
		configSlot
	}: {
		roomId?: string;
		hostPlayerId: string;
		myPlayerId: string;
		myColor: string;
		players: PlayerInfo[];
		onToggleReady: (ready: boolean) => void;
		onStartGame: () => void;
		startLabel?: string;
		configSlot?: Snippet;
	} = $props();

	let me = $derived(players.find((p) => p.player_id === myPlayerId));
	let isHost = $derived(hostPlayerId === myPlayerId);
</script>

<div class="mx-auto w-full max-w-lg space-y-5">
	{#if configSlot}
		<ScribblyBox seed={23} class="bg-[#faf8f4] p-4 sm:p-5">
			{@render configSlot()}
		</ScribblyBox>
	{/if}

	<ScribblyBox seed={37} class="bg-[#faf8f4] p-4 sm:p-5">
		<div class="mb-3 flex items-center justify-between">
			<h2 class="font-hand text-lg">Players ({players.length})</h2>
			<span class="text-xs text-[#6e6a63]">
				{players.filter((p) => p.is_ready).length}/{players.length} ready
			</span>
		</div>

		<ul class="divide-y divide-[#1a1917]/10">
			{#each players as player (player.player_id)}
				{@const displayColor = resolvePlayerColor(player.player_id, myPlayerId, myColor, players)}
				<li class="flex items-center justify-between py-2.5">
					<div class="flex items-center gap-2.5">
						<span
							class="h-4 w-4 rounded-full border-[1.6px] border-[#1a1917]"
							style="background-color: {displayColor};"
						></span>
						<span class="font-medium" style="color: {displayColor};">
							{player.name}
						</span>
						{#if player.player_id === myPlayerId}
							<span class="rounded border border-[#1a1917]/30 px-1.5 py-0.5 text-[10px] uppercase">
								you
							</span>
						{/if}
						{#if player.player_id === hostPlayerId}
							<span class="font-hand text-xs text-[#6e6a63]">(host)</span>
						{/if}
						{#if !player.is_connected}
							<span class="text-xs text-[#6e6a63] italic">offline</span>
						{/if}
					</div>

					<div>
						{#if player.is_ready}
							<span
								class="inline-flex items-center gap-1 rounded-full border border-[#1a1917] bg-[#1a1917] px-2.5 py-0.5 text-xs font-medium text-[#faf8f4]"
							>
								✓ Ready
							</span>
						{:else}
							<span class="font-hand text-xs text-[#6e6a63]">Not ready</span>
						{/if}
					</div>
				</li>
			{/each}
		</ul>

		<div class="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[#1a1917]/15 pt-4">
			<ScribblyButton
				onclick={() => onToggleReady(!(me?.is_ready ?? false))}
				variant={me?.is_ready ? 'default' : 'primary'}
				accentColor={myColor}
			>
				{me?.is_ready ? 'Not Ready' : 'Ready'}
			</ScribblyButton>

			{#if isHost}
				<ScribblyButton onclick={onStartGame} variant="primary" accentColor="#1a1917">
					{startLabel}
				</ScribblyButton>
			{:else}
				<span class="font-hand text-xs text-[#6e6a63]">
					Waiting for host…
				</span>
			{/if}
		</div>
	</ScribblyBox>
</div>
