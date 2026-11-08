<script lang="ts">
	import { onMount } from 'svelte';
	import { resolvePlayerColor } from '$lib/core/color';
	import PlayerBar from '$lib/core/components/PlayerBar.svelte';
	import RoomShell from '$lib/core/components/RoomShell.svelte';
	import ScribblyBox from '$lib/core/components/ScribblyBox.svelte';
	import ScribblyButton from '$lib/core/components/ScribblyButton.svelte';
	import TurnNotificationBell from '$lib/core/components/TurnNotificationBell.svelte';
	import { profile } from '$lib/core/profile.svelte';
	import { RoomSocketClient, type PlayerInfo, type ServerEvent } from '$lib/core/ws.svelte';

	let { roomId }: { roomId: string } = $props();

	type Category = 'city' | 'landmark' | 'event';
	type EndCondition = 'rounds' | 'points' | 'failed_round';

	interface Card {
		id: string;
		category: Category;
		points: number;
		name: string;
		country?: string;
		lat?: number;
		lon?: number;
		description?: string;
		wikipedia?: string;
		player_id?: string | null;
	}

	interface PlacedMove {
		type: 'location_placed';
		player_id: string;
		correct: boolean;
		points: number;
		factor: number;
		card: Card;
		slot: number | null;
	}

	interface SkippedMove {
		type: 'turn_skipped';
		player_id: string;
	}

	interface NorthSouthState {
		language?: string;
		continent?: string;
		categories?: Category[];
		timed?: boolean;
		end_condition?: EndCondition;
		end_target?: number;
		axis?: Card[];
		hands?: Record<string, Card[]>;
		discarded?: Card[];
		discarded_count?: number;
		turn_order?: string[];
		current_player_id?: string | null;
		turn_started_at?: string;
		round?: number;
		finished?: boolean;
		last_move?: PlacedMove | SkippedMove | null;
	}

	const client = new RoomSocketClient();

	const LANGUAGES = [
		{ code: 'de', label: 'Deutsch' },
		{ code: 'en', label: 'English' }
	];
	const CONTINENTS = [
		{ code: 'world', label: 'World' },
		{ code: 'europe', label: 'Europe' },
		{ code: 'asia', label: 'Asia' },
		{ code: 'africa', label: 'Africa' },
		{ code: 'north_america', label: 'N. America' },
		{ code: 'south_america', label: 'S. America' },
		{ code: 'oceania', label: 'Oceania' }
	];
	const CATEGORY_INFO: Record<Category, { label: string; color: string }> = {
		city: { label: 'City', color: '#3b6ea5' },
		landmark: { label: 'Landmark', color: '#4f8a4b' },
		event: { label: 'Event', color: '#b5523b' }
	};
	const ALL_CATEGORIES: Category[] = ['city', 'landmark', 'event'];
	const END_CONDITIONS: { code: EndCondition; label: string; hint: string; targets: number[] }[] =
		[
			{ code: 'rounds', label: 'Rounds', hint: 'Ends after this many rounds.', targets: [5, 10, 20] },
			{ code: 'points', label: 'Points', hint: 'First player to reach this score wins.', targets: [10, 20, 50] },
			{
				code: 'failed_round',
				label: 'All miss',
				hint: 'Ends after a round in which every player skipped or misplaced.',
				targets: []
			}
		];
	const SPEED_STEPS: [number, number][] = [
		[10, 2],
		[20, 1.5]
	];
	const REASONS: Record<string, string> = {
		not_your_turn: "It's not your turn.",
		not_in_hand: 'That card is not in your hand.',
		invalid_slot: 'That spot no longer exists.',
		finished: 'The game is over.'
	};

	let room = $derived(client.room);
	let gameState = $derived((room?.state ?? {}) as NorthSouthState);
	let players = $derived<PlayerInfo[]>(room?.players ?? []);
	let isHost = $derived(room?.host_player_id === profile.playerId);
	let isPlaying = $derived(room?.status === 'playing');

	let cfgLanguage = $derived(String(room?.config?.language ?? 'de'));
	let cfgContinent = $derived(String(room?.config?.continent ?? 'world'));
	let cfgCategories = $derived<Category[]>(
		Array.isArray(room?.config?.categories) ? (room?.config?.categories as Category[]) : ALL_CATEGORIES
	);
	let cfgTimed = $derived(Boolean(room?.config?.timed));
	let cfgEnd = $derived((room?.config?.end_condition ?? 'rounds') as EndCondition);
	let cfgTarget = $derived(Number(room?.config?.end_target ?? 10));

	let continent = $derived(gameState.continent ?? cfgContinent);
	let timed = $derived(gameState.timed ?? cfgTimed);
	let endCondition = $derived(gameState.end_condition ?? cfgEnd);
	let endTarget = $derived(gameState.end_target ?? cfgTarget);
	let axis = $derived<Card[]>(gameState.axis ?? []);
	let hands = $derived<Record<string, Card[]>>(gameState.hands ?? {});
	let myHand = $derived<Card[]>(hands[profile.playerId] ?? []);
	let currentPlayerId = $derived(gameState.current_player_id ?? null);
	let isMyTurn = $derived(isPlaying && currentPlayerId === profile.playerId);
	let lastMove = $derived(gameState.last_move ?? null);
	let lastPlacedId = $derived(
		lastMove?.type === 'location_placed' && lastMove.correct ? lastMove.card.id : null
	);

	let selectedId = $state<string | null>(null);
	let message = $state<string | null>(null);
	let drawSentFor = $state<string | null>(null);
	let clockOffsetMs = $state(0);
	let nowMs = $state(Date.now());

	let selectedCard = $derived(myHand.find((c) => c.id === selectedId) ?? null);
	let canPlace = $derived(isMyTurn && selectedCard !== null);

	// Slots from north (top) to south (bottom): slot i lies between axis[i-1] and axis[i].
	let rows = $derived.by(() => {
		const out: ({ kind: 'slot'; slot: number } | { kind: 'card'; card: Card })[] = [];
		for (let i = axis.length; i >= 0; i--) {
			out.push({ kind: 'slot', slot: i });
			if (i > 0) out.push({ kind: 'card', card: axis[i - 1] });
		}
		return out;
	});

	let elapsedSeconds = $derived.by(() => {
		if (!gameState.turn_started_at) return 0;
		return Math.max(0, (nowMs + clockOffsetMs - Date.parse(gameState.turn_started_at)) / 1000);
	});
	let speed = $derived.by(() => {
		for (const [limit, factor] of SPEED_STEPS) {
			if (elapsedSeconds <= limit) return { factor, left: Math.ceil(limit - elapsedSeconds), limit };
		}
		return { factor: 1, left: 0, limit: 0 };
	});

	let continentLabel = $derived(CONTINENTS.find((c) => c.code === continent)?.label ?? 'World');
	let endSummary = $derived.by(() => {
		if (endCondition === 'points') return `${endTarget} pts`;
		if (endCondition === 'failed_round') return 'until all miss';
		return `${endTarget} rounds`;
	});
	let progressText = $derived.by(() => {
		if (endCondition === 'rounds') return `round ${gameState.round ?? 1}/${endTarget}`;
		if (endCondition === 'points') return `first to ${endTarget}`;
		return `round ${gameState.round ?? 1}`;
	});

	let winners = $derived.by(() => {
		if (players.length === 0) return [];
		const maxScore = Math.max(...players.map((p) => p.score));
		return players.filter((p) => p.score === maxScore);
	});

	let turnNotificationHint = $derived.by(() => {
		if (!lastMove) return isPlaying ? `North South Sort #${roomId} has started — your move!` : '';
		return `${describeMove(lastMove)} Your move!`;
	});

	function playerName(id: string | null | undefined): string {
		if (!id) return '';
		if (id === profile.playerId) return 'You';
		return players.find((p) => p.player_id === id)?.name ?? 'Someone';
	}

	function playerColor(id: string): string {
		return resolvePlayerColor(id, profile.playerId, profile.primaryColor, players);
	}

	function formatLat(lat: number | undefined): string {
		if (lat === undefined) return '';
		return `${Math.abs(lat).toFixed(1)}° ${lat >= 0 ? 'N' : 'S'}`;
	}

	function formatPoints(points: number): string {
		const rounded = Math.round(points * 100) / 100;
		return rounded > 0 ? `+${rounded}` : `${rounded}`.replace('-', '−');
	}

	function describeMove(move: PlacedMove | SkippedMove): string {
		const who = playerName(move.player_id);
		if (move.type === 'turn_skipped') return `${who} skipped.`;
		const bonus = move.correct && move.factor > 1 ? ` (×${move.factor})` : '';
		return `${who}: ${move.card.name} ${move.correct ? '✓' : '✗'} ${formatPoints(move.points)}${bonus}`;
	}

	function updateConfig(patch: Record<string, unknown>) {
		if (isHost) client.updateConfig(patch);
	}

	function toggleCategory(cat: Category) {
		const next = cfgCategories.includes(cat)
			? cfgCategories.filter((c) => c !== cat)
			: ALL_CATEGORIES.filter((c) => c === cat || cfgCategories.includes(c));
		if (next.length > 0) updateConfig({ categories: next });
	}

	function updateEnd(code: EndCondition) {
		const cond = END_CONDITIONS.find((c) => c.code === code)!;
		updateConfig({ end_condition: code, end_target: cond.targets[1] ?? 0 });
	}

	function selectCard(id: string) {
		message = null;
		selectedId = selectedId === id ? null : id;
	}

	function place(slot: number) {
		if (!canPlace || !selectedCard) return;
		client.sendAction({ type: 'place', location_id: selectedCard.id, slot });
		selectedId = null;
	}

	function endGame() {
		if (!isHost) return;
		if (window.confirm('End the game now and show the final scores?')) client.endGame();
	}

	function skip() {
		if (!isMyTurn) return;
		selectedId = null;
		client.sendAction({ type: 'skip' });
	}

	$effect(() => {
		if (room?.server_time) clockOffsetMs = Date.parse(room.server_time) - Date.now();
	});

	$effect(() => {
		if (!(isPlaying && timed)) return;
		const timer = setInterval(() => (nowMs = Date.now()), 250);
		return () => clearInterval(timer);
	});

	$effect(() => {
		// Players who joined mid-game have no hand yet; ask the server to deal one.
		const order = gameState.turn_order ?? [];
		const key = `${roomId}:${gameState.round ?? 0}`;
		if (
			isPlaying &&
			!gameState.finished &&
			order.includes(profile.playerId) &&
			!(profile.playerId in hands) &&
			drawSentFor !== key
		) {
			drawSentFor = key;
			client.sendAction({ type: 'draw_hand' });
		}
	});

	$effect(() => {
		// Drop a selection that is no longer in the hand (e.g. after a reconnect).
		if (selectedId && !myHand.some((c) => c.id === selectedId)) selectedId = null;
	});

	onMount(() => {
		profile.init();
		client.connect({
			gameSlug: 'north-south-sort',
			roomId,
			playerId: profile.playerId,
			name: profile.name,
			color: profile.primaryColor
		});
		const unsub = client.onEvent((ev: ServerEvent) => {
			if (ev.type === 'action_rejected' && ev.player_id === profile.playerId) {
				message = REASONS[ev.reason] ?? null;
			} else if (ev.type === 'location_placed' || ev.type === 'turn_skipped') {
				message = null;
			}
		});
		return () => {
			unsub();
			client.disconnect();
		};
	});
