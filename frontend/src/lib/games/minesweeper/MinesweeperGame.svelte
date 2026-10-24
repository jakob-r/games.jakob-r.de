<script lang="ts">
	import { onMount } from 'svelte';
	import { resolvePlayerColor } from '$lib/core/color';
	import PlayerBar from '$lib/core/components/PlayerBar.svelte';
	import RoomShell from '$lib/core/components/RoomShell.svelte';
	import ScribblyBox from '$lib/core/components/ScribblyBox.svelte';
	import ScribblyButton from '$lib/core/components/ScribblyButton.svelte';
	import { profile } from '$lib/core/profile.svelte';
	import { RoomSocketClient, type PlayerInfo, type ServerEvent } from '$lib/core/ws.svelte';

	let { roomId }: { roomId: string } = $props();

	type CellStatus = 'hidden' | 'revealed' | 'flagged' | 'mine_revealed';

	interface MineCell {
		status: CellStatus;
		adjacent?: number;
		flag_owner_id?: string | null;
		revealed_by?: string | null;
	}

	interface MinesPublicState {
		width?: number;
		height?: number;
		mine_count?: number;
		cells?: MineCell[][];
		safe_revealed?: number;
		safe_total?: number;
		flagged_count?: number;
		mines_hit?: number;
		difficulty?: string;
		scoring_enabled?: boolean;
	}

	interface FxItem {
		id: number;
		kind: 'boom' | 'score' | 'challenge';
		row: number;
		col: number;
		text: string;
		color?: string;
	}

	const client = new RoomSocketClient();
	const DIFFICULTIES: ('easy' | 'medium' | 'hard')[] = ['easy', 'medium', 'hard'];
	const LONG_PRESS_MS = 420;

	let digMode = $state<'dig' | 'flag'>('dig');
	let fxItems = $state<FxItem[]>([]);
	let challengeTarget = $state<{ row: number; col: number; ownerId: string } | null>(null);
	let fxCounter = 0;

	let longPressTimer: ReturnType<typeof setTimeout> | null = null;
	let longPressFired = false;

	let room = $derived(client.room);
	let gameState = $derived((room?.state ?? {}) as MinesPublicState);
	let cells = $derived(gameState.cells ?? []);
	let width = $derived(gameState.width ?? 9);
	let height = $derived(gameState.height ?? 9);
	let players = $derived<PlayerInfo[]>(room?.players ?? []);
	let isHost = $derived(room?.host_player_id === profile.playerId);
	let scoringEnabled = $derived(Boolean(room?.config?.scoring_enabled ?? true));
	let currentDifficulty = $derived(String(room?.config?.difficulty ?? 'easy'));
	let mineCount = $derived(gameState.mine_count ?? 10);
	let flaggedCount = $derived(gameState.flagged_count ?? 0);
	let safeRevealed = $derived(gameState.safe_revealed ?? 0);
	let safeTotal = $derived(gameState.safe_total ?? width * height - mineCount);
	let subtitleItems = $derived(
		room?.status === 'playing' || room?.status === 'finished'
			? [currentDifficulty, `${flaggedCount}/${mineCount} flags`]
			: []
	);

	let cellSize = $derived(width >= 24 ? 22 : width >= 14 ? 28 : 34);

	function pushFx(item: Omit<FxItem, 'id'>, ms = 1100) {
		const id = ++fxCounter;
		fxItems = [...fxItems, { ...item, id }];
		setTimeout(() => {
			fxItems = fxItems.filter((f) => f.id !== id);
		}, ms);
	}

	onMount(() => {
		profile.init();
		client.connect({
			gameSlug: 'minesweeper',
			roomId,
			playerId: profile.playerId,
			name: profile.name,
			color: profile.primaryColor
		});

		const unsub = client.onEvent((ev: ServerEvent) => {
			if (ev.type === 'mine_hit') {
				pushFx(
					{
						kind: 'boom',
						row: ev.row,
						col: ev.col,
						text: scoringEnabled ? `${ev.points_delta}` : 'BOOM',
						color: '#dc2626'
					},
					1400
				);
			} else if (ev.type === 'cell_revealed') {
				if (scoringEnabled && ev.points_delta !== 0) {
					pushFx({
						kind: 'score',
						row: ev.row,
						col: ev.col,
						text: `+${ev.points_delta}`,
						color: resolvePlayerColor(
							ev.player_id,
							profile.playerId,
							profile.primaryColor,
							players
						)
					});
				}
			} else if (ev.type === 'flag_placed' || ev.type === 'flag_removed') {
				if (scoringEnabled && ev.points_delta !== 0) {
					const sign = ev.points_delta > 0 ? '+' : '';
					pushFx({
						kind: 'score',
						row: ev.row,
						col: ev.col,
						text: `${sign}${ev.points_delta}`,
						color: resolvePlayerColor(
							ev.player_id,
							profile.playerId,
							profile.primaryColor,
							players
						)
					});
				}
			} else if (ev.type === 'flag_challenged') {
				const sign = ev.challenger_delta > 0 ? '+' : '';
				pushFx(
					{
						kind: 'challenge',
						row: ev.row,
						col: ev.col,
						text: ev.was_correct
							? `Wrong call ${sign}${ev.challenger_delta}`
							: `Caught! ${sign}${ev.challenger_delta}`,
						color: ev.was_correct ? '#dc2626' : '#15803d'
					},
					1600
				);
			}
		});

		return () => {
			clearLongPress();
			unsub();
			client.disconnect();
		};
	});

	function clearLongPress() {
		if (longPressTimer) {
			clearTimeout(longPressTimer);
			longPressTimer = null;
		}
	}

	function handleCellPointerDown(r: number, c: number, e: PointerEvent) {
		if (room?.status !== 'playing') return;
		if (e.pointerType === 'mouse' && e.button === 2) return;
		longPressFired = false;
		clearLongPress();
		longPressTimer = setTimeout(() => {
			longPressFired = true;
			const cell = cells[r]?.[c];
			if (!cell || cell.status !== 'hidden') return;
			client.sendAction({ type: 'flag', row: r, col: c });
			client.sendCursor(r, c);
		}, LONG_PRESS_MS);
	}

	function handleCellPointerUp(r: number, c: number) {
		clearLongPress();
		if (longPressFired) return;
		onCellTap(r, c);
	}

	function handleCellPointerCancel() {
		clearLongPress();
	}

	function onCellTap(r: number, c: number) {
		if (room?.status !== 'playing') return;
		const cell = cells[r]?.[c];
		if (!cell) return;
		client.sendCursor(r, c);

		if (cell.status === 'flagged') {
			const owner = cell.flag_owner_id;
			if (owner === profile.playerId) {
				client.sendAction({ type: 'unflag', row: r, col: c });
			} else if (owner) {
				challengeTarget = { row: r, col: c, ownerId: owner };
			}
			return;
		}

		if (cell.status !== 'hidden') return;

		if (digMode === 'flag') {
			client.sendAction({ type: 'flag', row: r, col: c });
		} else {
			client.sendAction({ type: 'reveal', row: r, col: c });
		}
	}

	function handleContextMenu(r: number, c: number, e: MouseEvent) {
		e.preventDefault();
		if (room?.status !== 'playing') return;
		const cell = cells[r]?.[c];
		if (!cell) return;
		client.sendCursor(r, c);
		if (cell.status === 'hidden') {
			client.sendAction({ type: 'flag', row: r, col: c });
		} else if (cell.status === 'flagged' && cell.flag_owner_id === profile.playerId) {
			client.sendAction({ type: 'unflag', row: r, col: c });
		}
	}

	function confirmChallenge() {
		if (!challengeTarget) return;
		client.sendAction({
			type: 'challenge_flag',
			row: challengeTarget.row,
			col: challengeTarget.col
		});
		challengeTarget = null;
	}

	function flagColor(ownerId: string | null | undefined): string {
		if (!ownerId) return '#1a1917';
		return resolvePlayerColor(ownerId, profile.playerId, profile.primaryColor, players);
	}

	function ownerName(ownerId: string): string {
		return players.find((p) => p.player_id === ownerId)?.name ?? 'Player';
	}
