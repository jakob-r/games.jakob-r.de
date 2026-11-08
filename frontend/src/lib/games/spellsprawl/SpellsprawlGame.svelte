<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { resolvePlayerColor } from '$lib/core/color';
	import PlayerBar from '$lib/core/components/PlayerBar.svelte';
	import RoomShell from '$lib/core/components/RoomShell.svelte';
	import ScribblyBox from '$lib/core/components/ScribblyBox.svelte';
	import ScribblyButton from '$lib/core/components/ScribblyButton.svelte';
	import TurnNotificationBell from '$lib/core/components/TurnNotificationBell.svelte';
	import ZoomBoard from '$lib/core/components/ZoomBoard.svelte';
	import { profile } from '$lib/core/profile.svelte';
	import { RoomSocketClient, type PlayerInfo, type ServerEvent } from '$lib/core/ws.svelte';
	import {
		cellKey,
		foldLetters,
		parseKey,
		previewPlacement,
		step,
		type Cells,
		type Coord,
		type Direction
	} from './board';

	let { roomId }: { roomId: string } = $props();

	type EndCondition = 'words' | 'points' | 'area';

	interface PlayedWordEntry {
		word: string;
		cross_words: string[];
		player_id: string;
		positions: { row: number; col: number }[];
		placed: { row: number; col: number }[];
		points: number;
		move_number: number;
	}

	interface TurnPassedMove {
		type: 'turn_passed';
		player_id: string;
	}

	interface SpellsprawlState {
		language?: string;
		letter_scores?: Record<string, number>;
		end_condition?: EndCondition;
		end_target?: number;
		cells?: Cells;
		turn_order?: string[];
		current_player_id?: string | null;
		played_words?: PlayedWordEntry[];
		player_scores?: Record<string, number>;
		words_played?: number;
		area?: number;
		move_count?: number;
		last_move?: PlayedWordEntry | TurnPassedMove | null;
	}

	const client = new RoomSocketClient();

	const LANGUAGES: { code: string; label: string }[] = [
		{ code: 'de', label: 'Deutsch' },
		{ code: 'en', label: 'English' },
		{ code: 'fr', label: 'Français' },
		{ code: 'es', label: 'Español' }
	];
	const END_CONDITIONS: { code: EndCondition; label: string; hint: string; targets: number[] }[] =
		[
			{ code: 'words', label: 'Words played', hint: 'Ends after this many words.', targets: [20, 50, 100] },
			{ code: 'points', label: 'Points', hint: 'First player to reach this score wins.', targets: [200, 500, 1000] },
			{ code: 'area', label: 'Grid size', hint: 'Ends once height × width of the grid exceeds this.', targets: [200, 500, 1000] }
		];
	const MARGIN = 4;
	const MIN_CELL = 26;
	const MAX_CELL = 64;
	const SENTINEL = ' ';

	let room = $derived(client.room);
	let gameState = $derived((room?.state ?? {}) as SpellsprawlState);
	let players = $derived<PlayerInfo[]>(room?.players ?? []);
	let isHost = $derived(room?.host_player_id === profile.playerId);
	let isPlaying = $derived(room?.status === 'playing');

	let cfgLanguage = $derived(String(room?.config?.language ?? 'de'));
	let cfgEnd = $derived((room?.config?.end_condition ?? 'words') as EndCondition);
	let cfgTarget = $derived(Number(room?.config?.end_target ?? 50));

	let language = $derived(gameState.language ?? cfgLanguage);
	let letterScores = $derived(gameState.letter_scores ?? {});
	let endCondition = $derived(gameState.end_condition ?? cfgEnd);
	let endTarget = $derived(gameState.end_target ?? cfgTarget);
	let cells = $derived<Cells>(gameState.cells ?? {});
	let playedWords = $derived<PlayedWordEntry[]>(gameState.played_words ?? []);
	let currentPlayerId = $derived(gameState.current_player_id ?? null);
	let isMyTurn = $derived(isPlaying && currentPlayerId === profile.playerId);
	let lastWord = $derived.by(() => {
		const last = gameState.last_move;
		return last && 'word' in last ? last : null;
	});
	let lastPlacedKeys = $derived(
		new Set((lastWord?.placed ?? []).map((p) => cellKey(p.row, p.col)))
	);

	// --- Composer state: a start cell, a direction, and new letters by offset along the line.
	let start = $state<Coord | null>(null);
	let direction = $state<Direction>('right');
	let pending = $state<Record<number, string>>({});
	let cursor = $state(0);
	let rejectReason = $state<string | null>(null);
	let rejectShake = $state(false);
	let cellSize = $state(40);
	let viewW = $state(0);
	let viewH = $state(0);
	let composerH = $state(0);

	let inputEl = $state<HTMLInputElement | null>(null);
	let scrollEl = $state<HTMLDivElement | null>(null);

	function posAt(offset: number): Coord {
		const [dr, dc] = step(direction);
		return [start![0] + offset * dr, start![1] + offset * dc];
	}

	let pendingCount = $derived(Object.keys(pending).length);
	let directionLocked = $derived(pendingCount >= 2);
	let pendingMap = $derived.by(() => {
		const map = new Map<string, string>();
		if (!start) return map;
		for (const [off, letter] of Object.entries(pending)) {
			const [r, c] = posAt(Number(off));
			map.set(cellKey(r, c), letter);
		}
		return map;
	});
	let cursorKey = $derived.by(() => {
		if (!start) return null;
		const [r, c] = posAt(cursor);
		return cellKey(r, c);
	});
	let preview = $derived(previewPlacement(cells, pendingMap, direction, letterScores));
	let previewOk = $derived('main' in preview ? preview : null);
	let alreadyPlayed = $derived(
		previewOk !== null && playedWords.some((entry) => entry.word === previewOk.main.word)
	);
	// Scores after submitting the pending word (shown in italics in the player bar).
	let previewScores = $derived.by(() => {
		if (!isMyTurn || !previewOk || alreadyPlayed) return null;
		const me = players.find((p) => p.player_id === profile.playerId);
		return me ? { [me.player_id]: me.score + previewOk.points } : null;
	});

	// --- Visible region: bounding box of everything plus a margin.
	let region = $derived.by(() => {
		const coords: Coord[] = Object.keys(cells).map(parseKey);
		for (const key of pendingMap.keys()) coords.push(parseKey(key));
		if (start) coords.push(start);
		if (cursorKey) coords.push(parseKey(cursorKey));
		if (coords.length === 0) coords.push([0, 0]);
		const rows = coords.map(([r]) => r);
		const cols = coords.map(([, c]) => c);
		let minRow = Math.min(...rows) - MARGIN;
		let minCol = Math.min(...cols) - MARGIN;
		let rowCount = Math.max(...rows) + MARGIN - minRow + 1;
		let colCount = Math.max(...cols) + MARGIN - minCol + 1;
		// Pad a small board so the grid fills the whole viewport.
		const needRows = Math.ceil(viewH / cellSize);
		const needCols = Math.ceil(viewW / cellSize);
		if (rowCount < needRows) {
			minRow -= Math.floor((needRows - rowCount) / 2);
			rowCount = needRows;
		}
		if (colCount < needCols) {
			minCol -= Math.floor((needCols - colCount) / 2);
			colCount = needCols;
		}
		return { minRow, minCol, rows: rowCount, cols: colCount };
	});

	let gridDims = $derived.by(() => {
		const coords = Object.keys(cells).map(parseKey);
		if (coords.length === 0) return { h: 0, w: 0 };
		const rows = coords.map(([r]) => r);
		const cols = coords.map(([, c]) => c);
		return {
			h: Math.max(...rows) - Math.min(...rows) + 1,
			w: Math.max(...cols) - Math.min(...cols) + 1
		};
	});

	let progressText = $derived.by(() => {
		if (endCondition === 'words') return `${gameState.words_played ?? 0}/${endTarget} words`;
		if (endCondition === 'area') return `grid ${gameState.area ?? 0}/${endTarget}`;
		return `first to ${endTarget}`;
	});

	let endSummary = $derived.by(() => {
		if (endCondition === 'words') return `${endTarget} words`;
		if (endCondition === 'area') return `grid > ${endTarget}`;
		return `${endTarget} pts`;
	});

	let turnNotificationHint = $derived.by(() => {
		const last = gameState.last_move;
		if (!last) return isPlaying ? `Spellsprawl #${roomId} has started — your move!` : '';
		const actor = players.find((p) => p.player_id === last.player_id)?.name ?? 'Someone';
		if ('word' in last) return `${actor} played "${last.word}" (+${last.points}). Your move!`;
		return `${actor} passed. Your move!`;
	});

	let winners = $derived.by(() => {
		if (players.length === 0) return [];
		const maxScore = Math.max(...players.map((p) => p.score));
		return players.filter((p) => p.score === maxScore);
	});

	function languageLabel(code: string): string {
		return LANGUAGES.find((l) => l.code === code)?.label ?? code.toUpperCase();
	}

	function formatReason(reason: string, word: string): string {
		switch (reason) {
			case 'not_your_turn':
				return 'Wait for your turn.';
			case 'already_played':
				return `"${word}" has already been played.`;
			case 'not_in_dictionary':
				return `"${word}" is not in the ${languageLabel(language)} dictionary.`;
			case 'gap':
				return 'Your letters must form one unbroken line.';
			case 'not_in_line':
				return 'Words go either across or down.';
			case 'too_short':
				return 'Words need at least 2 letters.';
			case 'occupied':
				return 'That cell is already taken.';
			default:
				return 'Invalid word.';
		}
	}

	// --- Lobby config
	function updateLanguage(code: string) {
		if (isHost) client.updateConfig({ language: code });
	}

	function updateEnd(code: EndCondition) {
		if (!isHost) return;
		const def = END_CONDITIONS.find((e) => e.code === code)!;
		client.updateConfig({ end_condition: code, end_target: def.targets[1] });
	}

	function updateTarget(target: number) {
		if (isHost) client.updateConfig({ end_target: target });
	}

	// --- Composing
	function focusInput() {
		if (!inputEl) return;
		inputEl.value = SENTINEL;
		inputEl.focus({ preventScroll: true });
		inputEl.setSelectionRange(1, 1);
	}

	function resetComposer() {
		start = null;
		pending = {};
		cursor = 0;
		rejectReason = null;
	}

	function setDirection(next: Direction) {
		if (!start || directionLocked || next === direction) {
			if (!start) direction = next;
			return;
		}
		const entries = Object.entries(pending);
		if (entries.length === 1) {
			// Re-anchor on the single letter so it stays where it is.
			const [off, letter] = entries[0];
			start = posAt(Number(off));
			pending = { 0: letter };
			cursor = 1;
		} else {
			cursor = 0;
		}
		direction = next;
	}

	function onLineOffset(row: number, col: number): number | null {
		if (!start) return null;
		if (direction === 'right') return row === start[0] ? col - start[1] : null;
		return col === start[1] ? row - start[0] : null;
	}

	function tapCell(row: number, col: number) {
		if (!isMyTurn) return;
		rejectReason = null;
		const offset = onLineOffset(row, col);
		if (start && start[0] === row && start[1] === col && !directionLocked) {
			setDirection(direction === 'right' ? 'down' : 'right');
		} else if (offset !== null && (pendingCount > 0 || offset === 0)) {
			if (offset < 0) {
				// Extend the line backwards: re-index pending letters from the new start.
				const shifted: Record<number, string> = {};
				for (const [off, letter] of Object.entries(pending)) shifted[Number(off) - offset] = letter;
				start = [row, col];
				pending = shifted;
				cursor = 0;
			} else {
				cursor = offset;
			}
		} else {
			start = [row, col];
			pending = {};
			cursor = 0;
		}
		client.sendCursor(row, col);
		focusInput();
	}

	function typeLetter(letter: string) {
		if (!start || !isMyTurn) return;
		rejectReason = null;
		let off = cursor;
		const [r, c] = posAt(off);
		const existing = cells[cellKey(r, c)];
		if (existing && pending[off] === undefined) {
			if (existing.letter === letter) {
				cursor = off + 1;
				return;
			}
			while (cells[cellKey(...posAt(off))]) off += 1;
		}
		pending = { ...pending, [off]: letter };
		cursor = off + 1;
	}

	function backspace() {
		if (!start) return;
		rejectReason = null;
		const before = Object.keys(pending)
			.map(Number)
			.filter((o) => o < cursor);
		if (before.length === 0) {
			if (pendingCount === 0) resetComposer();
			return;
		}
		const off = Math.max(...before);
		const next = { ...pending };
		delete next[off];
		pending = next;
		cursor = off;
	}

	function moveCursor(delta: number) {
		if (!start) return;
		cursor += delta;
	}

	function submitWord() {
		if (!isMyTurn || !start || !previewOk || alreadyPlayed) return;
		rejectReason = null;
		const placements = Object.entries(pending).map(([off, letter]) => {
			const [row, col] = posAt(Number(off));
			return { row, col, letter };
		});
		client.sendAction({ type: 'submit_word', placements, direction });
	}

	function passTurn() {
		if (!isMyTurn || pendingCount > 0) return;
		client.sendAction({ type: 'pass_turn' });
	}

	function onInput() {
		if (!inputEl) return;
		const value = inputEl.value;
		if (value === '') {
			backspace();
		} else {
			for (const ch of foldLetters(value)) typeLetter(ch);
		}
		inputEl.value = SENTINEL;
		inputEl.setSelectionRange(1, 1);
	}

	function handleKey(e: KeyboardEvent, fromInput: boolean) {
		if (!isMyTurn || e.metaKey || e.ctrlKey || e.altKey) return;
		const next = direction === 'right';
		switch (e.key) {
			case 'Enter':
				e.preventDefault();
				submitWord();
				return;
			case 'Escape':
				e.preventDefault();
				resetComposer();
				inputEl?.blur();
				return;
			case 'Backspace':
				if (!start) return;
				e.preventDefault();
				backspace();
				return;
			case 'ArrowLeft':
			case 'ArrowUp':
			case 'ArrowRight':
			case 'ArrowDown': {
				if (!start) return;
				e.preventDefault();
				const horizontal = e.key === 'ArrowLeft' || e.key === 'ArrowRight';
				const forward = e.key === 'ArrowRight' || e.key === 'ArrowDown';
				if (horizontal === next) moveCursor(forward ? 1 : -1);
				else setDirection(horizontal ? 'right' : 'down');
				return;
			}
		}
		if (!fromInput && start && e.key.length === 1) {
			const letters = foldLetters(e.key);
			if (letters) {
				e.preventDefault();
				for (const ch of letters) typeLetter(ch);
				focusInput();
			}
		}
	}

	function onWindowKeydown(e: KeyboardEvent) {
		const target = e.target as HTMLElement | null;
		if (target === inputEl) return;
		if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return;
		handleKey(e, false);
	}

	function onBoardClick(e: MouseEvent) {
		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
		const col = region.minCol + Math.floor((e.clientX - rect.left) / cellSize);
		const row = region.minRow + Math.floor((e.clientY - rect.top) / cellSize);
		tapCell(row, col);
	}

	function scrollToCells(coords: Coord[], smooth: boolean) {
		const el = scrollEl;
		if (!el || coords.length === 0) return;
		const rows = coords.map(([r]) => r);
		const cols = coords.map(([, c]) => c);
		const midRow = (Math.min(...rows) + Math.max(...rows) + 1) / 2;
		const midCol = (Math.min(...cols) + Math.max(...cols) + 1) / 2;
		el.scrollTo({
			left: (midCol - region.minCol) * cellSize - el.clientWidth / 2,
			top: (midRow - region.minRow) * cellSize - el.clientHeight / 2,
			behavior: smooth ? 'smooth' : 'auto'
		});
	}

	// Center the board when the game shows up, and follow each new word.
	let centeredFor = $state<string | null>(null);
	$effect(() => {
		const marker = `${room?.status}:${gameState.move_count ?? 0}`;
		if (!scrollEl || !isPlaying && room?.status !== 'finished') return;
		if (marker === centeredFor) return;
		const first = centeredFor === null;
		centeredFor = marker;
		const target: Coord[] = lastWord
			? lastWord.positions.map((p) => [p.row, p.col] as Coord)
			: Object.keys(cells).map(parseKey);
		tick().then(() => scrollToCells(target.length ? target : [[0, 0]], !first));
	});

	// Keep the typing cursor in view.
	$effect(() => {
		const el = scrollEl;
		if (!el || !cursorKey) return;
		const [r, c] = parseKey(cursorKey);
		const x = (c - region.minCol) * cellSize;
		const y = (r - region.minRow) * cellSize;
		tick().then(() => {
			const pad = cellSize;
			if (x < el.scrollLeft + pad) el.scrollLeft = x - pad;
			else if (x + cellSize > el.scrollLeft + el.clientWidth - pad)
				el.scrollLeft = x + cellSize + pad - el.clientWidth;
			if (y < el.scrollTop + pad) el.scrollTop = y - pad;
			else if (y + cellSize > el.scrollTop + el.clientHeight - pad)
				el.scrollTop = y + cellSize + pad - el.clientHeight;
		});
	});

	function cellColor(playerId: string): string {
		return resolvePlayerColor(playerId, profile.playerId, profile.primaryColor, players);
	}

	onMount(() => {
		profile.init();
		client.connect({
			gameSlug: 'spellsprawl',
			roomId,
			playerId: profile.playerId,
			name: profile.name,
			color: profile.primaryColor
		});

		const unsub = client.onEvent((ev: ServerEvent) => {
			if (ev.type === 'word_played' || ev.type === 'turn_passed') {
				resetComposer();
			} else if (ev.type === 'word_rejected' && ev.player_id === profile.playerId) {
				rejectReason = formatReason(ev.reason, ev.word);
				rejectShake = true;
				setTimeout(() => {
					rejectShake = false;
				}, 450);
			}
		});

		window.addEventListener('keydown', onWindowKeydown);
		return () => {
			window.removeEventListener('keydown', onWindowKeydown);
			unsub();
			client.disconnect();
		};
	});
