<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolvePlayerColor } from '$lib/core/color';
	import Lobby from '$lib/core/components/Lobby.svelte';
	import NamePromptModal from '$lib/core/components/NamePromptModal.svelte';
	import ProfileBadge from '$lib/core/components/ProfileBadge.svelte';
	import ScribblyBox from '$lib/core/components/ScribblyBox.svelte';
	import ScribblyButton from '$lib/core/components/ScribblyButton.svelte';
	import { profile } from '$lib/core/profile.svelte';
	import { RoomSocketClient, type PlayerInfo, type ServerEvent } from '$lib/core/ws.svelte';

	let { roomId }: { roomId: string } = $props();

	interface SudokuCell {
		value: number | null;
		given: boolean;
		author_id: string | null;
	}

	interface SudokuPublicState {
		cells?: SudokuCell[][];
		notes?: Record<string, string>[][];
		hard_cells?: boolean[][];
		filled_count?: number;
		total_cells?: number;
		difficulty?: 'easy' | 'medium' | 'hard' | 'expert';
		scoring_enabled?: boolean;
	}

	interface MistakeFlash {
		id: number;
		row: number;
		col: number;
		value: number;
		player_id: string;
		points_delta: number;
	}

	interface ScorePopup {
		id: number;
		row: number;
		col: number;
		player_id: string;
		points_delta: number;
		multiplier: number;
		reason: string;
	}

	const client = new RoomSocketClient();

	let selectedRow = $state<number | null>(4);
	let selectedCol = $state<number | null>(4);
	let noteMode = $state<boolean>(false);
	let mistakeFlashes = $state<MistakeFlash[]>([]);
	let scorePopups = $state<ScorePopup[]>([]);
	let deletingRoom = $state<boolean>(false);
	let leavingRoom = $state<boolean>(false);
	let nowTick = $state<number>(Date.now());
	let flashCounter = 0;

	const DIFFICULTIES: ('easy' | 'medium' | 'hard' | 'expert')[] = [
		'easy',
		'medium',
		'hard',
		'expert'
	];

	let room = $derived(client.room);
	let sudokuState = $derived((room?.state ?? {}) as SudokuPublicState);
	let cells = $derived(sudokuState.cells ?? []);
	let notes = $derived(sudokuState.notes ?? []);
	let players = $derived<PlayerInfo[]>(room?.players ?? []);
	let isHost = $derived(room?.host_player_id === profile.playerId);
	let scoringEnabled = $derived(Boolean(room?.config?.scoring_enabled ?? true));
	let currentDifficulty = $derived(String(room?.config?.difficulty ?? 'medium'));

	// Count how many of each digit (1..9) are already placed on the board
	let digitCounts = $derived.by(() => {
		const counts: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0 };
		for (const row of cells) {
			for (const cell of row) {
				if (cell.value) {
					counts[cell.value] = (counts[cell.value] ?? 0) + 1;
				}
			}
		}
		return counts;
	});

	onMount(() => {
		profile.init();
		client.connect({
			gameSlug: 'sudoku',
			roomId,
			playerId: profile.playerId,
			name: profile.name,
			color: profile.primaryColor
		});

		const unsub = client.onEvent((ev: ServerEvent) => {
			if (ev.type === 'mistake_flash') {
				const id = ++flashCounter;
				mistakeFlashes = [
					...mistakeFlashes,
					{
						id,
						row: ev.row,
						col: ev.col,
						value: ev.value,
						player_id: ev.player_id,
						points_delta: ev.points_delta
					}
				];
				setTimeout(() => {
					mistakeFlashes = mistakeFlashes.filter((f) => f.id !== id);
				}, 950);
			} else if (ev.type === 'cell_scored') {
				const id = ++flashCounter;
				scorePopups = [
					...scorePopups,
					{
						id,
						row: ev.row,
						col: ev.col,
						player_id: ev.player_id,
						points_delta: ev.points_delta,
						multiplier: ev.multiplier,
						reason: ev.reason
					}
				];
				setTimeout(() => {
					scorePopups = scorePopups.filter((s) => s.id !== id);
				}, 1150);
			}
		});

		const timer = setInterval(() => {
			nowTick = Date.now();
		}, 120);

		return () => {
			clearInterval(timer);
			unsub();
			client.disconnect();
		};
	});

	function selectCell(r: number, c: number) {
		selectedRow = r;
		selectedCol = c;
		client.sendCursor(r, c);
	}

	function enterDigit(digit: number) {
		if (room?.status !== 'playing' || selectedRow === null || selectedCol === null) return;
		const cell = cells[selectedRow]?.[selectedCol];
		if (!cell || cell.value !== null) return;

		if (noteMode) {
			client.sendAction({
				type: 'toggle_note',
				row: selectedRow,
				col: selectedCol,
				digit
			});
		} else {
			client.sendAction({
				type: 'set_value',
				row: selectedRow,
				col: selectedCol,
				value: digit
			});
		}
	}

	function clearSelectedCell() {
		if (room?.status !== 'playing' || selectedRow === null || selectedCol === null) return;
		client.sendAction({
			type: 'clear_cell',
			row: selectedRow,
			col: selectedCol
		});
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (room?.status !== 'playing') return;
		const tag = (e.target as HTMLElement | null)?.tagName;
		if (tag === 'INPUT' || tag === 'TEXTAREA') return;

		if (e.key >= '1' && e.key <= '9') {
			e.preventDefault();
			enterDigit(Number(e.key));
			return;
		}
		if (e.key === 'n' || e.key === 'N' || e.key === ' ') {
			e.preventDefault();
			noteMode = !noteMode;
			return;
		}
		if (e.key === 'Backspace' || e.key === 'Delete') {
			e.preventDefault();
			clearSelectedCell();
			return;
		}

		const r = selectedRow ?? 4;
		const c = selectedCol ?? 4;
		if (e.key === 'ArrowUp' || e.key === 'w' || e.key === 'W') {
			e.preventDefault();
			selectCell((r + 8) % 9, c);
		} else if (e.key === 'ArrowDown' || e.key === 's' || e.key === 'S') {
			e.preventDefault();
			selectCell((r + 1) % 9, c);
		} else if (e.key === 'ArrowLeft' || e.key === 'a' || e.key === 'A') {
			e.preventDefault();
			selectCell(r, (c + 8) % 9);
		} else if (e.key === 'ArrowRight' || e.key === 'd' || e.key === 'D') {
			e.preventDefault();
			selectCell(r, (c + 1) % 9);
		}
	}

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

	async function deleteRoom() {
		if (!isHost || !profile.playerId || deletingRoom) return;
		deletingRoom = true;
		try {
			const res = await fetch(
				`/api/rooms/${encodeURIComponent(roomId)}?player_id=${encodeURIComponent(profile.playerId)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				client.disconnect();
				await goto('/');
			}
		} finally {
			deletingRoom = false;
		}
	}

	async function leaveRoom() {
		if (isHost || !profile.playerId || leavingRoom) return;
		leavingRoom = true;
		try {
			const res = await fetch(
				`/api/rooms/${encodeURIComponent(roomId)}/players/${encodeURIComponent(profile.playerId)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				client.disconnect();
				await goto('/');
			}
		} finally {
			leavingRoom = false;
		}
	}
</script>

<svelte:window onkeydown={handleKeyDown} />

<NamePromptModal onConfirm={(name, color) => client.syncProfile(profile.playerId, name, color)} />

<div class="mx-auto flex w-full max-w-3xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-5">
	<!-- Top Header -->
	<header class="mb-3 flex items-center justify-between gap-2">
		<div class="flex items-center gap-2.5">
			<a
				href="/"
				class="inline-flex items-center gap-1 rounded border-[1.5px] border-[#1a1917] bg-[#faf8f4] px-2.5 py-1 text-xs font-medium shadow-[1.5px_1.5px_0px_#1a1917] hover:bg-[#f2eee6]"
			>
				← Home
			</a>
			<div>
				<h1 class="font-hand text-lg leading-none sm:text-xl">Multiplayer Sudoku</h1>
				<div class="font-mono-num flex items-center gap-2 text-[11px] text-[#6e6a63]">
					<span>#{roomId}</span>
					{#if room?.status === 'playing' || room?.status === 'finished'}
						<span>•</span>
						<span class="capitalize">{currentDifficulty}</span>
					{/if}
					{#if !client.connected}
						<span class="text-[#dc2626]">• reconnecting…</span>
					{/if}
				</div>
			</div>
		</div>

		<div class="flex items-center gap-2">
			{#if isHost}
				<button
					type="button"
					onclick={deleteRoom}
					disabled={deletingRoom}
					title="Permanently delete this session"
					aria-label="Permanently delete this session"
					class="inline-flex cursor-pointer items-center justify-center rounded border-[1.5px] border-[#1a1917] bg-[#faf8f4] p-1.5 text-[#6e6a63] shadow-[1.5px_1.5px_0px_#1a1917] transition hover:border-[#dc2626] hover:bg-[#fef2f2] hover:text-[#dc2626] disabled:cursor-not-allowed disabled:opacity-50"
				>
					<svg
						class="h-3.5 w-3.5"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path d="M3 6h18" />
						<path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
						<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
						<line x1="10" y1="11" x2="10" y2="17" />
						<line x1="14" y1="11" x2="14" y2="17" />
					</svg>
				</button>
			{:else if room}
				<button
					type="button"
					onclick={leaveRoom}
					disabled={leavingRoom}
					title="Leave this game"
					aria-label="Leave this game"
					class="inline-flex cursor-pointer items-center justify-center rounded border-[1.5px] border-[#1a1917] bg-[#faf8f4] px-2 py-1 text-xs font-medium text-[#6e6a63] shadow-[1.5px_1.5px_0px_#1a1917] transition hover:border-[#dc2626] hover:bg-[#fef2f2] hover:text-[#dc2626] disabled:cursor-not-allowed disabled:opacity-50"
				>
					Leave
				</button>
			{/if}
			<ProfileBadge
				compact={true}
				onChange={(name, color) => client.syncProfile(profile.playerId, name, color)}
			/>
		</div>
	</header>

	{#if client.error}
		<ScribblyBox seed={99} class="my-6 bg-[#faf8f4] p-6 text-center">
			<p class="font-hand text-lg text-[#dc2626]">{client.error}</p>
			<a href="/" class="mt-3 inline-block underline">Back to Landing Page</a>
		</ScribblyBox>
	{:else if !room}
		<div class="flex flex-1 items-center justify-center py-16">
			<p class="font-hand text-lg text-[#6e6a63]">Sketching room #{roomId}…</p>
		</div>
	{:else if room.status === 'lobby'}
		<Lobby
			{roomId}
			hostPlayerId={room.host_player_id}
			myPlayerId={profile.playerId}
			myColor={profile.primaryColor}
			{players}
			onToggleReady={(r) => client.setReady(r)}
			onStartGame={() => client.startGame()}
			onLeaveRoom={isHost ? undefined : leaveRoom}
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
						<div class="grid grid-cols-4 gap-2">
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
					</div>

					<div class="flex items-center justify-between border-t border-[#1a1917]/10 pt-3">
						<div>
							<div class="text-sm font-medium">Scoring & Streaks</div>
							<p class="text-xs text-[#6e6a63]">
								-10 mistakes • 1.1× streak within 10s
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
		</Lobby>
	{:else}
		<!-- Active or Finished Sudoku Board View -->
		<div class="mx-auto flex w-full max-w-md flex-1 flex-col justify-between gap-3">
			<!-- Players & Live Score / Multiplier Bar -->
			<div class="flex flex-wrap items-center justify-between gap-2">
				<div class="flex flex-wrap items-center gap-2">
					{#each players as p (p.player_id)}
						{@const pColor = resolvePlayerColor(
							p.player_id,
							profile.playerId,
							profile.primaryColor,
							players
						)}
						{@const multRatio = getMultiplierRemainingRatio(p)}
						{@const liveMult = getLiveMultiplier(p)}
						<div
							class="relative flex h-7 items-center gap-2 overflow-hidden rounded-md border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-2.5 shadow-[1.5px_1.5px_0px_#1a1917]"
						>
							<span
								class="h-2.5 w-2.5 shrink-0 rounded-full border border-[#1a1917]"
								style="background-color: {pColor};"
							></span>
							<span class="max-w-[92px] truncate text-xs font-semibold" style="color: {pColor};">
								{p.name}
							</span>

							{#if scoringEnabled}
								<span class="font-mono-num text-xs font-bold text-[#1a1917]">
									{p.score}
								</span>
								{#if liveMult > 1.001 && multRatio > 0}
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
						</div>
					{/each}
				</div>

				<div class="font-mono-num text-xs text-[#6e6a63]">
					{sudokuState.filled_count ?? 0}/81
				</div>
			</div>

			{#if room.status === 'finished'}
				<ScribblyBox seed={55} class="bg-[#faf8f4] p-4 text-center">
					<div class="font-hand text-xl">Board Completed!</div>
					{#if isHost}
						<div class="mt-3 flex justify-center gap-2">
							<ScribblyButton onclick={() => client.startGame()} variant="primary">
								New Board
							</ScribblyButton>
							<ScribblyButton onclick={() => client.returnToLobby()}>
								Lobby
							</ScribblyButton>
						</div>
					{/if}
				</ScribblyBox>
			{/if}

	<!-- 9x9 Sudoku Grid -->
			<div class="relative mx-auto aspect-square w-full max-w-[430px] select-none">
				<div
					class="grid h-full w-full grid-cols-9 grid-rows-9 border-[2.5px] border-[#1a1917] bg-[#faf8f4]"
					role="grid"
					aria-label="Sudoku Board"
				>
					{#each cells as rowCells, r (r)}
						{#each rowCells as cell, c (c)}
							{@const isSelected = selectedRow === r && selectedCol === c}
							{@const cellNotes = notes[r]?.[c] ?? {}}
							{@const flash = mistakeFlashes.find((f) => f.row === r && f.col === c)}
							{@const popup = scorePopups.find((s) => s.row === r && s.col === c)}
							{@const peerCursors = players.filter(
								(p) =>
									p.player_id !== profile.playerId &&
									p.cursor?.row === r &&
									p.cursor?.col === c
							)}
							{@const authorColor = cell.author_id
								? resolvePlayerColor(
										cell.author_id,
										profile.playerId,
										profile.primaryColor,
										players
									)
								: '#1a1917'}
							{@const borderRight =
								c === 8
									? ''
									: (c + 1) % 3 === 0
										? 'border-r-[2.5px] border-r-[#1a1917]'
										: 'border-r border-r-[#1a1917]/45'}
							{@const borderBottom =
								r === 8
									? ''
									: (r + 1) % 3 === 0
										? 'border-b-[2.5px] border-b-[#1a1917]'
										: 'border-b border-b-[#1a1917]/45'}

							<button
								type="button"
								onclick={() => selectCell(r, c)}
								aria-label="Row {r + 1} Column {c + 1}"
								class="relative flex items-center justify-center bg-[#faf8f4] p-0 focus:outline-none {borderRight} {borderBottom}
								{flash ? 'animate-mistake-shake bg-[#dc2626]/15' : ''}"
							>
								<!-- Local selection outline in player's own color -->
								{#if isSelected}
									<span
										class="pointer-events-none absolute inset-[2px] rounded-[2px] border-2"
										style="border-color: {profile.primaryColor};"
									></span>
								{/if}

								<!-- Other players' live cursors -->
								{#each peerCursors as peer (peer.player_id)}
									{@const peerColor = resolvePlayerColor(
										peer.player_id,
										profile.playerId,
										profile.primaryColor,
										players
									)}
									<span
										class="pointer-events-none absolute inset-[3px] rounded-[2px] border-[1.8px] border-dashed opacity-85"
										style="border-color: {peerColor};"
									></span>
								{/each}

								<!-- Cell Value -->
								{#if cell.value !== null}
									<span
										class="{cell.given
											? 'font-mono-num text-xl font-bold text-[#1a1917] sm:text-2xl'
											: 'font-hand animate-scribble-pop text-2xl font-bold sm:text-[27px]'}"
										style="color: {cell.given ? '#1a1917' : authorColor};"
									>
										{cell.value}
									</span>
								{:else if flash}
									<!-- Rejected mistake flash -->
									<span
										class="font-hand text-2xl font-bold text-[#dc2626] line-through"
									>
										{flash.value}
									</span>
								{:else}
									<!-- 1-9 Corner Notes in a 3x3 mini-grid -->
									<div class="pointer-events-none grid h-full w-full grid-cols-3 grid-rows-3 p-[2px]">
										{#each [1, 2, 3, 4, 5, 6, 7, 8, 9] as n (n)}
											{@const noteAuthor = cellNotes[String(n)]}
											<span
												class="font-mono-num flex items-center justify-center text-[9px] leading-none font-bold sm:text-[10px]"
												style="color: {noteAuthor
													? resolvePlayerColor(
															noteAuthor,
															profile.playerId,
															profile.primaryColor,
															players
														)
													: 'transparent'};"
											>
												{noteAuthor ? n : ''}
											</span>
										{/each}
									</div>
								{/if}

								<!-- Floating score delta popup (+points or -10 mistake) -->
								{#if scoringEnabled && popup}
									{@const popColor = resolvePlayerColor(
										popup.player_id,
										profile.playerId,
										profile.primaryColor,
										players
									)}
									<span
										class="animate-float-score font-mono-num pointer-events-none absolute -top-3 z-30 rounded border border-[#1a1917] bg-[#faf8f4] px-1.5 py-0.5 text-[10px] font-bold shadow-sm"
										style="color: {popColor};"
									>
										+{popup.points_delta}
									</span>
								{/if}

								{#if scoringEnabled && flash}
									<span
										class="animate-float-score font-mono-num pointer-events-none absolute -top-3 z-30 rounded border border-[#dc2626] bg-[#faf8f4] px-1.5 py-0.5 text-[10px] font-bold text-[#dc2626] shadow-sm"
									>
										{flash.points_delta}
									</span>
								{/if}
							</button>
						{/each}
					{/each}
				</div>
			</div>

			<!-- Mobile-First Controls & Numpad -->
			<div class="space-y-2.5 pt-1">
				<!-- Mode & Action Bar -->
				<div class="flex items-center justify-between gap-2">
					<button
						type="button"
						onclick={() => (noteMode = !noteMode)}
						class="flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-md border-[1.8px] border-[#1a1917] px-3 py-2 text-xs font-semibold transition active:scale-[0.98]
						{noteMode
							? 'bg-[#1a1917] text-[#faf8f4] shadow-[2px_2px_0px_#6e6a63]'
							: 'bg-[#faf8f4] text-[#1a1917] shadow-[2px_2px_0px_#1a1917]'}"
					>
						<span>✎ Notes: {noteMode ? 'ON' : 'OFF'}</span>
						<span class="hidden text-[10px] opacity-70 sm:inline">(Space / N)</span>
					</button>

					<button
						type="button"
						onclick={clearSelectedCell}
						class="cursor-pointer rounded-md border-[1.8px] border-[#1a1917] bg-[#faf8f4] px-3.5 py-2 text-xs font-semibold shadow-[2px_2px_0px_#1a1917] transition hover:bg-[#f2eee6] active:scale-[0.98]"
					>
						Clear
					</button>
				</div>

				<!-- 1-9 Touch Numpad -->
				<div class="grid grid-cols-9 gap-1.5 sm:gap-2">
					{#each [1, 2, 3, 4, 5, 6, 7, 8, 9] as digit (digit)}
						{@const exhausted = !noteMode && (digitCounts[digit] ?? 0) >= 9}
						<button
							type="button"
							disabled={exhausted}
							onclick={() => enterDigit(digit)}
							style="--my-color: {profile.primaryColor};"
							class="relative flex h-12 cursor-pointer flex-col items-center justify-center rounded-md border-[1.8px] border-[#1a1917] bg-[#faf8f4] shadow-[2px_2px_0px_#1a1917] transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-30 sm:h-13"
						>
							<span
								class="font-hand text-xl leading-none font-bold"
								style="color: {noteMode ? '#6e6a63' : profile.primaryColor};"
							>
								{digit}
							</span>
							<span class="font-mono-num mt-0.5 text-[9px] text-[#6e6a63]">
								{9 - Math.min(9, digitCounts[digit] ?? 0)}
							</span>
						</button>
					{/each}
				</div>
			</div>
		</div>
	{/if}
</div>