</script>

<RoomShell
	{client}
	{roomId}
	title="Co-op Minesweeper"
	{subtitleItems}
	maxWidthClass="max-w-4xl"
>
	{#snippet configSlot()}
		<div class="space-y-4">
			{#if !isHost}
				<div class="text-right font-hand text-xs text-[#6e6a63]">Configured by host</div>
			{/if}

			<div>
				<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">
					Difficulty
				</span>
				<div class="grid grid-cols-3 gap-2">
					{#each DIFFICULTIES as diff}
						<button
							type="button"
							disabled={!isHost}
							onclick={() => client.updateConfig({ difficulty: diff })}
							class="cursor-pointer rounded border-[1.6px] border-[#1a1917] py-1.5 text-xs font-semibold capitalize transition disabled:cursor-not-allowed
							{currentDifficulty === diff
								? 'bg-[#1a1917] text-[#faf8f4] shadow-[2px_2px_0px_#6e6a63]'
								: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
						>
							{diff}
						</button>
					{/each}
				</div>
				<p class="mt-1.5 text-[11px] text-[#6e6a63]">
					{#if currentDifficulty === 'easy'}9×9 · 10 mines
					{:else if currentDifficulty === 'medium'}16×16 · 40 mines
					{:else}30×16 · 99 mines{/if}
				</p>
			</div>

			<div class="flex items-center justify-between border-t border-[#1a1917]/10 pt-3">
				<div>
					<div class="text-sm font-medium">Scoring</div>
					<p class="text-xs text-[#6e6a63]">
						+1 dig · +2 flag · −3 unflag · ±5 challenge · −10 mine
					</p>
				</div>
				<button
					type="button"
					disabled={!isHost}
					onclick={() => client.updateConfig({ scoring_enabled: !scoringEnabled })}
					class="cursor-pointer rounded-full border-[1.6px] border-[#1a1917] px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed
					{scoringEnabled ? 'bg-[#1a1917] text-[#faf8f4]' : 'bg-[#faf8f4] text-[#6e6a63]'}"
				>
					{scoringEnabled ? 'ON' : 'OFF'}
				</button>
			</div>
		</div>
	{/snippet}

	<div class="flex flex-1 flex-col gap-3">
		<PlayerBar
			{players}
			hostPlayerId={room?.host_player_id ?? ''}
			myPlayerId={profile.playerId}
			myColor={profile.primaryColor}
			{scoringEnabled}
			statusText="{safeRevealed}/{safeTotal} clear"
			onRemovePlayer={(id) => client.removePlayer(id)}
		/>

		{#if room?.status === 'playing'}
			<div class="flex items-center gap-2">
				<button
					type="button"
					onclick={() => (digMode = 'dig')}
					class="cursor-pointer rounded border-[1.6px] border-[#1a1917] px-3 py-1.5 text-xs font-semibold transition
					{digMode === 'dig'
						? 'bg-[#1a1917] text-[#faf8f4]'
						: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
				>
					Dig
				</button>
				<button
					type="button"
					onclick={() => (digMode = 'flag')}
					class="cursor-pointer rounded border-[1.6px] border-[#1a1917] px-3 py-1.5 text-xs font-semibold transition
					{digMode === 'flag'
						? 'bg-[#1a1917] text-[#faf8f4]'
						: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
				>
					Flag
				</button>
				<span class="text-[11px] text-[#6e6a63]">
					Long-press or right-click to flag · tap opponent flag to challenge
				</span>
			</div>
		{/if}

		{#if room?.status === 'finished'}
			<ScribblyBox seed={55} class="bg-[#faf8f4] p-4 text-center">
				<p class="font-hand text-xl">Field cleared!</p>
				<p class="mt-1 text-sm text-[#6e6a63]">
					All safe cells revealed or every mine secured.
				</p>
				<div class="mt-3 flex justify-center gap-2">
					{#if isHost}
						<ScribblyButton onclick={() => client.returnToLobby()}>
							Back to Lobby
						</ScribblyButton>
					{/if}
				</div>
			</ScribblyBox>
		{/if}

		<div class="relative overflow-auto rounded border-[1.8px] border-[#1a1917] bg-[#f3efe6] p-2 shadow-[2px_2px_0_#1a1917]">
			<div
				class="mine-grid relative mx-auto"
				style="width: {width * cellSize}px; height: {height * cellSize}px;"
				role="grid"
				aria-label="Minesweeper board"
			>
				{#each cells as row, r}
					{#each row as cell, c}
						{@const peer = players.find(
							(p) =>
								p.player_id !== profile.playerId &&
								p.cursor?.row === r &&
								p.cursor?.col === c
						)}
						<button
							type="button"
							role="gridcell"
							disabled={room?.status !== 'playing'}
							aria-label={`Cell ${r + 1}, ${c + 1}, ${cell.status}`}
							class="mine-cell absolute flex items-center justify-center border border-[#1a1917]/25 text-xs font-bold transition
							{cell.status === 'hidden' ? 'bg-[#e8e2d6] hover:bg-[#ddd5c4]' : ''}
							{cell.status === 'revealed' ? 'bg-[#faf8f4]' : ''}
							{cell.status === 'flagged' ? 'bg-[#e8e2d6]' : ''}
							{cell.status === 'mine_revealed' ? 'mine-boom bg-[#faf8f4]' : ''}
							{peer ? 'ring-2 ring-offset-0' : ''}"
							style="left: {c * cellSize}px; top: {r * cellSize}px; width: {cellSize}px; height: {cellSize}px; font-size: {Math.max(
								10,
								cellSize * 0.42
							)}px; {peer
								? `box-shadow: inset 0 0 0 2px ${resolvePlayerColor(peer.player_id, profile.playerId, profile.primaryColor, players)}`
								: ''}"
							onpointerdown={(e) => handleCellPointerDown(r, c, e)}
							onpointerup={() => handleCellPointerUp(r, c)}
							onpointerleave={handleCellPointerCancel}
							onpointercancel={handleCellPointerCancel}
							oncontextmenu={(e) => handleContextMenu(r, c, e)}
							onmouseenter={() => client.sendCursor(r, c)}
						>
							{#if cell.status === 'revealed' && (cell.adjacent ?? 0) > 0}
								<span class="font-mono-num text-[#1a1917]">{cell.adjacent}</span>
							{:else if cell.status === 'flagged'}
								<svg
									width={cellSize * 0.55}
									height={cellSize * 0.55}
									viewBox="0 0 24 24"
									aria-hidden="true"
								>
									<path
										d="M5 3v18M5 4h10l-2 4 2 4H5"
										fill={flagColor(cell.flag_owner_id)}
										stroke="#1a1917"
										stroke-width="1.4"
										stroke-linejoin="round"
									/>
								</svg>
							{:else if cell.status === 'mine_revealed'}
								<svg
									class="mine-icon"
									width={cellSize * 0.55}
									height={cellSize * 0.55}
									viewBox="0 0 24 24"
									aria-hidden="true"
								>
									<circle cx="12" cy="12" r="6" fill="#1a1917" />
									<path
										d="M12 2v3M12 19v3M2 12h3M19 12h3M4.5 4.5l2 2M17.5 17.5l2 2M19.5 4.5l-2 2M6.5 17.5l-2 2"
										stroke="#1a1917"
										stroke-width="1.6"
										stroke-linecap="round"
									/>
								</svg>
							{/if}
						</button>
					{/each}
				{/each}

				{#each fxItems as fx (fx.id)}
					<div
						class="pointer-events-none absolute z-10 font-hand text-sm font-bold
						{fx.kind === 'boom' ? 'fx-boom' : 'fx-float'}"
						style="left: {fx.col * cellSize + cellSize / 2}px; top: {fx.row * cellSize +
							cellSize / 2}px; color: {fx.color ?? '#1a1917'}; transform: translate(-50%, -50%);"
					>
						{fx.text}
					</div>
				{/each}
			</div>
		</div>
	</div>
</RoomShell>

{#if challengeTarget}
	<div
		class="fixed inset-0 z-50 flex items-end justify-center bg-[#1a1917]/35 p-4 sm:items-center"
		role="dialog"
		tabindex="-1"
		aria-modal="true"
		aria-labelledby="challenge-title"
	>
		<ScribblyBox seed={71} class="w-full max-w-sm bg-[#faf8f4] p-5">
			<h2 id="challenge-title" class="font-hand text-xl">Challenge flag?</h2>
			<p class="mt-2 text-sm text-[#6e6a63]">
				{ownerName(challengeTarget.ownerId)} planted this flag. If they are right you lose 5 and
				they gain 5. If they are wrong, you gain 5 and they lose 5 — then the cell opens.
			</p>
			<div class="mt-4 flex flex-wrap justify-end gap-2">
				<ScribblyButton onclick={() => (challengeTarget = null)}>Cancel</ScribblyButton>
				<ScribblyButton
					variant="primary"
					accentColor={profile.primaryColor}
					onclick={confirmChallenge}
				>
					Challenge
				</ScribblyButton>
			</div>
		</ScribblyBox>
	</div>
{/if}

<style>
	.mine-cell {
		touch-action: manipulation;
		user-select: none;
		-webkit-user-select: none;
	}

	.mine-boom .mine-icon {
		animation: boom-pop 0.55s ease-out;
	}

	.fx-boom {
		animation: boom-pop 1.2s ease-out forwards;
		font-size: 1.15rem;
	}

	.fx-float {
		animation: float-up 1.05s ease-out forwards;
	}

	@keyframes boom-pop {
		0% {
			transform: translate(-50%, -50%) scale(0.4);
			opacity: 0;
		}
		35% {
			transform: translate(-50%, -50%) scale(1.35);
			opacity: 1;
		}
		100% {
			transform: translate(-50%, -55%) scale(1);
			opacity: 0;
		}
	}

	@keyframes float-up {
		0% {
			transform: translate(-50%, -40%);
			opacity: 0;
		}
		20% {
			opacity: 1;
		}
		100% {
			transform: translate(-50%, -120%);
			opacity: 0;
		}
	}
</style>
