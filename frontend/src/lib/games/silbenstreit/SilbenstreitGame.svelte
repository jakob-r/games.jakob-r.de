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

	interface TileCoord {
		row: number;
		col: number;
	}

	interface PlayedWordEntry {
		word: string;
		player_id: string;
		positions: TileCoord[];
		word_points: number;
		points_delta: number;
		move_number: number;
	}

	interface SilbenPublicState {
		size?: number;
		language?: string;
		letters?: string[][];
		values?: number[][];
		owners?: (string | null)[][];
		protected?: boolean[][];
		turn_order?: string[];
		current_turn_index?: number;
		current_player_id?: string | null;
		played_words?: PlayedWordEntry[];
		player_scores?: Record<string, number>;
		unowned_count?: number;
		total_tiles?: number;
		consecutive_passes?: number;
		move_count?: number;
		last_move?: PlayedWordEntry | null;
	}

	const client = new RoomSocketClient();

	const SIZES = [4, 5, 6, 7, 8];
	const LANGUAGES: { code: string; label: string }[] = [
		{ code: 'de', label: 'Deutsch' },
		{ code: 'en', label: 'English' },
		{ code: 'fr', label: 'Français' },
		{ code: 'es', label: 'Español' }
	];

	let deletingRoom = $state<boolean>(false);
	let leavingRoom = $state<boolean>(false);
	let selectedTiles = $state<TileCoord[]>([]);
	let rejectReason = $state<string | null>(null);
	let rejectShake = $state<boolean>(false);
	let lastPlayedPopup = $state<{ word: string; delta: number; player_id: string } | null>(null);

	let room = $derived(client.room);
	let gameState = $derived((room?.state ?? {}) as SilbenPublicState);
	let players = $derived<PlayerInfo[]>(room?.players ?? []);
	let isHost = $derived(room?.host_player_id === profile.playerId);

	// Lobby config state
	let cfgSize = $derived(Number(room?.config?.size ?? 5));
	let cfgLanguage = $derived(String(room?.config?.language ?? 'de'));
	let cfgScoring = $derived(Boolean(room?.config?.scoring_enabled ?? true));

	// Playing board derived values
	let boardSize = $derived(gameState.size ?? cfgSize);
	let boardLang = $derived(gameState.language ?? cfgLanguage);
	let letters = $derived(gameState.letters ?? []);
	let values = $derived(gameState.values ?? []);
	let owners = $derived(gameState.owners ?? []);
	let protectedGrid = $derived(gameState.protected ?? []);
	let playedWords = $derived<PlayedWordEntry[]>(gameState.played_words ?? []);
	let currentPlayerId = $derived(gameState.current_player_id ?? null);
	let isMyTurn = $derived(room?.status === 'playing' && currentPlayerId === profile.playerId);
	let currentPlayer = $derived(players.find((p) => p.player_id === currentPlayerId) ?? null);
	let currentTurnColor = $derived(
		resolvePlayerColor(currentPlayerId, profile.playerId, profile.primaryColor, players)
	);

	// Word being composed
	let composedWord = $derived(
		selectedTiles.map((pos) => letters[pos.row]?.[pos.col] ?? '').join('')
	);
	let composedPoints = $derived(
		selectedTiles.reduce((sum, pos) => sum + (values[pos.row]?.[pos.col] ?? 0), 0)
	);
	let composedAlreadyPlayed = $derived(
		composedWord.length >= 2 &&
			playedWords.some((entry) => entry.word.toUpperCase() === composedWord.toUpperCase())
	);

	// Map of "row,col" -> 1-based step index in current selection
	let selectionOrderMap = $derived.by(() => {
		const map = new Map<string, number>();
		selectedTiles.forEach((pos, idx) => {
			map.set(`${pos.row},${pos.col}`, idx + 1);
		});
		return map;
	});

	// Last played word coordinates for subtle highlight
	let lastMoveSet = $derived.by(() => {
		const set = new Set<string>();
		for (const pos of gameState.last_move?.positions ?? []) {
			set.add(`${pos.row},${pos.col}`);
		}
		return set;
	});

	// Winners calculation when finished
	let winners = $derived.by(() => {
		if (players.length === 0) return [];
		const maxScore = Math.max(...players.map((p) => p.score));
		return players.filter((p) => p.score === maxScore);
	});

	function formatLanguageLabel(code: string): string {
		return LANGUAGES.find((l) => l.code === code)?.label ?? code.toUpperCase();
	}

	function formatRejectionReason(reason: string, word: string): string {
		if (reason === 'too_short') return 'Word must have at least 2 letters.';
		if (reason === 'protected_tile') return 'Protected tiles cannot be selected.';
		if (reason === 'already_played') return `"${word}" has already been played.`;
		if (reason === 'not_in_dictionary')
			return `"${word}" is not in the ${formatLanguageLabel(boardLang)} dictionary.`;
		if (reason === 'not_your_turn') return 'Wait for your turn.';
		return 'Invalid word.';
	}

	function updateSize(size: number) {
		if (!isHost) return;
		client.updateConfig({ size });
	}

	function updateLanguage(language: string) {
		if (!isHost) return;
		client.updateConfig({ language });
	}

	function updateScoring(scoring_enabled: boolean) {
		if (!isHost) return;
		client.updateConfig({ scoring_enabled });
	}

	function toggleTile(row: number, col: number) {
		if (!isMyTurn || room?.status !== 'playing') return;
		if (protectedGrid[row]?.[col]) return;

		rejectReason = null;
		const existingIdx = selectedTiles.findIndex((t) => t.row === row && t.col === col);
		if (existingIdx !== -1) {
			// If tapping the last tile, pop it; if tapping an earlier selected tile, remove it
			selectedTiles = selectedTiles.filter((_, idx) => idx !== existingIdx);
			return;
		}
		selectedTiles = [...selectedTiles, { row, col }];
		client.sendCursor(row, col);
	}

	function removeComposedAt(index: number) {
		rejectReason = null;
		selectedTiles = selectedTiles.filter((_, i) => i !== index);
	}

	function clearSelection() {
		rejectReason = null;
		selectedTiles = [];
	}

	function submitWord() {
		if (!isMyTurn || selectedTiles.length < 2) return;
		rejectReason = null;
		client.sendAction({
			type: 'submit_word',
			positions: selectedTiles
		});
	}

	function passTurn() {
		if (!isMyTurn) return;
		clearSelection();
		client.sendAction({
			type: 'pass_turn'
		});
	}

	function handleKeydown(e: KeyboardEvent) {
		if (!isMyTurn || room?.status !== 'playing') return;
		if (e.metaKey || e.ctrlKey || e.altKey) return;
		const target = e.target as HTMLElement | null;
		if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return;

		if (e.key === 'Backspace') {
			if (selectedTiles.length > 0) {
				e.preventDefault();
				rejectReason = null;
				selectedTiles = selectedTiles.slice(0, -1);
			}
			return;
		}
		if (e.key === 'Escape') {
			if (selectedTiles.length > 0) {
				e.preventDefault();
				clearSelection();
			}
			return;
		}
		if (e.key === 'Enter') {
			if (selectedTiles.length >= 2) {
				e.preventDefault();
				submitWord();
			}
			return;
		}

		const letter = e.key.toUpperCase();
		if (/^[A-Z]$/.test(letter)) {
			// Find first unselected, unprotected tile matching `letter`
			for (let r = 0; r < boardSize; r++) {
				for (let c = 0; c < boardSize; c++) {
					if (
						letters[r]?.[c] === letter &&
						!protectedGrid[r]?.[c] &&
						!selectionOrderMap.has(`${r},${c}`)
					) {
						e.preventDefault();
						rejectReason = null;
						selectedTiles = [...selectedTiles, { row: r, col: c }];
						return;
					}
				}
			}
		}
	}

	function getPlayerName(playerId: string | null | undefined): string {
		if (!playerId) return 'Player';
		return players.find((p) => p.player_id === playerId)?.name ?? 'Player';
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
		if (!profile.playerId || leavingRoom) return;
		leavingRoom = true;
		try {
			await fetch(
				`/api/rooms/${encodeURIComponent(roomId)}/players/${encodeURIComponent(profile.playerId)}`,
				{ method: 'DELETE' }
			);
			client.disconnect();
			await goto('/');
		} finally {
			leavingRoom = false;
		}
	}

	onMount(() => {
		profile.init();
		client.connect({
			gameSlug: 'silbenstreit',
			roomId,
			playerId: profile.playerId,
			name: profile.name,
			color: profile.primaryColor
		});

		const unsub = client.onEvent((ev: ServerEvent) => {
			if (ev.type === 'word_played') {
				selectedTiles = [];
				rejectReason = null;
				lastPlayedPopup = {
					word: ev.word,
					delta: ev.points_delta,
					player_id: ev.player_id
				};
				setTimeout(() => {
					if (lastPlayedPopup?.word === ev.word) {
						lastPlayedPopup = null;
					}
				}, 1800);
			} else if (ev.type === 'word_rejected' && ev.player_id === profile.playerId) {
				rejectReason = formatRejectionReason(ev.reason, ev.word);
				rejectShake = true;
				setTimeout(() => {
					rejectShake = false;
				}, 450);
			} else if (ev.type === 'turn_passed') {
				selectedTiles = [];
				rejectReason = null;
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

<NamePromptModal onConfirm={(name, color) => client.syncProfile(profile.playerId, name, color)} />

<div class="mx-auto flex w-full max-w-4xl flex-1 flex-col px-3 py-3 sm:px-6 sm:py-5">
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
				<h1 class="font-hand text-lg leading-none sm:text-xl">Silbenstreit</h1>
				<div class="font-mono-num flex items-center gap-2 text-[11px] text-[#6e6a63]">
					<span>#{roomId}</span>
					<span>•</span>
					<span>{boardSize}×{boardSize}</span>
					<span>•</span>
					<span class="uppercase">{boardLang}</span>
					{#if !client.connected}
						<span class="text-[#dc2626]">• reconnecting…</span>
					{/if}
				</div>
			</div>
		</div>

		<div class="flex items-center gap-2">
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
			onLeaveRoom={leaveRoom}
		>
			{#snippet configSlot()}
				<div class="space-y-4">
					{#if !isHost}
						<div class="font-hand text-right text-xs text-[#6e6a63]">Configured by host</div>
					{/if}

					<!-- Grid Size (4x4 to 8x8) -->
					<div>
						<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">
							Board Size ({cfgSize}×{cfgSize})
						</span>
						<div class="flex flex-wrap gap-1.5">
							{#each SIZES as sz (sz)}
								<button
									type="button"
									disabled={!isHost}
									onclick={() => updateSize(sz)}
									class="font-mono-num cursor-pointer rounded border border-[#1a1917] px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed
									{cfgSize === sz
										? 'bg-[#1a1917] text-[#faf8f4]'
										: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
								>
									{sz}×{sz}
								</button>
							{/each}
						</div>
					</div>

					<!-- Language Selection -->
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

					<!-- Scoring Toggle -->
					<div class="flex items-center justify-between border-t border-[#1a1917]/15 pt-3">
						<div>
							<div class="text-xs font-semibold uppercase">Rarity Scoring (1–10)</div>
							<div class="text-xs text-[#6e6a63]">
								Rare letters score up to 10 points while owned.
							</div>
						</div>
						<button
							type="button"
							disabled={!isHost}
							onclick={() => updateScoring(!cfgScoring)}
							class="cursor-pointer rounded border border-[#1a1917] px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed
							{cfgScoring ? 'bg-[#1a1917] text-[#faf8f4]' : 'bg-[#faf8f4] text-[#6e6a63]'}"
						>
							{cfgScoring ? 'Enabled' : 'Off'}
						</button>
					</div>
				</div>
			{/snippet}
		</Lobby>
	{:else}
		<!-- Active or Finished Silbenstreit View -->
		<div class="flex flex-1 flex-col gap-3">
			<!-- Players & Turn Bar -->
			<div class="flex flex-wrap items-center justify-between gap-2">
				<div class="flex flex-wrap items-center gap-2">
					{#each players as p (p.player_id)}
						{@const pColor = resolvePlayerColor(
							p.player_id,
							profile.playerId,
							profile.primaryColor,
							players
						)}
						{@const isTurn = room.status === 'playing' && p.player_id === currentPlayerId}
						<div
							class="relative flex items-center gap-2 rounded-md border-[1.8px] border-[#1a1917] px-2.5 py-1 transition
							{isTurn
								? 'bg-[#faf8f4] shadow-[2.5px_2.5px_0px_#1a1917]'
								: 'bg-[#faf8f4]/70 opacity-85 shadow-[1px_1px_0px_#1a1917]'}"
							style={isTurn ? `border-color: ${pColor};` : ''}
						>
							<span
								class="h-2.5 w-2.5 rounded-full border border-[#1a1917]"
								style="background-color: {pColor};"
							></span>
							<span class="max-w-[110px] truncate text-xs font-semibold" style="color: {pColor};">
								{p.name}
							</span>
							{#if cfgScoring}
								<span class="font-mono-num text-xs font-bold text-[#1a1917]">
									{p.score}
								</span>
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

				<div class="font-mono-num flex items-center gap-2 text-xs text-[#6e6a63]">
					<span>{formatLanguageLabel(boardLang)}</span>
					<span>•</span>
					<span>{gameState.unowned_count ?? 0} unowned left</span>
				</div>
			</div>

			<!-- Game Over or Turn Banner -->
			{#if room.status === 'finished'}
				<ScribblyBox seed={59} class="bg-[#faf8f4] p-4 text-center">
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
							<ScribblyButton onclick={() => client.returnToLobby()}>
								Lobby
							</ScribblyButton>
						</div>
					{/if}
				</ScribblyBox>
			{:else}
				<div
					class="flex flex-wrap items-center justify-between gap-2 rounded-md border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-2 text-xs shadow-[1.5px_1.5px_0px_#1a1917]"
				>
					{#if isMyTurn}
						<div class="flex items-center gap-2 font-semibold" style="color: {profile.primaryColor};">
							<span
								class="inline-block h-2.5 w-2.5 rounded-full border border-[#1a1917]"
								style="background-color: {profile.primaryColor};"
							></span>
							<span>Your turn — tap unprotected tiles to spell a {formatLanguageLabel(boardLang)} word</span>
						</div>
					{:else if currentPlayer}
						<div class="flex items-center gap-2">
							<span
								class="inline-block h-2.5 w-2.5 rounded-full border border-[#1a1917]"
								style="background-color: {currentTurnColor};"
							></span>
							<span>
								<strong style="color: {currentTurnColor};">{currentPlayer.name}</strong>'s turn
							</span>
						</div>
					{:else}
						<span class="text-[#6e6a63]">Waiting for player…</span>
					{/if}

					{#if lastPlayedPopup}
						{@const popColor = resolvePlayerColor(
							lastPlayedPopup.player_id,
							profile.playerId,
							profile.primaryColor,
							players
						)}
						<div class="font-mono-num flex items-center gap-1.5 text-xs font-bold" style="color: {popColor};">
							<span>"{lastPlayedPopup.word}"</span>
							{#if lastPlayedPopup.delta !== 0}
								<span>({lastPlayedPopup.delta > 0 ? `+${lastPlayedPopup.delta}` : lastPlayedPopup.delta})</span>
							{/if}
						</div>
					{/if}
				</div>
			{/if}

			<!-- Main Grid + Word Composer + Played Words Layout -->
			<div class="grid grid-cols-1 items-start gap-4 lg:grid-cols-[1fr_250px]">
				<!-- Left Column: Letter Grid & Word Composer -->
				<div class="flex flex-col items-center gap-3">
					<!-- Letter Grid -->
					<div
						class="grid w-full max-w-[440px] gap-1.5 select-none sm:gap-2"
						style="grid-template-columns: repeat({boardSize}, minmax(0, 1fr));"
						role="grid"
						aria-label="Silbenstreit Letter Grid"
					>
						{#each Array.from({ length: boardSize }, (_, r) => r) as r (r)}
							{#each Array.from({ length: boardSize }, (_, c) => c) as c (c)}
								{@const letter = letters[r]?.[c] ?? '?'}
								{@const val = values[r]?.[c] ?? 1}
								{@const ownerId = owners[r]?.[c] ?? null}
								{@const isProtected = protectedGrid[r]?.[c] ?? false}
								{@const stepIdx = selectionOrderMap.get(`${r},${c}`) ?? null}
								{@const isSelected = stepIdx !== null}
								{@const isLastMoveTile = lastMoveSet.has(`${r},${c}`)}
								{@const ownerColor = ownerId
									? resolvePlayerColor(ownerId, profile.playerId, profile.primaryColor, players)
									: null}
								<button
									type="button"
									disabled={!isMyTurn || isProtected || room.status !== 'playing'}
									onclick={() => toggleTile(r, c)}
									title={isProtected
										? `Protected tile (${letter}, ${val} pts) — surrounded by ${getPlayerName(ownerId)}`
										: `${letter} (${val} pts)`}
									class="relative flex aspect-square flex-col items-center justify-center rounded-md border-[1.8px] transition select-none
									{isProtected
										? 'cursor-not-allowed'
										: isMyTurn && room.status === 'playing'
											? 'cursor-pointer hover:-translate-y-0.5 active:translate-y-0'
											: 'cursor-default'}
									{isSelected
										? 'ring-2 ring-[#1a1917] -translate-y-0.5 shadow-[2.5px_2.5px_0px_#1a1917]'
										: 'shadow-[1.5px_1.5px_0px_#1a1917]'}"
									style="
										border-color: {ownerColor ?? '#1a1917'};
										background-color: {isProtected && ownerColor
											? `color-mix(in oklab, ${ownerColor} 32%, #faf8f4)`
											: ownerColor
												? `color-mix(in oklab, ${ownerColor} 16%, #faf8f4)`
												: isSelected
													? '#f2eee6'
													: '#faf8f4'};
									"
								>
									<!-- Protected inner frame / shield indicator -->
									{#if isProtected && ownerColor}
										<span
											class="pointer-events-none absolute inset-[3px] rounded border-[1.5px] border-dashed"
											style="border-color: {ownerColor};"
										></span>
										<span
											class="pointer-events-none absolute top-0.5 left-1 text-[9px] leading-none font-bold"
											style="color: {ownerColor};"
											aria-label="Protected"
										>
											★
										</span>
									{:else if isSelected}
										<span
											class="font-mono-num pointer-events-none absolute top-0.5 left-1 rounded bg-[#1a1917] px-1 text-[9px] leading-tight font-bold text-[#faf8f4]"
										>
											{stepIdx}
										</span>
									{:else if isLastMoveTile}
										<span
											class="pointer-events-none absolute top-1 left-1 h-1.5 w-1.5 rounded-full bg-[#1a1917]/40"
										></span>
									{/if}

									<!-- Main Letter -->
									<span
										class="font-hand leading-none font-bold
										{boardSize >= 7 ? 'text-base sm:text-xl' : 'text-xl sm:text-2xl'}"
										style="color: {ownerColor ?? '#1a1917'};"
									>
										{letter}
									</span>

									<!-- Rarity Score (1-10) in bottom-right corner -->
									<span
										class="font-mono-num pointer-events-none absolute right-1 bottom-0.5 text-[9px] leading-none font-semibold sm:text-[10px]"
										style="color: {ownerColor ?? '#6e6a63'};"
									>
										{val}
									</span>
								</button>
							{/each}
						{/each}
					</div>

					<!-- Word Composer Panel -->
					{#if room.status === 'playing'}
						<ScribblyBox
							seed={71}
							class="w-full max-w-[440px] bg-[#faf8f4] p-3 sm:p-4 {rejectShake ? 'animate-mistake-shake' : ''}"
						>
							<div class="flex items-center justify-between gap-2">
								<span class="text-xs font-semibold uppercase text-[#6e6a63]">
									Word Composer
								</span>
								{#if selectedTiles.length > 0}
									<span class="font-mono-num text-xs font-semibold text-[#1a1917]">
										{selectedTiles.length} letters • {composedPoints} tile pts
									</span>
								{/if}
							</div>

							<!-- Assembled Letter Chips -->
							<div
								class="mt-2 flex min-h-[44px] flex-wrap items-center gap-1.5 rounded border border-[#1a1917]/20 bg-[#f3efe6]/70 px-2.5 py-2"
							>
								{#if selectedTiles.length === 0}
									<span class="text-xs text-[#6e6a63]">
										{isMyTurn
											? 'Tap tiles or type on keyboard to build a word…'
											: 'Waiting for opponent…'}
									</span>
								{:else}
									{#each selectedTiles as pos, idx (`${pos.row},${pos.col}`)}
										{@const ch = letters[pos.row]?.[pos.col] ?? '?'}
										{@const pts = values[pos.row]?.[pos.col] ?? 1}
										<button
											type="button"
											onclick={() => removeComposedAt(idx)}
											title="Remove letter"
											class="inline-flex cursor-pointer items-baseline gap-0.5 rounded border border-[#1a1917] bg-[#faf8f4] px-2 py-1 shadow-[1px_1px_0px_#1a1917] hover:bg-[#fef2f2]"
										>
											<span class="font-hand text-base font-bold">{ch}</span>
											<span class="font-mono-num text-[9px] text-[#6e6a63]">{pts}</span>
										</button>
									{/each}
								{/if}
							</div>

							{#if composedAlreadyPlayed}
								<p class="mt-1.5 text-xs font-medium text-[#dc2626]">
									"{composedWord}" was already played in this game.
								</p>
							{/if}

							{#if rejectReason}
								<p class="mt-1.5 text-xs font-medium text-[#dc2626]">
									{rejectReason}
								</p>
							{/if}

							<!-- Actions -->
							<div class="mt-3 flex flex-wrap items-center justify-between gap-2">
								<div class="flex items-center gap-2">
									<ScribblyButton
										onclick={submitWord}
										disabled={!isMyTurn || selectedTiles.length < 2 || composedAlreadyPlayed}
										variant="primary"
										accentColor={profile.primaryColor}
									>
										Submit Word
									</ScribblyButton>
									{#if selectedTiles.length > 0}
										<ScribblyButton onclick={clearSelection}>
											Clear
										</ScribblyButton>
									{/if}
								</div>

								<ScribblyButton
									onclick={passTurn}
									disabled={!isMyTurn}
									title="Pass turn if no valid word can be formed"
								>
									Pass Turn
								</ScribblyButton>
							</div>
						</ScribblyBox>
					{/if}
				</div>

				<!-- Right Column: Played Words History & Rules Legend -->
				<div class="space-y-3">
					<ScribblyBox seed={83} class="bg-[#faf8f4] p-3.5 sm:p-4">
						<div class="mb-2 flex items-center justify-between">
							<h2 class="font-hand text-base font-bold">
								Played Words ({playedWords.length})
							</h2>
						</div>

						{#if playedWords.length === 0}
							<p class="py-3 text-xs text-[#6e6a63]">
								No words played yet. Each word can only be used once!
							</p>
						{:else}
							<ul class="max-h-[280px] divide-y divide-[#1a1917]/10 overflow-y-auto pr-1">
								{#each [...playedWords].reverse() as entry (entry.move_number)}
									{@const entryColor = resolvePlayerColor(
										entry.player_id,
										profile.playerId,
										profile.primaryColor,
										players
									)}
									<li class="flex items-center justify-between gap-2 py-1.5 text-xs">
										<div class="flex items-center gap-2">
											<span
												class="h-2 w-2 shrink-0 rounded-full border border-[#1a1917]"
												style="background-color: {entryColor};"
											></span>
											<span class="font-mono-num font-bold tracking-wide" style="color: {entryColor};">
												{entry.word}
											</span>
										</div>
										<span class="font-mono-num text-[11px] text-[#6e6a63]">
											{entry.points_delta >= 0 ? `+${entry.points_delta}` : entry.points_delta}
										</span>
									</li>
								{/each}
							</ul>
						{/if}
					</ScribblyBox>

					<ScribblyBox seed={89} class="bg-[#faf8f4] p-3.5 text-xs text-[#6e6a63]">
						<div class="font-hand mb-1 text-sm font-bold text-[#1a1917]">How Protection Works</div>
						<p class="leading-relaxed">
							Tiles you claim turn your color and add their <span class="font-mono-num font-semibold text-[#1a1917]">1–10</span> rarity value to your score.
							When a tile is orthogonally surrounded by tiles of your color, it becomes
							<strong class="text-[#1a1917]">protected (★)</strong> and cannot be selected anymore.
						</p>
					</ScribblyBox>
				</div>
			</div>
		</div>
	{/if}
</div>
