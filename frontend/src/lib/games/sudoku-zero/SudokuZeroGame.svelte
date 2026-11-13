<script lang="ts">
	import { onMount } from 'svelte';
	import { resolvePlayerColor } from '#lib/core/color.ts';
	import PlayerBar from '#lib/core/components/PlayerBar.svelte';
	import RoomShell from '#lib/core/components/RoomShell.svelte';
	import ScribblyBox from '#lib/core/components/ScribblyBox.svelte';
	import ScribblyButton from '#lib/core/components/ScribblyButton.svelte';
	import TurnNotificationBell from '#lib/core/components/TurnNotificationBell.svelte';
	import { profile } from '#lib/core/profile.svelte.ts';
	import { RoomSocketClient, type PlayerInfo, type ServerEvent } from '#lib/core/ws.svelte.ts';
	import { countInBackground } from './count.ts';
	import { SOLUTION_CAP, endBonus, formatCount, hasConflict } from './solver.ts';

	let { roomId }: { roomId: string } = $props();

	interface Cell {
		row: number;
		col: number;
		value: number;
	}

	type LastMove =
		| (Cell & {
				type: 'place';
				player_id: string;
				solutions_before: number;
				solutions: number;
				points: number;
				end_bonus: number | null;
		  })
		| (Cell & { type: 'wrong'; player_id: string })
		| { type: 'pass' | 'give_up'; player_id: string };

	type EndReason = 'unique' | 'gave_up' | 'contradiction' | 'passed' | 'wrong_clues';

	interface ZeroState {
		solo?: boolean;
		grid?: number[][];
		owners?: (string | null)[][];
		solutions?: number;
		clues?: number;
		turn_order?: string[];
		current_player_id?: string | null;
		consecutive_passes?: number;
		consecutive_wrongs?: number;
		move_count?: number;
		last_move?: LastMove | null;
		failed_cell?: Cell | null;
		end_reason?: EndReason | null;
		end_bonus?: number | null;
	}

	interface Popup {
		id: number;
		row: number;
		col: number;
		text: string;
		color: string;
	}

	const client = new RoomSocketClient();
	const DIGITS = [1, 2, 3, 4, 5, 6, 7, 8, 9];

	let selected = $state<number | null>(null);
	let pending = $state<number | null>(null);
	let counting = $state(false);
	let confirmGiveUp = $state(false);
	let message = $state<string | null>(null);
	let popups = $state<Popup[]>([]);
	let flash = $state<Cell | null>(null);
	let popupId = 0;

	let room = $derived(client.room);
	let gameState = $derived((room?.state ?? {}) as ZeroState);
	let players = $derived<PlayerInfo[]>(room?.players ?? []);
	let isHost = $derived(room?.host_player_id === profile.playerId);
	let playing = $derived(room?.status === 'playing');

	let cfgSolo = $derived(Boolean(room?.config?.solo ?? false));
	// Solo can only be switched on while the host is alone in the room.
	let canSwitchToSolo = $derived(players.filter((p) => !p.is_bot).length <= 1);

	let isSolo = $derived(gameState.solo ?? cfgSolo);
	let flat = $derived((gameState.grid ?? []).flat());
	let solutions = $derived(gameState.solutions ?? SOLUTION_CAP);
	let clues = $derived(gameState.clues ?? 0);
	let currentPlayerId = $derived(gameState.current_player_id ?? null);
	let isMyTurn = $derived(playing && currentPlayerId === profile.playerId);
	let lastMove = $derived(gameState.last_move ?? null);
	let lastPlacedIndex = $derived(
		lastMove && lastMove.type === 'place' ? lastMove.row * 9 + lastMove.col : null
	);
	let failedIndex = $derived(
		gameState.failed_cell ? gameState.failed_cell.row * 9 + gameState.failed_cell.col : null
	);
	// What a unique grid would be worth if the next clue made it unique.
	let uniqueNowBonus = $derived(endBonus(clues + 1));
	let cluesLabel = $derived(`${clues} ${clues === 1 ? 'clue' : 'clues'}`);
	let opponentPassed = $derived(
		!isSolo && (gameState.consecutive_passes ?? 0) > 0 && lastMove?.type === 'pass'
	);
	let canPlace = $derived(
		isMyTurn && !counting && selected !== null && pending !== null && !flat[selected]
	);

	let playerName = (id: string | null | undefined) =>
		players.find((p) => p.player_id === id)?.name ?? 'Opponent';

	function inkFor(playerId: string | null | undefined): string {
		if (!playerId || isSolo) return '#1a1917';
		return resolvePlayerColor(playerId, profile.playerId, profile.primaryColor, players);
	}

	let turnNotificationHint = $derived.by(() => {
		if (!lastMove) return playing ? `Sudoku Zero #${roomId} has started. Your move!` : '';
		const actor = playerName(lastMove.player_id);
		if (lastMove.type === 'place')
			return `${actor} placed a ${lastMove.value} (${formatCount(lastMove.solutions)} solutions left). Your move!`;
		if (lastMove.type === 'wrong') return `${actor} placed a clue with no solution. Your move!`;
		return `${actor} passed. Your move!`;
	});

	let winners = $derived.by(() => {
		if (players.length === 0) return [];
		const max = Math.max(...players.map((p) => p.score));
		return players.filter((p) => p.score === max);
	});
	let myScore = $derived(players.find((p) => p.player_id === profile.playerId)?.score ?? 0);

	let endText = $derived.by(() => {
		switch (gameState.end_reason) {
			case 'unique':
				return `Unique with ${cluesLabel}! End bonus +${gameState.end_bonus ?? 0}${isSolo ? '' : ' (split)'}.`;
			case 'gave_up':
				return `Stopped at ${cluesLabel}, ${formatCount(solutions)} ${solutions === 1 ? 'solution' : 'solutions'} left.`;
			case 'contradiction':
				return 'That clue left no solution (−50).';
			case 'passed':
				return 'Both players passed.';
			case 'wrong_clues':
				return 'Two clues without a solution in a row.';
			default:
				return 'Game over.';
		}
	});

	function reasonText(reason: string): string {
		if (reason === 'occupied') return 'That cell already has a clue.';
		if (reason === 'conflict') return 'That number is already in the row, column or box.';
		if (reason === 'count_mismatch') return 'The solution count did not match. Try again.';
		if (reason === 'not_your_turn') return 'Wait for your turn.';
		if (reason === 'no_solution') return 'No solution left: the clue was rejected (−50).';
		return 'Not possible.';
	}

	function updateSolo(solo: boolean) {
		if (!isHost || (solo && !canSwitchToSolo)) return;
		client.updateConfig({ solo });
	}

	function selectCell(index: number) {
		if (!playing) return;
		message = null;
		confirmGiveUp = false;
		selected = selected === index ? null : index;
		pending = null;
		if (!isSolo) client.sendCursor(selected === null ? null : Math.floor(index / 9), index % 9);
	}

	function pickDigit(d: number) {
		if (!isMyTurn || selected === null || flat[selected] || hasConflict(flat, selected, d)) return;
		message = null;
		if (pending === d) {
			void place();
			return;
		}
		pending = d;
	}

	async function place() {
		if (!canPlace || selected === null || pending === null) return;
		const index = selected;
		const value = pending;
		counting = true;
		try {
			const next = flat.slice();
			next[index] = value;
			const n = await countInBackground(next);
			client.sendAction({
				type: 'place',
				row: Math.floor(index / 9),
				col: index % 9,
				value,
				solutions: n
			});
		} finally {
			counting = false;
		}
	}

	function passOrGiveUp() {
		if (!isMyTurn) return;
		if (isSolo) {
			if (!confirmGiveUp) {
				confirmGiveUp = true;
				return;
			}
			client.sendAction({ type: 'give_up' });
		} else {
			client.sendAction({ type: 'pass_turn' });
		}
		confirmGiveUp = false;
	}

	function addPopup(row: number, col: number, text: string, color: string) {
		const id = popupId++;
		popups = [...popups, { id, row, col, text, color }];
		setTimeout(() => (popups = popups.filter((p) => p.id !== id)), 1300);
	}

	function handleKeydown(e: KeyboardEvent) {
		if (!playing || e.metaKey || e.ctrlKey || e.altKey) return;
		const target = e.target as HTMLElement | null;
		if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return;
		const moves: Record<string, number> = { ArrowUp: -9, ArrowDown: 9, ArrowLeft: -1, ArrowRight: 1 };
		if (e.key in moves) {
			e.preventDefault();
			const from = selected ?? 40;
			const to = from + moves[e.key];
			if (to >= 0 && to < 81 && !(Math.abs(moves[e.key]) === 1 && Math.floor(to / 9) !== Math.floor(from / 9)))
				selectCell(to);
			else if (selected === null) selectCell(from);
			return;
		}
		if (/^[1-9]$/.test(e.key)) {
			e.preventDefault();
			pickDigit(Number(e.key));
			return;
		}
		if (e.key === 'Enter' && canPlace) {
			e.preventDefault();
			void place();
		} else if (e.key === 'Escape' || e.key === 'Backspace') {
			pending = null;
			if (e.key === 'Escape') selected = null;
		}
	}

	onMount(() => {
		profile.init();
		client.connect({
			gameSlug: 'sudoku-zero',
			roomId,
			playerId: profile.playerId,
			name: profile.name,
			color: profile.primaryColor
		});

		const unsub = client.onEvent((ev: ServerEvent) => {
			if (ev.type === 'clue_placed') {
				addPopup(ev.row, ev.col, `+${ev.points}`, inkFor(ev.player_id));
				if (ev.player_id === profile.playerId) {
					pending = null;
					selected = null;
				}
			} else if (ev.type === 'clue_rejected') {
				if (ev.reason === 'no_solution' && ev.row !== undefined && ev.col !== undefined) {
					const cell = { row: ev.row, col: ev.col, value: ev.value ?? 0 };
					flash = cell;
					addPopup(cell.row, cell.col, `−${ev.penalty ?? 50}`, '#dc2626');
					setTimeout(() => {
						if (flash === cell) flash = null;
					}, 1200);
				}
				if (ev.player_id === profile.playerId) {
					message = reasonText(ev.reason);
					pending = null;
				}
			} else if (ev.type === 'turn_passed') {
				pending = null;
			}
		});

		window.addEventListener('keydown', handleKeydown);
		return () => {
			window.removeEventListener('keydown', handleKeydown);
			unsub();
			client.disconnect();
		};
	});
