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
	import { EMOJI_CATEGORIES, WORD_CATEGORY_LABELS } from './emojis';

	let { roomId }: { roomId: string } = $props();

	interface WordInfo {
		text?: string;
		category?: string;
		aliases?: string[];
	}

	interface GuessEntry {
		player_id: string;
		text?: string;
		close?: boolean;
		correct?: boolean;
	}

	interface RoundResult {
		round_number: number;
		reason: 'guessed' | 'gave_up' | 'time_up' | 'explainer_left';
		word: string | null;
		category: string | null;
		explainer_id: string | null;
		winner_id: string | null;
		points: Record<string, number>;
		next_player_id: string | null;
	}

	interface EmojiPublicState {
		language?: string;
		turn_order?: string[];
		current_player_id?: string | null;
		explainer_id?: string | null;
		phase?: 'choosing' | 'explaining' | 'reveal';
		round_number?: number;
		choices?: WordInfo[];
		word?: WordInfo | null;
		sentences?: string[][];
		deadline?: string | null;
		guesses?: GuessEntry[];
		last_result?: RoundResult | null;
	}

	const client = new RoomSocketClient();

	const MAX_SENTENCES = 5;
	const MAX_EMOJIS_PER_SENTENCE = 16;
	const ROUND_SECONDS = [60, 90, 120, 180, 240];
	const LANGUAGES = [
		{ code: 'de', label: 'Deutsch' },
		{ code: 'en', label: 'English' }
	];

	let room = $derived(client.room);
	let gameState = $derived((room?.state ?? {}) as EmojiPublicState);
	let players = $derived<PlayerInfo[]>(room?.players ?? []);
	let isHost = $derived(room?.host_player_id === profile.playerId);
	let isPlaying = $derived(room?.status === 'playing');

	let cfgMode = $derived(String(room?.config?.mode ?? 'in_person'));
	let cfgTimed = $derived(Boolean(room?.config?.timed ?? false));
	let cfgSeconds = $derived(Number(room?.config?.round_seconds ?? 120));
	let cfgLanguage = $derived(String(room?.config?.language ?? 'de'));
	let cfgScoring = $derived(Boolean(room?.config?.scoring_enabled ?? true));

	let phase = $derived(gameState.phase ?? 'choosing');
	let explainerId = $derived(gameState.explainer_id ?? null);
	let currentPlayerId = $derived(gameState.current_player_id ?? null);
	let amExplainer = $derived(isPlaying && explainerId === profile.playerId);
	let isMyTurn = $derived(isPlaying && currentPlayerId === profile.playerId);
	let serverSentences = $derived(gameState.sentences ?? [[]]);
	let guesses = $derived<GuessEntry[]>(gameState.guesses ?? []);
	let lastResult = $derived(gameState.last_result ?? null);
	let roundNumber = $derived(gameState.round_number ?? 1);

	// Explainer edits a local draft and pushes every change to the server.
	let draft = $state<string[][]>([[]]);
	let draftRound = $state<number | null>(null);
	let activeSentence = $state(0);
	let selectedEmoji = $state<number | null>(null);
	let activeCategory = $state(EMOJI_CATEGORIES[0].id);

	let guessText = $state('');
	let myLastGuess = $state<{ text: string; close: boolean } | null>(null);
	let rejectMessage = $state<string | null>(null);

	let clockOffsetMs = $state(0);
	let nowMs = $state(Date.now());
	let timeUpSentAt = $state(0);

	let sentences = $derived(amExplainer && phase === 'explaining' ? draft : serverSentences);
	let category = $derived(
		EMOJI_CATEGORIES.find((c) => c.id === activeCategory) ?? EMOJI_CATEGORIES[0]
	);
	let remainingMs = $derived.by(() => {
		if (!gameState.deadline || phase !== 'explaining') return null;
		return Math.max(0, Date.parse(gameState.deadline) - (nowMs + clockOffsetMs));
	});
	let otherPlayers = $derived(players.filter((p) => p.player_id !== profile.playerId));
	let sortedPlayers = $derived([...players].sort((a, b) => b.score - a.score));

	let nextExplainer = $derived(players.find((p) => p.player_id === currentPlayerId) ?? null);
	let canStartNextRound = $derived(
		phase === 'reveal' && (isMyTurn || isHost || !nextExplainer?.is_connected)
	);

	let turnNotificationHint = $derived.by(() => {
		if (lastResult?.word) return `The word was "${lastResult.word}". You explain next!`;
		return `Game #${roomId} has started and you are explaining first!`;
	});

	$effect(() => {
		if (amExplainer && phase === 'explaining' && draftRound !== roundNumber) {
			draft = serverSentences.map((s) => [...s]);
			draftRound = roundNumber;
			activeSentence = 0;
			selectedEmoji = null;
		}
	});

	$effect(() => {
		if (room?.server_time) {
			clockOffsetMs = Date.parse(room.server_time) - Date.now();
		}
	});

	$effect(() => {
		// Any client may report the deadline; the server ignores early or duplicate calls.
		if (remainingMs === 0 && isPlaying && nowMs - timeUpSentAt > 1500) {
			timeUpSentAt = nowMs;
			client.sendAction({ type: 'time_up' });
		}
	});

	function playerName(id: string | null | undefined): string {
		if (!id) return 'Someone';
		if (id === profile.playerId) return 'You';
		return players.find((p) => p.player_id === id)?.name ?? 'Someone';
	}

	function playerColor(id: string): string {
		return resolvePlayerColor(id, profile.playerId, profile.primaryColor, players);
	}

	function categoryLabel(id: string | null | undefined): string {
		return id ? (WORD_CATEGORY_LABELS[id] ?? id) : '';
	}

	function formatClock(ms: number): string {
		const total = Math.ceil(ms / 1000);
		return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
	}

	function updateConfig(patch: Record<string, unknown>) {
		if (isHost) client.updateConfig(patch);
	}

	function pushDraft(next: string[][]) {
		draft = next;
		client.sendAction({ type: 'set_sentences', sentences: next });
	}

	function addEmoji(emoji: string) {
		const line = draft[activeSentence] ?? [];
		if (line.length >= MAX_EMOJIS_PER_SENTENCE) return;
		const at = selectedEmoji === null ? line.length : selectedEmoji + 1;
		const nextLine = [...line.slice(0, at), emoji, ...line.slice(at)];
		pushDraft(draft.map((s, i) => (i === activeSentence ? nextLine : s)));
		if (selectedEmoji !== null) selectedEmoji = at;
	}

	function removeSelected() {
		if (selectedEmoji === null) return;
		const idx = selectedEmoji;
		const nextLine = draft[activeSentence].filter((_, i) => i !== idx);
		pushDraft(draft.map((s, i) => (i === activeSentence ? nextLine : s)));
		selectedEmoji = nextLine.length === 0 ? null : Math.min(idx, nextLine.length - 1);
	}

	function moveSelected(delta: -1 | 1) {
		if (selectedEmoji === null) return;
		const line = [...draft[activeSentence]];
		const to = selectedEmoji + delta;
		if (to < 0 || to >= line.length) return;
		[line[selectedEmoji], line[to]] = [line[to], line[selectedEmoji]];
		pushDraft(draft.map((s, i) => (i === activeSentence ? line : s)));
		selectedEmoji = to;
	}

	function selectSentence(index: number) {
		if (activeSentence !== index) {
			activeSentence = index;
			selectedEmoji = null;
		}
	}

	function tapEmoji(sentenceIdx: number, emojiIdx: number) {
		selectSentence(sentenceIdx);
		selectedEmoji = selectedEmoji === emojiIdx ? null : emojiIdx;
	}

	function addSentence() {
		if (draft.length >= MAX_SENTENCES) return;
		pushDraft([...draft, []]);
		activeSentence = draft.length - 1;
		selectedEmoji = null;
	}

	function deleteSentence(index: number) {
		if (draft.length <= 1) return;
		pushDraft(draft.filter((_, i) => i !== index));
		activeSentence = Math.max(0, Math.min(activeSentence, draft.length - 1));
		selectedEmoji = null;
	}

	function submitGuess(e: SubmitEvent) {
		e.preventDefault();
		const text = guessText.trim();
		if (!text) return;
		client.sendAction({ type: 'guess', text });
		guessText = '';
	}

	function endGame() {
		if (!isHost) return;
		if (window.confirm('End the game now and show the final scores?')) client.endGame();
	}

	function resultLine(result: RoundResult): string {
		if (result.reason === 'guessed') {
			return `${playerName(result.winner_id)} got it!`;
		}
		if (result.reason === 'time_up') return 'Time ran out.';
		if (result.reason === 'explainer_left') return `${playerName(result.explainer_id)} left.`;
		return `${playerName(result.explainer_id)} gave up.`;
	}

	onMount(() => {
		profile.init();
		client.connect({
			gameSlug: 'emoji-charades',
			roomId,
			playerId: profile.playerId,
			name: profile.name,
			color: profile.primaryColor
		});

		const unsub = client.onEvent((ev: ServerEvent) => {
			if (ev.type === 'guess_wrong' && ev.player_id === profile.playerId) {
				myLastGuess = { text: ev.text, close: ev.close };
			} else if (ev.type === 'round_ended' || ev.type === 'round_started') {
				myLastGuess = null;
				rejectMessage = null;
			} else if (
				ev.type === 'action_rejected' &&
				ev.player_id === profile.playerId &&
				ev.reason !== 'too_early'
			) {
				rejectMessage = 'That is not possible right now.';
				setTimeout(() => (rejectMessage = null), 2500);
			}
		});

		const tick = setInterval(() => (nowMs = Date.now()), 250);

		return () => {
			clearInterval(tick);
			unsub();
			client.disconnect();
		};
	});
