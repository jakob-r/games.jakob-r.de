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
	import CardIcon from './CardIcon.svelte';
	import {
		CARD_LABELS,
		CARD_ORDER,
		CARD_SHAPES,
		CARD_TYPES,
		DECK_COUNTS,
		GRAY,
		boundingArea,
		boundingBox,
		cellKey,
		claimAllowed,
		computeRegions,
		fits,
		growsOwnArea,
		shapeKey,
		frontier,
		labelPoint,
		parseKey,
		placeCard,
		regionColor,
		regionOf,
		territoryScores,
		type CardType,
		type Cells
	} from './board';

	let { roomId }: { roomId: string } = $props();

	interface PlacedMove {
		type: 'card_placed';
		player_id: string;
		card: CardType;
		row: number;
		col: number;
		rot: number;
		area: number | null;
		penalty: number;
		takeovers: { winner: string; losers: string[] }[];
		score_deltas: Record<string, number>;
	}
	interface DiscardedMove {
		type: 'card_discarded';
		player_id: string;
		card: CardType;
		score_deltas: Record<string, number>;
	}

	interface FragmentoryState {
		cells?: Cells;
		hands?: Record<string, CardType>;
		deck_counts?: Record<CardType, number>;
		deck_size?: number;
		turn_order?: string[];
		current_player_id?: string | null;
		territory?: Record<string, number>;
		penalties?: Record<string, number>;
		area?: number;
		move_count?: number;
		last_move?: PlacedMove | DiscardedMove | null;
		finished?: boolean;
	}

	const REASONS: Record<string, string> = {
		not_your_turn: "It's not your turn.",
		does_not_fit: "The card doesn't fit there.",
		claim_not_allowed: 'You cannot occupy that area.',
		invalid_area: 'That area does not exist.',
		card_fits: 'Your card still fits somewhere.',
		no_card: 'You have no card.',
		finished: 'The game is over.'
	};
	const GRAY_FILL = '#8a857c';
	const INK = '#1a1917';

	const DECK_TOTAL = Object.values(DECK_COUNTS).reduce((a, b) => a + b, 0);

	const client = new RoomSocketClient();

	let room = $derived(client.room);
	let gameState = $derived((room?.state ?? {}) as FragmentoryState);
	let players = $derived<PlayerInfo[]>(room?.players ?? []);
	let isHost = $derived(room?.host_player_id === profile.playerId);
	let isPlaying = $derived(room?.status === 'playing');
	let isFinished = $derived(room?.status === 'finished');

	let cells = $derived<Cells>(gameState.cells ?? {});
	let hands = $derived<Record<string, CardType>>(gameState.hands ?? {});
	let myCard = $derived<CardType | null>(hands[profile.playerId] ?? null);
	let currentPlayerId = $derived(gameState.current_player_id ?? null);
	let isMyTurn = $derived(isPlaying && currentPlayerId === profile.playerId && myCard !== null);
	let lastMove = $derived(gameState.last_move ?? null);
	let deckSize = $derived(gameState.deck_size ?? 0);
	let cardsLeft = $derived(deckSize + Object.keys(hands).length);

	// --- Pending move (my turn only)
	let rot = $state(0);
	let pending = $state<{ row: number; col: number } | null>(null);
	let claim = $state<number | null>(null);
	let message = $state<string | null>(null);
	let showDeck = $state(false);
	const MIN_CELL = 28;
	const MAX_CELL = 140;
	const MARGIN = 2;
	let cellSize = $state(64);
	let viewW = $state(0);
	let viewH = $state(0);
	let scrollEl = $state<HTMLDivElement | null>(null);
	let barH = $state(0);

	let spots = $derived.by(() => {
		if (!isMyTurn || !myCard) return [] as { row: number; col: number; rots: number[] }[];
		const card = myCard;
		return frontier(cells)
			.map(([row, col]) => ({
				row,
				col,
				rots: [0, 1, 2, 3].filter((r) => fits(cells, row, col, card, r))
			}))
			.filter((s) => s.rots.length > 0);
	});
	let canDiscard = $derived(isMyTurn && spots.length === 0);

	let regionsNow = $derived(computeRegions(cells));
	let claimOptions = $derived.by(() => {
		if (!isMyTurn || !myCard || !pending) return [] as boolean[];
		const card = myCard;
		const p = pending;
		return CARD_TYPES[card].areas.map((_, i) =>
			claimAllowed(cells, regionsNow, p.row, p.col, card, rot, i, profile.playerId)
		);
	});

	let growsMine = $derived(
		isMyTurn && myCard !== null && pending !== null
			? growsOwnArea(cells, regionsNow, pending.row, pending.col, myCard, rot, profile.playerId)
			: false
	);

	let preview = $derived.by(() => {
		if (!isMyTurn || !myCard || !pending) return null;
		return placeCard(cells, pending.row, pending.col, myCard, rot, claim, profile.playerId);
	});

	let shownCells = $derived<Cells>(preview?.cells ?? cells);
	let shownRegions = $derived(preview ? computeRegions(shownCells) : regionsNow);

	// Each player's most recently placed card (key -> player id).
	let lastCardOf = $derived.by(() => {
		const latest = new Map<string, { key: string; move: number }>();
		for (const [key, cell] of Object.entries(cells)) {
			if (!cell.placed_by) continue;
			const prev = latest.get(cell.placed_by);
			if (!prev || cell.move > prev.move) latest.set(cell.placed_by, { key, move: cell.move });
		}
		return new Map([...latest].map(([pid, { key }]) => [key, pid]));
	});

	function totals(territory: Record<string, number>, penalties: Record<string, number>) {
		const out: Record<string, number> = {};
		for (const id of new Set([...Object.keys(territory), ...Object.keys(penalties)]))
			out[id] = (territory[id] ?? 0) - (penalties[id] ?? 0);
		return out;
	}

	let previewScores = $derived.by(() => {
		if (!preview) return null;
		const penalties = gameState.penalties ?? {};
		const before = totals(territoryScores(cells), penalties);
		const after = totals(territoryScores(preview.cells), {
			...penalties,
			[profile.playerId]: (penalties[profile.playerId] ?? 0) + preview.penalty
		});
		const out: Record<string, number> = {};
		for (const p of players) {
			const delta = (after[p.player_id] ?? 0) - (before[p.player_id] ?? 0);
			if (delta !== 0) out[p.player_id] = p.score + delta;
		}
		return out;
	});

	// --- Board geometry: bounding box of the cards plus one ring for new cards.
	// Based on the real cards so a pending card (always in the outer ring) does not shift the view.
	let box = $derived(boundingBox(Object.keys(cells)) ?? { minR: 0, maxR: 0, minC: 0, maxC: 0 });
	let usedBox = $derived(boundingBox(Object.keys(shownCells)));
	// Visible region: the cards plus a margin, padded so the board fills the whole canvas.
	let view = $derived.by(() => {
		let minR = box.minR - MARGIN;
		let minC = box.minC - MARGIN;
		let rows = box.maxR - box.minR + 1 + 2 * MARGIN;
		let cols = box.maxC - box.minC + 1 + 2 * MARGIN;
		const needRows = Math.ceil(viewH / cellSize);
		const needCols = Math.ceil(viewW / cellSize);
		if (rows < needRows) {
			minR -= Math.floor((needRows - rows) / 2);
			rows = needRows;
		}
		if (cols < needCols) {
			minC -= Math.floor((needCols - cols) / 2);
			cols = needCols;
		}
		return { minR, minC, rows, cols };
	});

	function scrollToCells(coords: [number, number][], smooth: boolean) {
		const el = scrollEl;
		if (!el || coords.length === 0) return;
		const rows = coords.map(([r]) => r);
		const cols = coords.map(([, c]) => c);
		const midRow = (Math.min(...rows) + Math.max(...rows) + 1) / 2;
		const midCol = (Math.min(...cols) + Math.max(...cols) + 1) / 2;
		el.scrollTo({
			left: (midCol - view.minC) * cellSize - el.clientWidth / 2,
			top: (midRow - view.minR) * cellSize - el.clientHeight / 2,
			behavior: smooth ? 'smooth' : 'auto'
		});
	}

	// Center the board when the game shows up, and follow each new card.
	let centeredFor = $state<string | null>(null);
	$effect(() => {
		const marker = `${room?.status}:${gameState.move_count ?? 0}`;
		if (!scrollEl || (!isPlaying && !isFinished)) return;
		if (marker === centeredFor) return;
		const first = centeredFor === null;
		centeredFor = marker;
		const target: [number, number][] =
			!first && lastMove?.type === 'card_placed'
				? [[lastMove.row, lastMove.col]]
				: Object.keys(cells).map(parseKey);
		tick().then(() => scrollToCells(target.length ? target : [[0, 0]], !first));
	});

	function playerColor(id: string): string {
		return resolvePlayerColor(id, profile.playerId, profile.primaryColor, players);
	}

	function playerName(id: string | null | undefined): string {
		if (!id) return '';
		if (id === profile.playerId) return 'You';
		return players.find((p) => p.player_id === id)?.name ?? 'Someone';
	}

	function areaStyle(key: string, idx: number): { fill: string; opacity: number } {
		const region = regionOf(shownRegions, key, idx);
		const color = regionColor(region);
		if (color === null) return { fill: 'none', opacity: 0 };
		if (color === GRAY) return { fill: GRAY_FILL, opacity: 0.45 };
		if (region.cards.size < 2) return { fill: playerColor(color), opacity: 0.22 };
		return { fill: playerColor(color), opacity: region.enclosed ? 0.88 : 0.5 };
	}

	function formatPoints(points: number): string {
		return points > 0 ? `+${points}` : `${points}`.replace('-', '−');
	}

	/** Points of a move, with the area penalty split out: "+3 (+6 −3)". */
	function movePoints(move: PlacedMove | DiscardedMove): string {
		if (move.type === 'card_discarded') return 'discarded';
		const total = move.score_deltas?.[move.player_id] ?? 0;
		if (!move.penalty) return formatPoints(total);
		return `${formatPoints(total)} (${formatPoints(total + move.penalty)} ${formatPoints(-move.penalty)})`;
	}

	function describeMove(move: PlacedMove | DiscardedMove): string {
		return `${playerName(move.player_id)}: ${movePoints(move)}`;
	}


	let turnNotificationHint = $derived.by(() => {
		if (!lastMove) return isPlaying ? `Fragmentory #${roomId} has started — your move!` : '';
		return `${describeMove(lastMove)}. Your move!`;
	});

	let winners = $derived.by(() => {
		if (players.length === 0) return [];
		const maxScore = Math.max(...players.map((p) => p.score));
		return players.filter((p) => p.score === maxScore);
	});

	function chooseSpot(row: number, col: number, rots: number[]) {
		message = null;
		if (pending && pending.row === row && pending.col === col) {
			rotate();
			return;
		}
		pending = { row, col };
		if (!rots.includes(rot)) rot = rots[0];
		claim = null;
	}

	function rotate() {
		if (!myCard) return;
		message = null;
		const card = myCard;
		if (!pending) {
			const current = shapeKey(card, rot);
			for (let step = 1; step < 4; step++) {
				if (shapeKey(card, (rot + step) % 4) !== current) {
					rot = (rot + step) % 4;
					break;
				}
			}
			return;
		}
		const p = pending;
		const current = shapeKey(card, rot);
		for (let step = 1; step < 4; step++) {
			const r = (rot + step) % 4;
			if (shapeKey(card, r) !== current && fits(cells, p.row, p.col, card, r)) {
				rot = r;
				break;
			}
		}
	}

	function toggleClaim(idx: number) {
		if (!pending || !claimOptions[idx]) return;
		claim = claim === idx ? null : idx;
	}

	function place() {
		if (!isMyTurn || !pending || !preview) return;
		client.sendAction({ type: 'place', row: pending.row, col: pending.col, rot, area: claim });
		pending = null;
		claim = null;
	}

	function discard() {
		if (!canDiscard) return;
		client.sendAction({ type: 'discard' });
	}

	function endGame() {
		if (!isHost) return;
		if (window.confirm('End the game now and show the final scores?')) client.endGame();
	}

	$effect(() => {
		// A claim may become invalid after rotating.
		if (claim !== null && claimOptions[claim] === false) claim = null;
	});

	let moveCount = $derived(gameState.move_count ?? 0);

	$effect(() => {
		// New board state or turn: drop the pending move.
		void moveCount;
		void currentPlayerId;
		pending = null;
		claim = null;
	});

	onMount(() => {
		profile.init();
		client.connect({
			gameSlug: 'fragmentory',
			roomId,
			playerId: profile.playerId,
			name: profile.name,
			color: profile.primaryColor
		});
		const unsub = client.onEvent((ev: ServerEvent) => {
			if (ev.type === 'action_rejected' && ev.player_id === profile.playerId) {
				message = REASONS[ev.reason] ?? null;
			} else if (ev.type === 'card_placed' || ev.type === 'card_discarded') {
				message = null;
			}
		});
		return () => {
			unsub();
			client.disconnect();
		};
	});