</script>

<RoomShell
	{client}
	{roomId}
	title="Sudoku Zero"
	subtitleItems={[isSolo ? 'Solo' : '2 players']}
>
	{#snippet headerActions()}
		{#if !isSolo}
			<TurnNotificationBell
				{roomId}
				gameSlug="sudoku-zero"
				gameTitle="Sudoku Zero"
				{isMyTurn}
				isPlaying={playing}
				turnHint={turnNotificationHint}
			/>
		{/if}
	{/snippet}

	{#snippet configSlot()}
		<div class="space-y-4">
			{#if !isHost}
				<div class="font-hand text-right text-xs text-[#6e6a63]">Configured by host</div>
			{/if}
			<div class="space-y-1.5 text-sm text-[#1a1917]">
				<p>
					Start with an empty grid. Place clues until exactly one solution remains — the fewer
					clues, the bigger the end bonus (17 clues: 1000 points).
				</p>
				<p class="text-xs text-[#6e6a63]">
					Every clue scores 1 point plus a bonus for how much it cuts the solution count. A clue
					that leaves no solution costs 50.
				</p>
			</div>

			<div class="flex items-center justify-between border-t border-[#1a1917]/15 pt-3">
				<div>
					<div class="text-xs font-semibold uppercase">Solo</div>
					<div class="text-xs text-[#6e6a63]">
						{#if cfgSolo}
							Nobody else can join. Give up any time to keep your score.
						{:else if isHost && !canSwitchToSolo}
							Only possible while you are alone in the room.
						{:else}
							Off: two players take turns, pass instead of giving up.
						{/if}
					</div>
				</div>
				<button
					type="button"
					data-testid="zero-solo-toggle"
					aria-label="Solo mode"
					aria-pressed={cfgSolo}
					disabled={!isHost || (!cfgSolo && !canSwitchToSolo)}
					onclick={() => updateSolo(!cfgSolo)}
					class="cursor-pointer rounded border border-[#1a1917] px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50
					{cfgSolo ? 'bg-[#1a1917] text-[#faf8f4]' : 'bg-[#faf8f4] text-[#6e6a63]'}"
				>
					{cfgSolo ? 'On' : 'Off'}
				</button>
			</div>
		</div>
	{/snippet}

	<div class="mx-auto flex w-full max-w-[440px] flex-1 flex-col gap-3">
		<PlayerBar
			{players}
			hostPlayerId={room?.host_player_id ?? ''}
			myPlayerId={profile.playerId}
			myColor={profile.primaryColor}
			scoringEnabled={true}
			showTurnBadge={playing && !isSolo}
			{currentPlayerId}
			onRemovePlayer={(id) => client.removePlayer(id)}
		/>

		<!-- Live solution counter -->
		<div class="flex items-end justify-between gap-3 px-1" data-testid="zero-counter">
			<div>
				<div class="text-[10px] font-semibold tracking-wide text-[#6e6a63] uppercase">
					Solutions
				</div>
				<div class="font-mono-num text-3xl leading-none font-bold" data-testid="zero-solutions">
					{#if counting}
						<span class="text-[#6e6a63]">…</span>
					{:else}
						{formatCount(solutions)}{solutions === 1 ? ' ✓' : ''}
					{/if}
				</div>
			</div>
			<div class="text-right text-xs text-[#6e6a63]">
				<div><span class="font-mono-num font-semibold text-[#1a1917]">{clues}</span> {clues === 1 ? 'clue' : 'clues'}</div>
				{#if playing}
					<div>unique next: <span class="font-mono-num font-semibold text-[#1a1917]">+{uniqueNowBonus}</span></div>
				{/if}
			</div>
		</div>

		{#if room?.status === 'finished'}
			<ScribblyBox seed={71} class="bg-[#faf8f4] p-4 text-center">
				<div data-testid="zero-finished">
				<div class="font-hand text-xl">
					{#if isSolo}
						{endText} You scored {myScore} pts.
					{:else}
						{endText}
						{#if winners.length === 1}
							{winners[0].name} wins ({winners[0].score} pts)!
						{:else if winners.length > 1}
							It's a tie ({winners[0].score} pts)!
						{/if}
					{/if}
				</div>
				<div class="mt-3 flex justify-center gap-2">
					{#if isHost}
						<ScribblyButton onclick={() => client.returnToLobby()} variant="primary">
							New Round
						</ScribblyButton>
					{:else}
						<p class="text-sm text-[#6e6a63]">Waiting for the host to start a new round…</p>
					{/if}
				</div>
				</div>
			</ScribblyBox>
		{/if}

		<!-- 9×9 board -->
		<div class="relative mx-auto aspect-square w-full select-none">
			<div
				class="grid h-full w-full grid-cols-9 grid-rows-9 border-[2.5px] border-[#1a1917] bg-[#faf8f4]"
				role="grid"
				aria-label="Sudoku Zero board"
			>
				{#each DIGITS as _r, r (r)}
					{#each DIGITS as _c, c (c)}
						{@const index = r * 9 + c}
						{@const value = flat[index] ?? 0}
						{@const owner = gameState.owners?.[r]?.[c] ?? null}
						{@const isSelected = selected === index}
						{@const isFailed = failedIndex === index}
						{@const isFlash = flash !== null && flash.row === r && flash.col === c}
						{@const popup = popups.find((p) => p.row === r && p.col === c)}
						{@const peers = isSolo
							? []
							: players.filter(
									(p) =>
										p.player_id !== profile.playerId && p.cursor?.row === r && p.cursor?.col === c
								)}
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
							onclick={() => selectCell(index)}
							aria-label="Row {r + 1} Column {c + 1}{value ? `, ${value}` : ''}"
							data-cell={index}
							class="relative flex items-center justify-center bg-[#faf8f4] p-0 focus:outline-none {borderRight} {borderBottom}
							{isFlash ? 'animate-mistake-shake bg-[#dc2626]/15' : ''}
							{lastPlacedIndex === index ? 'bg-[#1a1917]/[0.06]' : ''}"
						>
							{#if isSelected}
								<span
									class="pointer-events-none absolute inset-[2px] rounded-[2px] border-2"
									style="border-color: {profile.primaryColor};"
								></span>
							{/if}
							{#each peers as peer (peer.player_id)}
								<span
									class="pointer-events-none absolute inset-[3px] rounded-[2px] border-[1.8px] border-dashed opacity-85"
									style="border-color: {inkFor(peer.player_id)};"
								></span>
							{/each}

							{#if value}
								<span
									class="font-hand animate-scribble-pop text-2xl font-bold sm:text-[27px]"
									style="color: {inkFor(owner)};"
								>
									{value}
								</span>
							{:else if isFailed && gameState.failed_cell}
								<span class="font-hand text-2xl font-bold text-[#dc2626] line-through">
									{gameState.failed_cell.value}
								</span>
							{:else if isFlash && flash}
								<span class="font-hand text-2xl font-bold text-[#dc2626] line-through">
									{flash.value}
								</span>
							{:else if isSelected && pending !== null}
								<span class="font-hand text-2xl font-bold opacity-45" style="color: {profile.primaryColor};">
									{pending}
								</span>
							{/if}

							{#if popup}
								<span
									class="animate-float-score font-mono-num pointer-events-none absolute -top-3 z-30 rounded border bg-[#faf8f4] px-1.5 py-0.5 text-[10px] font-bold shadow-sm"
									style="color: {popup.color}; border-color: {popup.color};"
								>
									{popup.text}
								</span>
							{/if}
						</button>
					{/each}
				{/each}
			</div>
		</div>

		{#if playing}
			<div class="space-y-2.5 pt-1">
				<div class="min-h-5 text-center text-xs text-[#6e6a63]" aria-live="polite">
					{#if message}
						<span class="text-[#dc2626]">{message}</span>
					{:else if counting}
						Counting solutions…
					{:else if !isMyTurn}
						Waiting for {playerName(currentPlayerId)}…
					{:else if opponentPassed}
						{playerName(lastMove?.player_id)} passed — passing now ends the round.
					{:else if selected === null}
						Tap an empty cell, then a number.
					{:else if pending !== null}
						Tap {pending} again or Place to commit.
					{/if}
				</div>

				<div class="grid grid-cols-9 gap-1.5 sm:gap-2">
					{#each DIGITS as d (d)}
						{@const blocked =
							!isMyTurn || selected === null || !!flat[selected] || hasConflict(flat, selected, d)}
						<button
							type="button"
							disabled={blocked || counting}
							onclick={() => pickDigit(d)}
							aria-label="Number {d}"
							aria-pressed={pending === d}
							class="flex h-12 cursor-pointer items-center justify-center rounded-md border-[1.8px] border-[#1a1917] shadow-[2px_2px_0px_#1a1917] transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-30 sm:h-13
							{pending === d ? 'bg-[#1a1917] text-[#faf8f4]' : 'bg-[#faf8f4]'}"
						>
							<span class="font-hand text-xl leading-none font-bold">{d}</span>
						</button>
					{/each}
				</div>

				<div class="flex gap-2">
					<button
						type="button"
						disabled={!canPlace}
						onclick={() => void place()}
						data-testid="zero-place"
						class="flex-1 cursor-pointer rounded-md border-[1.8px] border-[#1a1917] bg-[#1a1917] px-3 py-2 text-sm font-semibold text-[#faf8f4] transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-30"
					>
						Place
					</button>
					<button
						type="button"
						disabled={!isMyTurn || counting}
						onclick={passOrGiveUp}
						data-testid="zero-pass"
						class="cursor-pointer rounded-md border-[1.8px] border-[#1a1917] bg-[#faf8f4] px-3.5 py-2 text-sm font-semibold shadow-[2px_2px_0px_#1a1917] transition hover:bg-[#f2eee6] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-30"
					>
						{#if isSolo}
							{confirmGiveUp ? 'Sure? Stop here' : 'Give up'}
						{:else}
							Pass
						{/if}
					</button>
				</div>
			</div>
		{/if}
	</div>
</RoomShell>