</script>

<RoomShell {client} {roomId} title="Spellsprawl" subtitleItems={[language.toUpperCase(), endSummary]}>
	{#snippet headerActions()}
		<TurnNotificationBell
			{roomId}
			playerId={profile.playerId}
			gameSlug="spellsprawl"
			gameTitle="Spellsprawl"
			{isMyTurn}
			{isPlaying}
			turnHint={turnNotificationHint}
		/>
	{/snippet}

	{#snippet configSlot()}
		<div class="space-y-4">
			{#if !isHost}
				<div class="font-hand text-right text-xs text-[#6e6a63]">Configured by host</div>
			{/if}

			<div>
				<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">
					Dictionary Language
				</span>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
					{#each LANGUAGES as lang (lang.code)}
						<button
							type="button"
							disabled={!isHost}
							onclick={() => updateLanguage(lang.code)}
							class="cursor-pointer rounded border border-[#1a1917] px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed
							{cfgLanguage === lang.code
								? 'bg-[#1a1917] text-[#faf8f4]'
								: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
						>
							{lang.label}
						</button>
					{/each}
				</div>
			</div>

			<div>
				<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">Game Ends</span>
				<div class="grid grid-cols-3 gap-2">
					{#each END_CONDITIONS as cond (cond.code)}
						<button
							type="button"
							disabled={!isHost}
							onclick={() => updateEnd(cond.code)}
							class="cursor-pointer rounded border border-[#1a1917] px-2 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed
							{cfgEnd === cond.code
								? 'bg-[#1a1917] text-[#faf8f4]'
								: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
						>
							{cond.label}
						</button>
					{/each}
				</div>
				{#each END_CONDITIONS.filter((c) => c.code === cfgEnd) as cond (cond.code)}
					<div class="mt-2 flex flex-wrap items-center gap-1.5">
						{#each cond.targets as target (target)}
							<button
								type="button"
								disabled={!isHost}
								onclick={() => updateTarget(target)}
								class="font-mono-num cursor-pointer rounded border border-[#1a1917] px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed
								{cfgTarget === target
									? 'bg-[#1a1917] text-[#faf8f4]'
									: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
							>
								{target}
							</button>
						{/each}
						<span class="text-xs text-[#6e6a63]">{cond.hint}</span>
					</div>
				{/each}
			</div>

			<p class="border-t border-[#1a1917]/15 pt-3 text-xs text-[#6e6a63]">
				New letters score nothing. Every letter you reuse from the grid scores its rarity
				(1–10), in your word and in any cross-words you form.
			</p>
		</div>
	{/snippet}

	<div class="mx-auto flex w-full max-w-[640px] flex-1 flex-col gap-3">
		<PlayerBar
			{players}
			hostPlayerId={room?.host_player_id ?? ''}
			myPlayerId={profile.playerId}
			myColor={profile.primaryColor}
			showTurnBadge={isPlaying}
			{currentPlayerId}
			statusText={progressText}
			{previewScores}
			onRemovePlayer={(id) => client.removePlayer(id)}
		/>

		{#if room?.status === 'finished'}
			<ScribblyBox seed={61} class="bg-[#faf8f4] p-4 text-center">
				<div class="font-hand text-xl">
					{#if winners.length === 1}
						{winners[0].name} wins ({winners[0].score} pts)!
					{:else if winners.length > 1}
						It's a tie! ({winners.map((w) => w.name).join(' & ')} — {winners[0].score} pts)
					{:else}
						Game Over!
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
			</ScribblyBox>
		{/if}

		<!-- Board -->
		<ZoomBoard
			bind:cellSize
			bind:el={scrollEl}
			bind:viewW
			bind:viewH
			originX={region.minCol}
			originY={region.minRow}
			minCell={MIN_CELL}
			maxCell={MAX_CELL}
			reserveBelow={composerH ? composerH + 12 : 0}
			ariaLabel="Spellsprawl grid"
		>
			<!-- svelte-ignore a11y_click_events_have_key_events -->
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="sprawl-board relative select-none {isMyTurn ? 'cursor-pointer' : 'cursor-default'}"
				style="width: {region.cols * cellSize}px; height: {region.rows * cellSize}px; --cs: {cellSize}px;"
				onclick={onBoardClick}
			>
				{#each Object.entries(cells) as [key, cell] (key)}
					{@const [r, c] = parseKey(key)}
					{@const color = cellColor(cell.player_id)}
					<div
						class="sprawl-cell absolute flex items-center justify-center
						{lastPlacedKeys.has(key) ? 'border-2 border-[#1a1917]' : 'border border-[#1a1917]/30'}"
						style="left: {(c - region.minCol) * cellSize}px; top: {(r - region.minRow) * cellSize}px; background-color: color-mix(in oklab, {color} 28%, #faf8f4);"
					>
						<span class="sprawl-letter">{cell.letter}</span>
						<span class="sprawl-value font-mono-num">{letterScores[cell.letter] ?? 1}</span>
					</div>
				{/each}

				{#each [...pendingMap] as [key, letter] (key)}
					{@const [r, c] = parseKey(key)}
					<div
						class="sprawl-cell absolute flex items-center justify-center border-2 border-dashed bg-white"
						style="left: {(c - region.minCol) * cellSize}px; top: {(r - region.minRow) * cellSize}px; border-color: {profile.primaryColor};"
					>
						<span class="sprawl-letter font-semibold">{letter}</span>
						<span class="sprawl-value font-mono-num">{letterScores[letter] ?? 1}</span>
					</div>
				{/each}

				{#if cursorKey && isMyTurn}
					{@const [r, c] = parseKey(cursorKey)}
					<div
						class="sprawl-cursor pointer-events-none absolute"
						style="left: {(c - region.minCol) * cellSize}px; top: {(r - region.minRow) * cellSize}px; width: {cellSize}px; height: {cellSize}px; --accent: {profile.primaryColor};"
					>
						<span class="sprawl-arrow">{direction === 'right' ? '▸' : '▾'}</span>
					</div>
				{/if}
			</div>
			{#snippet overlay()}
				{#if gridDims.w > 0}
					<div
						class="font-mono-num pointer-events-none absolute top-1.5 left-1.5 bg-[#faf8f4]/85 px-1.5 text-[11px] text-[#6e6a63]"
					>
						{gridDims.w}×{gridDims.h} = {gridDims.w * gridDims.h}
					</div>
				{/if}
			{/snippet}
		</ZoomBoard>

		<input
			bind:this={inputEl}
			class="sprawl-input"
			type="text"
			autocomplete="off"
			autocapitalize="characters"
			spellcheck="false"
			aria-label="Type letters"
			oninput={onInput}
			onkeydown={(e) => handleKey(e, true)}
		/>

		<!-- Composer -->
		{#if isPlaying}
			<div
				bind:clientHeight={composerH}
				class="border-[1.8px] border-[#1a1917] bg-[#faf8f4] px-3 py-2.5 {rejectShake
					? 'animate-mistake-shake'
					: ''}"
			>
				<div class="flex min-h-[38px] flex-wrap items-center justify-between gap-2">
					{#if !isMyTurn}
						<span class="text-xs text-[#6e6a63]">
							Waiting for {players.find((p) => p.player_id === currentPlayerId)?.name ?? 'the next player'}…
						</span>
					{:else if !start}
						<span class="text-xs text-[#6e6a63]">Tap a cell to start your word.</span>
					{:else if pendingCount === 0}
						<span class="text-xs text-[#6e6a63]">
							Type your word. Tap the start cell again to switch direction.
						</span>
					{:else if previewOk}
						<div class="flex flex-wrap items-center gap-1">
							{#each previewOk.main.word.split('') as ch, i (i)}
								{@const reused = previewOk.main.existing.includes(i)}
								<span
									class="sprawl-chip flex h-8 w-7 items-center justify-center border text-base font-semibold
									{reused ? 'border-[#1a1917] bg-[#e9e3d6]' : 'border-[#1a1917]/40 border-dashed bg-white'}"
								>
									{ch}
								</span>
							{/each}
							<span class="font-mono-num ml-1 text-xs font-semibold text-[#1a1917]">
								+{previewOk.points}
							</span>
							{#if previewOk.cross.length > 0}
								<span class="w-full text-xs text-[#6e6a63]">
									Also forms: {previewOk.cross.map((w) => w.word).join(', ')}
								</span>
							{/if}
						</div>
					{:else if 'reason' in preview}
						<span class="text-xs text-[#6e6a63]">{formatReason(preview.reason, '')}</span>
					{/if}

					{#if isMyTurn}
						<div class="flex gap-1">
							<button
								type="button"
								disabled={directionLocked}
								onclick={() => setDirection('right')}
								class="h-8 w-8 cursor-pointer border border-[#1a1917] text-sm disabled:cursor-not-allowed disabled:opacity-40
								{direction === 'right' ? 'bg-[#1a1917] text-[#faf8f4]' : 'bg-[#faf8f4]'}"
								aria-label="Type across">→</button
							>
							<button
								type="button"
								disabled={directionLocked}
								onclick={() => setDirection('down')}
								class="h-8 w-8 cursor-pointer border border-[#1a1917] text-sm disabled:cursor-not-allowed disabled:opacity-40
								{direction === 'down' ? 'bg-[#1a1917] text-[#faf8f4]' : 'bg-[#faf8f4]'}"
								aria-label="Type down">↓</button
							>
						</div>
					{/if}
				</div>

				{#if alreadyPlayed && previewOk}
					<p class="mt-1 text-xs font-medium text-[#dc2626]">
						"{previewOk.main.word}" was already played.
					</p>
				{/if}
				{#if rejectReason}
					<p class="mt-1 text-xs font-medium text-[#dc2626]">{rejectReason}</p>
				{/if}

				<div class="mt-2 flex items-center justify-between gap-2 border-t border-[#1a1917]/15 pt-2">
					{#if start}
						<ScribblyButton onclick={resetComposer} disabled={!isMyTurn}>Cancel</ScribblyButton>
					{:else}
						<ScribblyButton onclick={passTurn} disabled={!isMyTurn} title="Skip your turn">
							Pass Turn
						</ScribblyButton>
					{/if}
					<ScribblyButton
						onclick={submitWord}
						disabled={!isMyTurn || !previewOk || alreadyPlayed}
						variant="primary"
						accentColor={profile.primaryColor}
					>
						Submit Word
					</ScribblyButton>
				</div>
			</div>
		{/if}

		{#if playedWords.length > 0}
			<div class="border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-2.5">
				<div class="mb-1.5 text-[11px] font-semibold tracking-wide text-[#6e6a63] uppercase">
					Played Words ({playedWords.length})
				</div>
				<div class="flex max-h-[140px] flex-wrap gap-1.5 overflow-y-auto">
					{#each [...playedWords].reverse() as entry (entry.move_number)}
						<button
							type="button"
							onclick={() =>
								scrollToCells(
									entry.positions.map((p) => [p.row, p.col] as Coord),
									true
								)}
							title={entry.cross_words.length ? `Also: ${entry.cross_words.join(', ')}` : ''}
							class="inline-flex cursor-pointer items-center gap-1.5 border border-[#1a1917]/25 px-2 py-0.5 text-xs"
							style="background-color: color-mix(in oklab, {cellColor(entry.player_id)} 20%, #faf8f4);"
						>
							<span class="font-semibold tracking-wide text-[#1a1917]">{entry.word}</span>
							<span class="font-mono-num text-[10px] text-[#1a1917]/65">+{entry.points}</span>
						</button>
					{/each}
				</div>
			</div>
		{/if}
	</div>
</RoomShell>

<style>
	.sprawl-board {
		background-image:
			linear-gradient(to right, rgb(26 25 23 / 0.12) 1px, transparent 1px),
			linear-gradient(to bottom, rgb(26 25 23 / 0.12) 1px, transparent 1px);
		background-size: var(--cs) var(--cs);
	}

	.sprawl-cell {
		width: var(--cs);
		height: var(--cs);
		pointer-events: none;
	}

	.sprawl-letter,
	.sprawl-chip {
		font-family: Arial, Helvetica, system-ui, -apple-system, sans-serif;
		line-height: 1;
		color: #1a1917;
	}

	.sprawl-letter {
		font-size: calc(var(--cs) * 0.58);
	}

	.sprawl-value {
		position: absolute;
		right: 2px;
		bottom: 1px;
		font-size: max(8px, calc(var(--cs) * 0.22));
		line-height: 1;
		color: rgb(26 25 23 / 0.6);
	}

	.sprawl-cursor {
		outline: 2.5px solid var(--accent);
		outline-offset: -2px;
		animation: sprawl-blink 1.1s ease-in-out infinite;
	}

	.sprawl-arrow {
		position: absolute;
		left: 2px;
		top: 0;
		font-size: max(10px, calc(var(--cs) * 0.3));
		line-height: 1;
		color: var(--accent);
	}

	@keyframes sprawl-blink {
		50% {
			outline-color: transparent;
		}
	}

	/* Off-screen but focusable so mobile browsers open the system keyboard. */
	.sprawl-input {
		position: fixed;
		left: 0;
		bottom: 0;
		width: 1px;
		height: 1px;
		opacity: 0;
		font-size: 16px;
		pointer-events: none;
	}
</style>