</script>

<RoomShell {client} {roomId} title="North South Sort" subtitleItems={[continentLabel, endSummary]}>
	{#snippet headerActions()}
		<TurnNotificationBell
			{roomId}
			playerId={profile.playerId}
			gameSlug="north-south-sort"
			gameTitle="North South Sort"
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
				<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">Play on</span>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
					{#each CONTINENTS as c (c.code)}
						<button
							type="button"
							disabled={!isHost}
							onclick={() => updateConfig({ continent: c.code })}
							class="cfg-btn {cfgContinent === c.code ? 'cfg-on' : 'cfg-off'}"
						>
							{c.label}
						</button>
					{/each}
				</div>
			</div>

			<div>
				<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">Cards</span>
				<div class="grid grid-cols-3 gap-2">
					{#each ALL_CATEGORIES as cat (cat)}
						<button
							type="button"
							disabled={!isHost}
							aria-pressed={cfgCategories.includes(cat)}
							onclick={() => toggleCategory(cat)}
							class="cfg-btn {cfgCategories.includes(cat) ? 'cfg-on' : 'cfg-off'}"
						>
							{CATEGORY_INFO[cat].label}
							<span class="font-mono-num opacity-70">
								{cat === 'city' ? 1 : cat === 'landmark' ? 2 : 3}
							</span>
						</button>
					{/each}
				</div>
			</div>

			<div class="grid grid-cols-2 gap-4">
				<div>
					<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">Names</span>
					<div class="grid grid-cols-2 gap-2">
						{#each LANGUAGES as lang (lang.code)}
							<button
								type="button"
								disabled={!isHost}
								onclick={() => updateConfig({ language: lang.code })}
								class="cfg-btn {cfgLanguage === lang.code ? 'cfg-on' : 'cfg-off'}"
							>
								{lang.label}
							</button>
						{/each}
					</div>
				</div>
				<div>
					<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">Speed bonus</span>
					<div class="grid grid-cols-2 gap-2">
						{#each [false, true] as value (value)}
							<button
								type="button"
								disabled={!isHost}
								onclick={() => updateConfig({ timed: value })}
								class="cfg-btn {cfgTimed === value ? 'cfg-on' : 'cfg-off'}"
							>
								{value ? 'On' : 'Off'}
							</button>
						{/each}
					</div>
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
							class="cfg-btn {cfgEnd === cond.code ? 'cfg-on' : 'cfg-off'}"
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
								onclick={() => updateConfig({ end_target: target })}
								class="cfg-btn font-mono-num px-3 py-1 {cfgTarget === target ? 'cfg-on' : 'cfg-off'}"
							>
								{target}
							</button>
						{/each}
						<span class="text-xs text-[#6e6a63]">{cond.hint}</span>
					</div>
				{/each}
			</div>

			<p class="border-t border-[#1a1917]/15 pt-3 text-xs text-[#6e6a63]">
				On your turn, pick one of your cards and place it north or south of the locations on the
				axis. Right: score its value{cfgTimed ? ' (×2 within 10 s, ×1.5 within 20 s)' : ''}. Wrong:
				lose its value, and the card stays hidden until the end.
			</p>
		</div>
	{/snippet}

	<div class="mx-auto flex w-full max-w-[640px] flex-1 flex-col gap-3 pb-40">
		<PlayerBar
			{players}
			hostPlayerId={room?.host_player_id ?? ''}
			myPlayerId={profile.playerId}
			myColor={profile.primaryColor}
			showTurnBadge={isPlaying}
			{currentPlayerId}
			statusText={progressText}
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
				{#if isHost}
					<div class="mt-3 flex justify-center gap-2">
						<ScribblyButton onclick={() => client.startGame()} variant="primary">
							Play Again
						</ScribblyButton>
						<ScribblyButton onclick={() => client.returnToLobby()}>Lobby</ScribblyButton>
					</div>
				{/if}
			</ScribblyBox>

			{#if (gameState.discarded ?? []).length > 0}
				<ScribblyBox seed={67} class="bg-[#faf8f4] p-3">
					<div class="font-hand mb-2 text-lg">Misplaced cards</div>
					<ul class="space-y-2">
						{#each gameState.discarded ?? [] as card (card.id)}
							<li class="flex items-start gap-2 text-sm">
								<span
									class="mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-full"
									style="background: {playerColor(card.player_id ?? '')}"
								></span>
								<div class="min-w-0 flex-1">
									<div class="font-semibold">
										{card.name}
										<span class="font-mono-num text-xs font-normal text-[#6e6a63]">
											{formatLat(card.lat)}
										</span>
									</div>
									<div class="text-xs text-[#6e6a63]">
										{card.country ? `${card.country} · ` : ''}{card.description}
										{#if card.wikipedia}
											<a href={card.wikipedia} target="_blank" rel="noopener" class="underline">Wiki</a>
										{/if}
									</div>
								</div>
							</li>
						{/each}
					</ul>
				</ScribblyBox>
			{/if}
		{/if}

		{#if isPlaying || room?.status === 'finished'}
			<div class="min-h-[1.5rem] text-center text-sm" aria-live="polite">
				{#if message}
					<span class="text-[#b5523b]">{message}</span>
				{:else if lastMove}
					<span
						class={lastMove.type === 'location_placed'
							? lastMove.correct
								? 'text-[#4f8a4b]'
								: 'text-[#b5523b]'
							: 'text-[#6e6a63]'}
					>
						{describeMove(lastMove)}
					</span>
				{:else if isPlaying}
					<span class="text-[#6e6a63]">
						{currentPlayerId === profile.playerId ? 'You start.' : `${playerName(currentPlayerId)} starts.`}
					</span>
				{/if}
			</div>

			<!-- The axis: north at the top -->
			<div class="relative border-[2px] border-[#1a1917] bg-[#faf8f4]">
				<div class="font-hand absolute top-1 left-2 text-sm text-[#6e6a63]">N ↑</div>
				<div class="font-hand absolute bottom-1 left-2 text-sm text-[#6e6a63]">S ↓</div>
				<ol class="relative max-h-[min(62vh,620px)] overflow-y-auto px-3 py-6" aria-label="North–south axis">
					{#each rows as row (row.kind === 'slot' ? `s${row.slot}` : `c${row.card.id}`)}
						{#if row.kind === 'slot'}
							<li class="relative flex justify-center">
								{#if canPlace}
									<button
										type="button"
										onclick={() => place(row.slot)}
										class="slot-btn my-1 w-full cursor-pointer rounded border-[1.5px] border-dashed border-[#1a1917]/60 py-1.5 text-xs font-semibold text-[#1a1917] transition hover:bg-[#1a1917] hover:text-[#faf8f4]"
										aria-label="Place {selectedCard?.name} here"
									>
										place here
									</button>
								{:else}
									<div class="h-2"></div>
								{/if}
							</li>
						{:else}
							{@const card = row.card}
							<li
								class="axis-card relative flex items-start gap-2 rounded border-[1.5px] border-[#1a1917] bg-white/70 px-2.5 py-1.5
								{lastPlacedId === card.id ? 'last-placed' : ''}"
							>
								<span
									class="mt-1.5 h-3 w-3 shrink-0 rounded-full border-[1.5px] border-[#1a1917]"
									style="background: {card.player_id ? playerColor(card.player_id) : '#faf8f4'}"
								></span>
								<div class="min-w-0 flex-1">
									<div class="flex items-baseline gap-2">
										<span class="truncate font-semibold">{card.name}</span>
										<span
											class="shrink-0 text-[10px] font-semibold uppercase"
											style="color: {CATEGORY_INFO[card.category].color}"
										>
											{CATEGORY_INFO[card.category].label}
										</span>
									</div>
									<div class="truncate text-xs text-[#6e6a63]">
										{card.country ? `${card.country} · ` : ''}{card.description}
									</div>
								</div>
								<div class="flex shrink-0 flex-col items-end">
									<span class="font-mono-num text-sm">{formatLat(card.lat)}</span>
									{#if card.wikipedia}
										<a
											href={card.wikipedia}
											target="_blank"
											rel="noopener"
											class="text-[10px] text-[#6e6a63] underline"
										>
											Wiki
										</a>
									{/if}
								</div>
							</li>
						{/if}
					{/each}
				</ol>
			</div>

			<!-- Everyone's hands are public -->
			{#if isPlaying && (gameState.turn_order ?? []).length > 1}
				<div class="space-y-1 text-xs">
					{#each (gameState.turn_order ?? []).filter((id) => id !== profile.playerId) as pid (pid)}
						<div class="flex flex-wrap items-center gap-1.5">
							<span class="font-semibold" style="color: {playerColor(pid)}">{playerName(pid)}:</span>
							{#each hands[pid] ?? [] as card (card.id)}
								<span
									class="rounded border px-1.5 py-0.5"
									style="border-color: {CATEGORY_INFO[card.category].color}"
								>
									{card.name}
								</span>
							{:else}
								<span class="text-[#6e6a63]">no cards</span>
							{/each}
						</div>
					{/each}
				</div>
			{/if}

			{#if isHost && isPlaying}
				<div class="flex justify-center pt-2">
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
		<!-- My hand, sticky at the bottom -->
		<div class="fixed inset-x-0 bottom-0 z-20 border-t-[2px] border-[#1a1917] bg-[#faf8f4]/95 px-3 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] backdrop-blur">
			<div class="mx-auto max-w-[640px]">
				<div class="mb-1.5 flex items-center justify-between gap-2 text-xs">
					<span class="font-semibold">
						{#if isMyTurn}
							{selectedCard ? 'Now tap where it goes on the axis.' : 'Your turn — pick a card.'}
						{:else}
							{playerName(currentPlayerId)}'s turn
						{/if}
					</span>
					{#if timed && isMyTurn}
						<span class="font-mono-num" aria-live="off">
							{#if speed.factor > 1}
								×{speed.factor} · {speed.left}s
							{:else}
								×1
							{/if}
						</span>
					{/if}
				</div>
				{#if timed && isMyTurn && speed.factor > 1}
					<div class="mb-2 h-1 overflow-hidden rounded bg-[#1a1917]/10">
						<div
							class="h-full bg-[#1a1917] transition-[width] duration-200"
							style="width: {Math.min(100, (speed.left / 10) * 100)}%"
						></div>
					</div>
				{/if}
				<div class="flex items-stretch gap-2">
					{#each myHand as card (card.id)}
						<button
							type="button"
							disabled={!isMyTurn}
							onclick={() => selectCard(card.id)}
							aria-pressed={selectedId === card.id}
							class="hand-card min-w-0 flex-1 cursor-pointer rounded border-[1.5px] px-2 py-1.5 text-left transition disabled:cursor-default
							{selectedId === card.id ? 'bg-[#1a1917] text-[#faf8f4]' : 'bg-white'}"
							style="border-color: {CATEGORY_INFO[card.category].color}"
						>
							<div class="flex items-center justify-between gap-1 text-[10px] font-semibold uppercase">
								<span style="color: {selectedId === card.id ? '#faf8f4' : CATEGORY_INFO[card.category].color}">
									{CATEGORY_INFO[card.category].label}
								</span>
								<span class="font-mono-num">{card.points}</span>
							</div>
							<div
								lang={gameState.language ?? 'de'}
								title={card.name}
								class="line-clamp-4 text-sm leading-tight font-semibold hyphens-auto [overflow-wrap:anywhere]"
							>
								{card.name}
							</div>
						</button>
					{:else}
						<div class="flex-1 py-2 text-center text-sm text-[#6e6a63]">No cards left.</div>
					{/each}
					<button
						type="button"
						disabled={!isMyTurn}
						onclick={skip}
						class="shrink-0 cursor-pointer rounded border-[1.5px] border-[#1a1917] px-2 text-xs font-semibold transition hover:bg-[#f2eee6] disabled:cursor-default disabled:opacity-40"
					>
						Skip
					</button>
				</div>
			</div>
		</div>
	{/if}
</RoomShell>

<style>
	.cfg-btn {
		cursor: pointer;
		border-radius: 0.25rem;
		border: 1px solid #1a1917;
		padding: 0.375rem 0.5rem;
		font-size: 0.75rem;
		font-weight: 600;
		transition: background-color 0.15s;
	}
	.cfg-btn:disabled {
		cursor: not-allowed;
	}
	.cfg-on {
		background: #1a1917;
		color: #faf8f4;
	}
	.cfg-off {
		background: #faf8f4;
		color: #1a1917;
	}
	.cfg-off:not(:disabled):hover {
		background: #f2eee6;
	}
	.last-placed {
		animation: pop 0.9s ease-out;
		box-shadow: 0 0 0 2px #4f8a4b;
	}
	@keyframes pop {
		0% {
			transform: scale(0.96);
			background: #e7f1e4;
		}
		100% {
			transform: scale(1);
		}
	}
</style>
