<script lang="ts">
	import { onMount } from 'svelte';
	import { resolvePlayerColor } from '$lib/core/color';
	import type { PlayerInfo } from '$lib/core/ws.svelte';
	import RemovePlayerModal from './RemovePlayerModal.svelte';

	let {
		players,
		hostPlayerId,
		myPlayerId,
		myColor,
		scoringEnabled = true,
		currentPlayerId = null,
		showTurnBadge = false,
		showMultiplier = false,
		statusText = '',
		onRemovePlayer
	}: {
		players: PlayerInfo[];
		hostPlayerId: string;
		myPlayerId: string;
		myColor: string;
		scoringEnabled?: boolean;
		currentPlayerId?: string | null;
		showTurnBadge?: boolean;
		showMultiplier?: boolean;
		statusText?: string;
		onRemovePlayer?: (playerId: string) => Promise<unknown> | unknown;
	} = $props();

	let playerToRemove = $state<PlayerInfo | null>(null);
	let nowTick = $state<number>(Date.now());

	let isHost = $derived(hostPlayerId === myPlayerId);
	let activePlayerToRemove = $derived(
		playerToRemove ? (players.find((p) => p.player_id === playerToRemove?.player_id) ?? null) : null
	);

	onMount(() => {
		if (!showMultiplier) return;
		const timer = setInterval(() => {
			nowTick = Date.now();
		}, 120);
		return () => clearInterval(timer);
	});

	function getMultiplierRemainingRatio(p: PlayerInfo): number {
		if (!p.last_correct_at) return 0;
		const lastMs = new Date(p.last_correct_at).getTime();
		const elapsed = (nowTick - lastMs) / 1000;
		if (elapsed >= 10 || elapsed < -2) return 0;
		return Math.max(0, Math.min(1, (10 - Math.max(0, elapsed)) / 10));
	}

	function getLiveMultiplier(p: PlayerInfo): number {
		const ratio = getMultiplierRemainingRatio(p);
		return ratio > 0 ? p.multiplier : 1;
	}
</script>

<div class="flex flex-wrap items-center justify-between gap-2">
	<div class="flex flex-wrap items-center gap-2">
		{#each players as p (p.player_id)}
			{@const pColor = resolvePlayerColor(p.player_id, myPlayerId, myColor, players)}
			{@const isTurn = showTurnBadge && p.player_id === currentPlayerId}
			{@const canRemove = isHost && p.player_id !== myPlayerId && Boolean(onRemovePlayer)}
			{@const multRatio = showMultiplier ? getMultiplierRemainingRatio(p) : 0}
			{@const liveMult = showMultiplier ? getLiveMultiplier(p) : 1}

			<div
				class="relative flex h-7 items-center gap-2 overflow-hidden rounded-md border-[1.6px] border-[#1a1917] px-2.5 transition
				{showTurnBadge
					? isTurn
						? 'bg-[#faf8f4] shadow-[2.5px_2.5px_0px_#1a1917]'
						: 'bg-[#faf8f4]/70 opacity-85 shadow-[1px_1px_0px_#1a1917]'
					: 'bg-[#faf8f4] shadow-[1.5px_1.5px_0px_#1a1917]'}"
				style={isTurn ? `border-color: ${pColor};` : ''}
			>
				<span
					class="h-2.5 w-2.5 shrink-0 rounded-full border border-[#1a1917]"
					style="background-color: {pColor};"
				></span>

				{#if canRemove}
					<button
						type="button"
						onclick={() => (playerToRemove = p)}
						title="Click to remove {p.name}"
						class="max-w-[96px] cursor-pointer truncate text-xs font-semibold underline-offset-2 hover:underline"
						style="color: {pColor};"
					>
						{p.name}
					</button>
				{:else}
					<span class="max-w-[96px] truncate text-xs font-semibold" style="color: {pColor};">
						{p.name}
					</span>
				{/if}

				{#if scoringEnabled}
					<span class="font-mono-num text-xs font-bold text-[#1a1917]">
						{p.score}
					</span>
					{#if showMultiplier && liveMult > 1.001 && multRatio > 0}
						<span
							class="font-mono-num relative inline-flex h-4 items-center overflow-hidden rounded border border-[#1a1917]/50 bg-[#1a1917]/10 px-1.5 text-[10px] leading-none font-bold text-[#1a1917]"
							title="Streak multiplier ({Math.ceil(multRatio * 10)}s left)"
						>
							<span
								class="pointer-events-none absolute inset-y-0 left-0 opacity-35 transition-all duration-100"
								style="width: {Math.round(multRatio * 100)}%; background-color: {pColor};"
							></span>
							<span class="relative z-10">{Number(liveMult.toFixed(2))}×</span>
						</span>
					{/if}
				{/if}

				{#if isTurn}
					<span
						class="rounded px-1.5 py-0.2 text-[10px] font-bold text-[#faf8f4]"
						style="background-color: {pColor};"
					>
						turn
					</span>
				{/if}
			</div>
		{/each}
	</div>

	{#if statusText}
		<div class="font-mono-num text-xs text-[#6e6a63]">
			{statusText}
		</div>
	{/if}
</div>

<RemovePlayerModal
	player={activePlayerToRemove}
	{myPlayerId}
	{myColor}
	{players}
	onConfirm={(playerId) => onRemovePlayer?.(playerId)}
	onClose={() => (playerToRemove = null)}
/>