</script>

{#snippet cardSvg(type: CardType, r: number, size: number, interactive: boolean)}
	<svg viewBox="-0.04 -0.04 1.08 1.08" width={size} height={size} class="block" aria-hidden={!interactive}>
		<rect x="0" y="0" width="1" height="1" rx="0.04" fill="#fff" stroke={INK} stroke-width="0.03" />
		<g transform="rotate({r * 90} .5 .5)">
			{#each CARD_SHAPES[type].areas as d, i (i)}
				{#if interactive && pending && claim === i}
					<path {d} fill={profile.primaryColor} fill-opacity="0.75" />
				{/if}
			{/each}
			<path d={CARD_SHAPES[type].lines} stroke={INK} stroke-width="0.07" stroke-linecap="round" fill="none" />
			{#if type === 'end'}
				<circle cx=".5" cy=".45" r=".06" fill={INK} />
			{/if}
		</g>
		{#if interactive}
			<rect
				x="0"
				y="0"
				width="1"
				height="1"
				fill="transparent"
				role="button"
				tabindex="0"
				aria-label="Rotate card"
				class="cursor-pointer"
				onclick={rotate}
				onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && rotate()}
			/>
		{/if}
		{#if interactive && pending}
			{@render claimMarks(type, r, 0.08)}
		{/if}
	</svg>
{/snippet}

<!-- Empty circles on the areas that may be occupied; the chosen one is filled in. -->
{#snippet claimMarks(type: CardType, r: number, radius: number)}
	{#each CARD_SHAPES[type].areas as _, i (i)}
		{#if claimOptions[i]}
			{@const [lx, ly] = labelPoint(type, r, i)}
			<circle
				cx={lx}
				cy={ly}
				r={radius}
				role="button"
				tabindex="-1"
				aria-label="Occupy area {i + 1}"
				aria-pressed={claim === i}
				class="claim-mark cursor-pointer"
				fill={claim === i ? profile.primaryColor : '#fff'}
				stroke={INK}
				stroke-width={radius * 0.3}
				onclick={(e) => {
					e.stopPropagation();
					toggleClaim(i);
				}}
				onkeydown={() => {}}
			/>
		{/if}
	{/each}
{/snippet}

<RoomShell {client} {roomId} title="Fragmentory" subtitleItems={isPlaying ? [`${cardsLeft} cards left`] : []}>
	{#snippet headerActions()}
		<TurnNotificationBell
			{roomId}
			playerId={profile.playerId}
			gameSlug="fragmentory"
			gameTitle="Fragmentory"
			{isMyTurn}
			{isPlaying}
			turnHint={turnNotificationHint}
		/>
	{/snippet}

	{#snippet configSlot()}
		<div class="space-y-3 text-sm">
			<p>
				Take turns placing square cards. Rotate your card so every side matches its neighbours
				(line to line, no line to no line), then optionally occupy one of its areas in your colour.
			</p>
			<ul class="list-disc space-y-1 pl-5 text-xs text-[#6e6a63]">
				<li>
					You may only occupy a new area if the move does not grow one of your areas, and it may
					not touch another player’s area.
				</li>
				<li>Unclaimed areas take the colour of whatever they touch.</li>
				<li>
					When two colours meet, the bigger one takes over; a tie turns gray until one colour leads
					by two cards.
				</li>
				<li>
					Every card of your areas scores 1 point; single-card areas score nothing, areas fully
					enclosed by lines score double.
				</li>
				<li>Growing the used rectangle costs 1 point per new unit.</li>
				<li>The game ends when all 42 cards are played.</li>
			</ul>
		</div>
	{/snippet}

	<div class="mx-auto flex w-full max-w-[720px] flex-1 flex-col gap-3 pb-44">
		<PlayerBar
			{players}
			hostPlayerId={room?.host_player_id ?? ''}
			myPlayerId={profile.playerId}
			myColor={profile.primaryColor}
			showTurnBadge={isPlaying}
			{currentPlayerId}
			statusText={`${cardsLeft} cards left · area ${preview ? boundingArea(preview.cells) : (gameState.area ?? 1)}`}
			{previewScores}
			onRemovePlayer={(id) => client.removePlayer(id)}
		/>

		{#if isFinished}
			<ScribblyBox seed={67} class="bg-[#faf8f4] p-4 text-center">
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
						<ScribblyButton onclick={() => client.returnToLobby()} variant="primary">New Round</ScribblyButton>
					{:else}
						<p class="text-sm text-[#6e6a63]">Waiting for the host to start a new round…</p>
					{/if}
				</div>
			</ScribblyBox>
		{/if}

		{#if isPlaying || isFinished}
			<div class="flex min-h-[1.5rem] items-center justify-between gap-2 text-sm" aria-live="polite">
				<span class="min-w-0">
					{#if message}
						<span class="text-[#b5523b]">{message}</span>
					{:else if lastMove}
						<span class="font-mono-num text-[#6e6a63]">
							<span class="font-sans font-semibold" style="color: {playerColor(lastMove.player_id)}"
								>{playerName(lastMove.player_id)}</span
							>
							{movePoints(lastMove)}
						</span>
					{:else if isPlaying}
						<span class="text-[#6e6a63]">
							{currentPlayerId === profile.playerId ? 'You start.' : `${playerName(currentPlayerId)} starts.`}
						</span>
					{/if}
				</span>
				<button
					type="button"
					onclick={() => (showDeck = true)}
					class="shrink-0 cursor-pointer rounded border-[1.5px] border-[#1a1917] px-2 py-0.5 text-xs font-semibold hover:bg-[#f2eee6]"
				>
					Deck · {deckSize}
				</button>
			</div>

			<!-- The board -->
			<ZoomBoard
				bind:cellSize
				bind:el={scrollEl}
				bind:viewW
				bind:viewH
				originX={view.minC}
				originY={view.minR}
				minCell={MIN_CELL}
				maxCell={MAX_CELL}
				reserveBelow={isPlaying ? barH : 0}
				ariaLabel="Fragmentory board"
			>
				<svg
					viewBox="{view.minC} {view.minR} {view.cols} {view.rows}"
					width={view.cols * cellSize}
					height={view.rows * cellSize}
					class="block select-none"
					role="group"
					aria-label="Board"
				>
					{#if usedBox}
						<rect
							x={usedBox.minC - 0.06}
							y={usedBox.minR - 0.06}
							width={usedBox.maxC - usedBox.minC + 1.12}
							height={usedBox.maxR - usedBox.minR + 1.12}
							fill="none"
							stroke={INK}
							stroke-opacity="0.35"
							stroke-width="0.03"
							stroke-dasharray="0.12 0.08"
							class="used-box"
						/>
					{/if}

					{#each spots as spot (cellKey(spot.row, spot.col))}
						{@const isPending = pending?.row === spot.row && pending?.col === spot.col}
						{#if !isPending}
							<rect
								x={spot.col + 0.08}
								y={spot.row + 0.08}
								width="0.84"
								height="0.84"
								rx="0.06"
								role="button"
								tabindex="0"
								aria-label="Place card at row {spot.row}, column {spot.col}"
								class="spot cursor-pointer"
								fill={INK}
								fill-opacity="0.1"
								onclick={() => chooseSpot(spot.row, spot.col, spot.rots)}
								onkeydown={(e) =>
									(e.key === 'Enter' || e.key === ' ') && chooseSpot(spot.row, spot.col, spot.rots)}
							/>
						{/if}
					{/each}

					{#each Object.entries(shownCells) as [key, cell] (key)}
						{@const [r, c] = parseKey(key)}
						{@const isPending = pending !== null && pending.row === r && pending.col === c}
						{@const isLast =
							lastMove?.type === 'card_placed' && lastMove.row === r && lastMove.col === c}
						<g
							transform="translate({c} {r})"
							class="{isPending ? 'pending-card' : ''} {isLast && !preview ? 'last-card' : ''}"
						>
							<rect x="0" y="0" width="1" height="1" fill="#fff" />
							<g transform="rotate({cell.rot * 90} .5 .5)">
								{#each CARD_SHAPES[cell.type].areas as d, i (i)}
									{@const style = areaStyle(key, i)}
									<path {d} fill={style.fill} fill-opacity={style.opacity} class="area-fill" />
								{/each}
								{#if !isPending && lastCardOf.has(key)}
									<!-- The grid line of this card in the colour of the player whose latest card it is, under the card's lines. -->
									<rect
										x="0.0075"
										y="0.0075"
										width="0.985"
										height="0.985"
										fill="none"
										stroke={playerColor(lastCardOf.get(key)!)}
										stroke-width="0.015"
										pointer-events="none"
									/>
								{/if}
								<path
									d={CARD_SHAPES[cell.type].lines}
									stroke={INK}
									stroke-width="0.06"
									stroke-linecap="round"
									fill="none"
									pointer-events="none"
								/>
								{#if cell.type === 'end'}
									<circle cx=".5" cy=".45" r=".05" fill={INK} pointer-events="none" />
								{/if}
							</g>
							{#if isPending && myCard}
								<!-- Tap the placed card to rotate it; tap a circle to occupy an area. -->
								<rect
									x="0"
									y="0"
									width="1"
									height="1"
									fill="transparent"
									role="button"
									tabindex="-1"
									aria-label="Rotate card"
									class="cursor-pointer"
									onclick={rotate}
									onkeydown={() => {}}
								/>
								{@render claimMarks(myCard, rot, 0.09)}
							{/if}
							{#if cell.claimed !== null && cell.placed_by && !isPending}
								<!-- Small mark where a player claimed an area; the pending claim shows as area fill only. -->
								{@const [lx, ly] = labelPoint(cell.type, cell.rot, cell.claimed)}
								<circle
									cx={lx}
									cy={ly}
									r="0.035"
									fill={INK}
									fill-opacity="0.45"
									pointer-events="none"
								/>
							{/if}
							<rect
								x="0"
								y="0"
								width="1"
								height="1"
								fill="none"
								stroke={INK}
								stroke-opacity={isPending ? 0.9 : lastCardOf.has(key) ? 0 : 0.18}
								stroke-width={isPending ? 0.05 : 0.015}
								stroke-dasharray={isPending ? '0.1 0.06' : 'none'}
								pointer-events="none"
							/>
						</g>
					{/each}

					{#if pending && !preview && myCard}
						<!-- Invalid rotation at the chosen spot (should not happen): show an outline. -->
						<rect x={pending.col} y={pending.row} width="1" height="1" fill="none" stroke="#b5523b" stroke-width="0.05" />
					{/if}
				</svg>
			</ZoomBoard>

			<!-- Everyone's cards are public -->
			{#if (gameState.turn_order ?? []).length > 1}
				<div class="flex flex-wrap gap-x-4 gap-y-1 text-xs">
					{#each (gameState.turn_order ?? []).filter((id) => id !== profile.playerId) as pid (pid)}
						<div class="flex items-center gap-1.5">
							<span class="font-semibold" style="color: {playerColor(pid)}">{playerName(pid)}</span>
							{#if hands[pid]}
								<CardIcon type={hands[pid]} size={22} />
								<span class="text-[#6e6a63]">{CARD_LABELS[hands[pid]]}</span>
							{:else}
								<span class="text-[#6e6a63]">no card</span>
							{/if}
						</div>
					{/each}
				</div>
			{/if}

			<p class="text-xs text-[#6e6a63]">
				Pale: single-card area (no points) · solid: 1 point per card · dark: enclosed, 2 points per
				card · gray: tie. The dashed frame is the used area — growing it costs points.
			</p>

			{#if isHost && isPlaying}
				<div class="flex justify-center">
					<button
						type="button"
						onclick={endGame}
						class="cursor-pointer text-xs text-[#6e6a63] underline hover:text-[#1a1917]"
					>
						End game &amp; show scores
					</button>
				</div>
			{/if}
		{/if}
	</div>

	{#if isPlaying}
		<!-- My card, sticky at the bottom -->
		<div
			bind:clientHeight={barH}
			class="fixed inset-x-0 bottom-0 z-20 border-t-[2px] border-[#1a1917] bg-[#faf8f4]/95 px-3 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] backdrop-blur"
		>
			<div class="mx-auto flex max-w-[720px] items-center gap-3">
				<div class="shrink-0">
					{#if myCard}
						<div class="card-preview" style="--rot: {rot * 90}deg">
							{@render cardSvg(myCard, rot, 92, isMyTurn)}
						</div>
					{:else}
						<div class="flex h-[92px] w-[92px] items-center justify-center text-xs text-[#6e6a63]">
							no card
						</div>
					{/if}
				</div>
				<div class="flex min-w-0 flex-1 flex-col gap-2">
					<div class="text-xs font-semibold">
						{#if isMyTurn}
							{#if canDiscard}
								Your {CARD_LABELS[myCard!]} fits nowhere — discard it.
							{:else if !pending}
								Your turn — tap a shaded spot on the board.
							{:else if !claimOptions.some(Boolean)}
								No new area here{growsMine ? ' — this move grows your area' : ''}. Place it?
							{:else if claim === null}
								Tap the card to rotate, a circle to occupy that area (optional), then place.
							{:else}
								Ready to place.
							{/if}
						{:else if currentPlayerId}
							{playerName(currentPlayerId)}'s turn{myCard ? ` · your card: ${CARD_LABELS[myCard]}` : ''}
						{/if}
					</div>
					<div class="flex flex-wrap gap-2">
						<button
							type="button"
							disabled={!isMyTurn || canDiscard}
							onclick={rotate}
							class="action-btn"
							aria-label="Rotate card"
						>
							↻ Rotate
						</button>
						{#if canDiscard}
							<button type="button" onclick={discard} class="action-btn action-primary">Discard</button>
						{:else}
							<button
								type="button"
								disabled={!isMyTurn || !preview}
								onclick={place}
								class="action-btn action-primary"
							>
								Place{#if previewScores?.[profile.playerId] !== undefined}
									{@const me = players.find((p) => p.player_id === profile.playerId)}
									<span class="font-mono-num ml-1 font-normal opacity-80">
										{formatPoints((previewScores[profile.playerId] ?? 0) - (me?.score ?? 0))}
									</span>
								{/if}
							</button>
						{/if}
					</div>
				</div>
			</div>
		</div>
	{/if}

	{#if showDeck}
		<div
			class="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4"
			role="presentation"
			onclick={(e) => e.target === e.currentTarget && (showDeck = false)}
		>
			<div class="w-full max-w-sm rounded border-[2px] border-[#1a1917] bg-[#faf8f4] p-4" role="dialog" aria-modal="true" aria-label="Cards left in the deck">
				<div class="mb-3 flex items-center justify-between">
					<h2 class="font-hand text-xl">Deck · {deckSize}/{DECK_TOTAL}</h2>
					<button type="button" class="cursor-pointer text-xl leading-none" aria-label="Close" onclick={() => (showDeck = false)}>×</button>
				</div>
				<ul class="space-y-2">
					{#each CARD_ORDER as type (type)}
						<li class="flex items-center gap-3">
							<CardIcon {type} size={36} />
							<span class="flex-1 text-sm">{CARD_LABELS[type]}</span>
							<span class="font-mono-num text-right">
								<span class="font-semibold">{gameState.deck_counts?.[type] ?? 0}</span><span
									class="text-[#6e6a63]">/{DECK_COUNTS[type]}</span
								>
							</span>
						</li>
					{/each}
				</ul>
				<p class="mt-3 text-xs text-[#6e6a63]">Cards in players’ hands are not counted.</p>
			</div>
		</div>
	{/if}
</RoomShell>

<style>
	.action-btn {
		cursor: pointer;
		border-radius: 0.25rem;
		border: 1.5px solid #1a1917;
		padding: 0.4rem 0.8rem;
		font-size: 0.85rem;
		font-weight: 600;
		background: #faf8f4;
		transition: background-color 0.15s;
	}
	.action-btn:not(:disabled):hover {
		background: #f2eee6;
	}
	.action-btn:disabled {
		cursor: default;
		opacity: 0.4;
	}
	.action-primary {
		background: #1a1917;
		color: #faf8f4;
	}
	.action-primary:not(:disabled):hover {
		background: #33312d;
	}
	.spot {
		transition: fill-opacity 0.15s;
	}
	/* Chrome draws focus rings of SVG paths around the full arc circle; use fill feedback instead. */
	svg [role='button'] {
		outline: none;
	}
	.spot:focus-visible {
		fill-opacity: 0.22;
	}
	.spot:hover {
		fill-opacity: 0.22;
	}
	.area-fill {
		transition:
			fill 0.35s,
			fill-opacity 0.35s;
	}
	.pending-card {
		animation: hover-in 0.25s ease-out;
	}
	.last-card {
		animation: settle 0.7s ease-out;
	}
	@keyframes hover-in {
		from {
			opacity: 0.3;
		}
		to {
			opacity: 1;
		}
	}
	@keyframes settle {
		0% {
			opacity: 0.4;
		}
		100% {
			opacity: 1;
		}
	}
	.card-preview :global(svg) {
		transition: transform 0.2s;
	}
	.used-box {
		transition: all 0.3s;
	}
	@media (prefers-reduced-motion: reduce) {
		.pending-card,
		.last-card {
			animation: none;
		}
	}
</style>