</script>

<RoomShell
	{client}
	{roomId}
	title="Emoji Charades"
	subtitleItems={[
		cfgMode === 'remote' ? 'Remote' : 'In person',
		cfgTimed ? formatClock(cfgSeconds * 1000) : 'Untimed',
		cfgLanguage.toUpperCase()
	]}
>
	{#snippet headerActions()}
		<TurnNotificationBell
			{roomId}
			playerId={profile.playerId}
			gameSlug="emoji-charades"
			gameTitle="Emoji Charades"
			{isMyTurn}
			isPlaying={isPlaying}
			turnHint={turnNotificationHint}
		/>
	{/snippet}

	{#snippet configSlot()}
		<div class="space-y-4">
			{#if !isHost}
				<div class="font-hand text-right text-xs text-[#6e6a63]">Configured by host</div>
			{/if}

			<div>
				<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">Played</span>
				<div class="grid grid-cols-2 gap-2">
					{#each [{ id: 'in_person', label: 'In person', hint: 'Shout guesses' }, { id: 'remote', label: 'Remote', hint: 'Type guesses' }] as m (m.id)}
						<button
							type="button"
							disabled={!isHost}
							onclick={() => updateConfig({ mode: m.id })}
							class="cursor-pointer rounded border border-[#1a1917] px-3 py-1.5 text-left text-xs font-semibold transition disabled:cursor-not-allowed
							{cfgMode === m.id
								? 'bg-[#1a1917] text-[#faf8f4]'
								: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
						>
							{m.label}
							<span class="block font-normal opacity-70">{m.hint}</span>
						</button>
					{/each}
				</div>
			</div>

			<div>
				<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">Words</span>
				<div class="grid grid-cols-2 gap-2">
					{#each LANGUAGES as lang (lang.code)}
						<button
							type="button"
							disabled={!isHost}
							onclick={() => updateConfig({ language: lang.code })}
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

			<div class="flex items-center justify-between border-t border-[#1a1917]/15 pt-3">
				<div>
					<div class="text-xs font-semibold uppercase">Timer</div>
					<div class="text-xs text-[#6e6a63]">Timed rounds also give the explainer a point.</div>
				</div>
				<button
					type="button"
					disabled={!isHost}
					onclick={() => updateConfig({ timed: !cfgTimed })}
					class="cursor-pointer rounded border border-[#1a1917] px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed
					{cfgTimed ? 'bg-[#1a1917] text-[#faf8f4]' : 'bg-[#faf8f4] text-[#6e6a63]'}"
				>
					{cfgTimed ? 'On' : 'Off'}
				</button>
			</div>
			{#if cfgTimed}
				<div class="flex flex-wrap gap-1.5">
					{#each ROUND_SECONDS as secs (secs)}
						<button
							type="button"
							disabled={!isHost}
							onclick={() => updateConfig({ round_seconds: secs })}
							class="font-mono-num cursor-pointer rounded border border-[#1a1917] px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed
							{cfgSeconds === secs
								? 'bg-[#1a1917] text-[#faf8f4]'
								: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
						>
							{formatClock(secs * 1000)}
						</button>
					{/each}
				</div>
			{/if}

			<div class="flex items-center justify-between border-t border-[#1a1917]/15 pt-3">
				<div>
					<div class="text-xs font-semibold uppercase">Scoring</div>
					<div class="text-xs text-[#6e6a63]">+1 for the correct guess.</div>
				</div>
				<button
					type="button"
					disabled={!isHost}
					onclick={() => updateConfig({ scoring_enabled: !cfgScoring })}
					class="cursor-pointer rounded border border-[#1a1917] px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed
					{cfgScoring ? 'bg-[#1a1917] text-[#faf8f4]' : 'bg-[#faf8f4] text-[#6e6a63]'}"
				>
					{cfgScoring ? 'Enabled' : 'Off'}
				</button>
			</div>
		</div>
	{/snippet}

	<div class="mx-auto flex w-full max-w-[480px] flex-1 flex-col gap-3">
		<PlayerBar
			{players}
			hostPlayerId={room?.host_player_id ?? ''}
			myPlayerId={profile.playerId}
			myColor={profile.primaryColor}
			scoringEnabled={cfgScoring}
			showMultiplier={false}
			showTurnBadge={isPlaying}
			{currentPlayerId}
			statusText="Round {roundNumber}"
			onRemovePlayer={(id) => client.removePlayer(id)}
		/>

		{#if room?.status === 'finished'}
			<ScribblyBox seed={61} class="bg-[#faf8f4] p-4">
				<div class="font-hand mb-2 text-center text-xl">Final scores</div>
				<ol class="space-y-1">
					{#each sortedPlayers as p, i (p.player_id)}
						<li class="flex items-center justify-between gap-2 text-sm">
							<span class="flex items-center gap-2">
								<span class="font-mono-num w-5 text-[#6e6a63]">{i + 1}.</span>
								<span
									class="inline-block h-2.5 w-2.5 rounded-full"
									style="background-color: {playerColor(p.player_id)};"
								></span>
								{p.name}
							</span>
							<span class="font-mono-num font-semibold">{p.score}</span>
						</li>
					{/each}
				</ol>
				{#if isHost}
					<div class="mt-3 flex justify-center gap-2">
						<ScribblyButton onclick={() => client.startGame()} variant="primary">
							Play Again
						</ScribblyButton>
						<ScribblyButton onclick={() => client.returnToLobby()}>Lobby</ScribblyButton>
					</div>
				{/if}
			</ScribblyBox>
		{:else if phase === 'reveal' && lastResult}
			<ScribblyBox seed={roundNumber * 7 + 3} class="reveal-pop bg-[#faf8f4] p-4 text-center">
				<div class="text-xs tracking-wide text-[#6e6a63] uppercase">
					{categoryLabel(lastResult.category)}
				</div>
				<div class="font-hand mt-1 text-2xl break-words">{lastResult.word ?? '—'}</div>
				{#if serverSentences.some((s) => s.length > 0)}
					<div class="mt-2 space-y-0.5 text-xl">
						{#each serverSentences as line, i (i)}
							{#if line.length > 0}<div>{line.join(' ')}</div>{/if}
						{/each}
					</div>
				{/if}
				<div class="mt-2 text-sm">{resultLine(lastResult)}</div>
				{#if cfgScoring && Object.keys(lastResult.points).length > 0}
					<div class="mt-1 text-xs text-[#6e6a63]">
						{Object.entries(lastResult.points)
							.map(([id, pts]) => `${playerName(id)} +${pts}`)
							.join(' · ')}
					</div>
				{/if}
				<div class="mt-4 flex flex-col items-center gap-2">
					{#if canStartNextRound}
						<ScribblyButton
							onclick={() => client.sendAction({ type: 'next_round' })}
							variant="primary"
							accentColor={profile.primaryColor}
						>
							{isMyTurn ? 'Start my round →' : `Start round for ${playerName(currentPlayerId)} →`}
						</ScribblyButton>
					{:else}
						<p class="font-hand text-[#6e6a63]">
							Waiting for {playerName(currentPlayerId)} to start the next round…
						</p>
					{/if}
				</div>
			</ScribblyBox>
		{:else if phase === 'choosing'}
			{#if amExplainer}
				<ScribblyBox seed={41} class="bg-[#faf8f4] p-4">
					<div class="font-hand mb-3 text-center text-xl">Pick something to explain</div>
					<div class="flex flex-col gap-2">
						{#each gameState.choices ?? [] as choice, i (i)}
							<button
								type="button"
								onclick={() => client.sendAction({ type: 'choose_word', index: i })}
								class="cursor-pointer border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-2.5 text-left transition hover:bg-[#f2eee6]"
							>
								<span class="block text-[11px] tracking-wide text-[#6e6a63] uppercase">
									{categoryLabel(choice.category)}
								</span>
								<span class="text-lg font-semibold">{choice.text}</span>
							</button>
						{/each}
					</div>
				</ScribblyBox>
			{:else}
				<div class="flex flex-1 items-center justify-center py-10 text-center">
					<p class="font-hand text-lg text-[#6e6a63]">
						{playerName(explainerId)} is picking something to explain…
					</p>
				</div>
			{/if}
		{:else}
			<!-- Explaining -->
			<div class="flex items-center justify-between gap-2 text-sm">
				<span class="text-[#6e6a63]">
					{#if amExplainer}
						Explain:
						<strong class="text-[#1a1917]">{gameState.word?.text}</strong>
					{:else}
						{playerName(explainerId)} explains a
						<strong class="text-[#1a1917]">{categoryLabel(gameState.word?.category)}</strong>
					{/if}
				</span>
				{#if remainingMs !== null}
					<span
						class="font-mono-num rounded border border-[#1a1917] px-2 py-0.5 text-sm font-semibold
						{remainingMs < 15000 ? 'animate-pulse text-[#dc2626]' : ''}"
					>
						{formatClock(remainingMs)}
					</span>
				{/if}
			</div>

			<div class="border-[1.8px] border-[#1a1917] bg-[#faf8f4] px-3 py-2.5">
				{#each sentences as line, si (si)}
					{@const isActive = amExplainer && si === activeSentence}
					<div
						class="flex min-h-[48px] items-center gap-1 py-1.5
						{si > 0 ? 'border-t border-dashed border-[#1a1917]/20' : ''}"
					>
						{#if amExplainer}
							<button
								type="button"
								onclick={() => selectSentence(si)}
								aria-label="Edit sentence {si + 1}"
								class="font-mono-num w-6 shrink-0 cursor-pointer text-xs
								{isActive ? 'font-bold text-[#1a1917]' : 'text-[#6e6a63]'}"
							>
								{isActive ? '✎' : si + 1}
							</button>
						{/if}
						<!-- Tap target for touch; keyboard users select via the numbered button. -->
						<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
						<div
							class="flex flex-1 flex-wrap items-center gap-0.5
							{isActive ? 'rounded bg-[#f3efe6] px-1' : ''}"
							onclick={() => amExplainer && selectSentence(si)}
						>
							{#if line.length === 0}
								<span class="text-xs text-[#6e6a63]">
									{amExplainer
										? si === 0
											? 'Main concept: tap emojis below…'
											: 'Empty sentence'
										: si === 0
											? 'Waiting for emojis…'
											: ''}
								</span>
							{/if}
							{#each line as emoji, ei (`${si}-${ei}-${emoji}`)}
								{#if amExplainer}
									<button
										type="button"
										onclick={(e) => {
											e.stopPropagation();
											tapEmoji(si, ei);
										}}
										class="emoji-chip cursor-pointer rounded px-0.5 leading-none
										{si === 0 ? 'text-[2rem]' : 'text-[1.6rem]'}
										{isActive && selectedEmoji === ei ? 'ring-2 ring-[#1a1917]' : ''}"
									>
										{emoji}
									</button>
								{:else}
									<span
										class="emoji-chip leading-none {si === 0 ? 'text-[2.4rem]' : 'text-[1.8rem]'}"
									>
										{emoji}
									</span>
								{/if}
							{/each}
						</div>
						{#if amExplainer && sentences.length > 1}
							<button
								type="button"
								onclick={() => deleteSentence(si)}
								aria-label="Delete sentence {si + 1}"
								class="shrink-0 cursor-pointer px-1 text-xs text-[#6e6a63] hover:text-[#dc2626]"
							>
								✕
							</button>
						{/if}
					</div>
				{/each}

				{#if amExplainer}
					<div
						class="mt-1 flex flex-wrap items-center justify-between gap-2 border-t border-[#1a1917]/15 pt-2"
					>
						<div class="flex gap-1">
							<button
								type="button"
								onclick={() => moveSelected(-1)}
								disabled={selectedEmoji === null || selectedEmoji === 0}
								aria-label="Move emoji left"
								class="tool-btn">◀</button
							>
							<button
								type="button"
								onclick={() => moveSelected(1)}
								disabled={selectedEmoji === null ||
									selectedEmoji >= (draft[activeSentence]?.length ?? 0) - 1}
								aria-label="Move emoji right"
								class="tool-btn">▶</button
							>
							<button
								type="button"
								onclick={removeSelected}
								disabled={selectedEmoji === null}
								aria-label="Remove emoji"
								class="tool-btn">⌫</button
							>
						</div>
						<button
							type="button"
							onclick={addSentence}
							disabled={draft.length >= MAX_SENTENCES}
							class="cursor-pointer text-xs underline disabled:cursor-not-allowed disabled:opacity-40"
						>
							+ Sentence
						</button>
					</div>
				{/if}
			</div>

			{#if amExplainer}
				<!-- Emoji palette -->
				<div class="border-[1.6px] border-[#1a1917] bg-[#faf8f4]">
					<div class="flex overflow-x-auto border-b border-[#1a1917]/20" role="tablist">
						{#each EMOJI_CATEGORIES as cat (cat.id)}
							<button
								type="button"
								role="tab"
								aria-selected={activeCategory === cat.id}
								onclick={() => (activeCategory = cat.id)}
								class="flex shrink-0 cursor-pointer flex-col items-center px-2.5 py-1.5 text-[10px]
								{activeCategory === cat.id
									? 'bg-[#1a1917] text-[#faf8f4]'
									: 'text-[#6e6a63] hover:bg-[#f2eee6]'}"
							>
								<span class="text-lg leading-none">{cat.icon}</span>
								{cat.label}
							</button>
						{/each}
					</div>
					<div class="max-h-[220px] overflow-y-auto p-2">
						{#if 'pairs' in category}
							<div class="grid grid-cols-3 gap-1.5 sm:grid-cols-4">
								{#each category.pairs as [left, right] (`${left}${right}`)}
									<div class="flex items-center justify-center rounded border border-[#1a1917]/20">
										<button type="button" class="palette-btn" onclick={() => addEmoji(left)}>
											{left}
										</button>
										<span class="text-[10px] text-[#6e6a63]">↔</span>
										<button type="button" class="palette-btn" onclick={() => addEmoji(right)}>
											{right}
										</button>
									</div>
								{/each}
							</div>
						{:else}
							<div class="grid grid-cols-7 gap-0.5 sm:grid-cols-9">
								{#each category.emojis as emoji (emoji)}
									<button type="button" class="palette-btn" onclick={() => addEmoji(emoji)}>
										{emoji}
									</button>
								{/each}
							</div>
						{/if}
					</div>
				</div>

				{#if cfgMode === 'in_person'}
					<div class="border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-2.5">
						<div class="mb-1.5 text-[11px] font-semibold tracking-wide text-[#6e6a63] uppercase">
							Who guessed it?
						</div>
						<div class="flex flex-wrap gap-1.5">
							{#each otherPlayers as p (p.player_id)}
								<button
									type="button"
									onclick={() => client.sendAction({ type: 'award', player_id: p.player_id })}
									class="cursor-pointer border border-[#1a1917] px-2.5 py-1 text-sm transition hover:bg-[#f2eee6]"
									style="border-left: 4px solid {playerColor(p.player_id)};"
								>
									{p.name}
								</button>
							{:else}
								<span class="text-xs text-[#6e6a63]">Nobody else is here yet.</span>
							{/each}
						</div>
					</div>
				{/if}

				<div class="flex justify-end">
					<ScribblyButton onclick={() => client.sendAction({ type: 'give_up' })}>
						Give up
					</ScribblyButton>
				</div>
			{:else if cfgMode === 'remote'}
				<form class="flex gap-2" onsubmit={submitGuess}>
					<input
						bind:value={guessText}
						maxlength="80"
						autocomplete="off"
						placeholder="Your guess…"
						aria-label="Your guess"
						class="min-w-0 flex-1 border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-2 text-base outline-none focus:bg-white"
					/>
					<ScribblyButton
						type="submit"
						variant="primary"
						accentColor={profile.primaryColor}
						disabled={!guessText.trim()}
					>
						Guess
					</ScribblyButton>
				</form>
				{#if myLastGuess}
					<p class="text-xs {myLastGuess.close ? 'font-semibold text-[#b45309]' : 'text-[#6e6a63]'}">
						"{myLastGuess.text}" — {myLastGuess.close ? 'close!' : 'not it.'}
					</p>
				{/if}
			{:else}
				<p class="font-hand text-center text-[#6e6a63]">
					Shout your guess! {playerName(explainerId)} picks who got it.
				</p>
			{/if}

			{#if cfgMode === 'remote' && guesses.length > 0}
				<div class="border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-2.5">
					<div class="mb-1.5 text-[11px] font-semibold tracking-wide text-[#6e6a63] uppercase">
						Guesses
					</div>
					<div class="flex max-h-[140px] flex-wrap gap-1.5 overflow-y-auto">
						{#each [...guesses].reverse() as g, i (i)}
							<span
								class="inline-flex items-center gap-1 border border-[#1a1917]/25 px-2 py-0.5 text-xs"
								style="border-left: 3px solid {playerColor(g.player_id)};"
							>
								{g.text}
								{#if g.close}<span class="font-semibold text-[#b45309]">close</span>{/if}
							</span>
						{/each}
					</div>
				</div>
			{/if}
		{/if}

		{#if rejectMessage}
			<p class="text-center text-xs font-medium text-[#dc2626]">{rejectMessage}</p>
		{/if}

		{#if isHost && isPlaying}
			<div class="mt-auto flex justify-center pt-2">
				<button
					type="button"
					onclick={endGame}
					class="cursor-pointer text-xs text-[#6e6a63] underline hover:text-[#1a1917]"
				>
					End game &amp; show scores
				</button>
			</div>
		{/if}
	</div>
</RoomShell>

<style>
	.emoji-chip,
	.palette-btn {
		font-family:
			'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji', system-ui, sans-serif;
	}

	.palette-btn {
		cursor: pointer;
		border-radius: 4px;
		padding: 4px 2px;
		font-size: 1.6rem;
		line-height: 1;
		touch-action: manipulation;
		transition: transform 120ms ease;
	}

	.palette-btn:hover {
		background: #f2eee6;
	}

	.palette-btn:active {
		transform: scale(0.85);
	}

	.tool-btn {
		cursor: pointer;
		border: 1px solid #1a1917;
		padding: 2px 10px;
		font-size: 0.85rem;
		background: #faf8f4;
	}

	.tool-btn:disabled {
		cursor: not-allowed;
		opacity: 0.35;
	}

	:global(.reveal-pop) {
		animation: reveal-pop 360ms cubic-bezier(0.2, 1.4, 0.4, 1);
	}

	@keyframes reveal-pop {
		from {
			transform: scale(0.94);
			opacity: 0;
		}
		to {
			transform: scale(1);
			opacity: 1;
		}
	}
</style>
