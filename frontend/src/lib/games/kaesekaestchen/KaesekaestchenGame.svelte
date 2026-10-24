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

	interface LastMoveInfo {
		orientation: 'h' | 'v';
		row: number;
		col: number;
		player_id: string;
		closed_squares: { row: number; col: number }[];
	}

	interface KaesePublicState {
		width?: number;
		height?: number;
		active_squares?: boolean[][];
		h_edges?: (string | null)[][];
		v_edges?: (string | null)[][];
		square_owners?: (string | null)[][];
		turn_order?: string[];
		current_turn_index?: number;
		current_player_id?: string | null;
		total_squares?: number;
		claimed_squares?: number;
		move_count?: number;
		last_move?: LastMoveInfo | null;
	}

	interface ScorePopup {
		id: number;
		row: number;
		col: number;
		player_id: string;
		points_delta: number;
	}

	const client = new RoomSocketClient();

	const SIZES = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
	const CELL_STEP = 56;
	const PAD = 28;

	let deletingRoom = $state<boolean>(false);
	let leavingRoom = $state<boolean>(false);
	let scorePopups = $state<ScorePopup[]>([]);
	let hoveredEdge = $state<{ orientation: 'h' | 'v'; row: number; col: number } | null>(null);
	let dragDrawMode = $state<'add' | 'remove' | null>(null);
	let popupCounter = 0;

	let room = $derived(client.room);
	let gameState = $derived((room?.state ?? {}) as KaesePublicState);
	let players = $derived<PlayerInfo[]>(room?.players ?? []);
	let isHost = $derived(room?.host_player_id === profile.playerId);

	// Lobby config state
	let cfgWidth = $derived(Number(room?.config?.width ?? 6));
	let cfgHeight = $derived(Number(room?.config?.height ?? 6));
	let cfgBorderEdges = $derived<string[]>(
		Array.isArray(room?.config?.border_edges) ? (room?.config?.border_edges as string[]) : []
	);
	let cfgBorderSet = $derived(new Set(cfgBorderEdges));

	// Preview active squares in Lobby using the same flood-fill rule as backend
	let lobbyActivePreview = $derived(computeActiveSquaresClient(cfgWidth, cfgHeight, cfgBorderSet));
	let lobbyActiveCount = $derived(
		lobbyActivePreview.reduce(
			(acc, row) => acc + row.reduce((rAcc, active) => rAcc + (active ? 1 : 0), 0),
			0
		)
	);

	// Playing board derived values
	let boardWidth = $derived(gameState.width ?? cfgWidth);
	let boardHeight = $derived(gameState.height ?? cfgHeight);
	let activeSquares = $derived(gameState.active_squares ?? []);
	let hEdges = $derived(gameState.h_edges ?? []);
	let vEdges = $derived(gameState.v_edges ?? []);
	let squareOwners = $derived(gameState.square_owners ?? []);
	let currentPlayerId = $derived(gameState.current_player_id ?? null);
	let isMyTurn = $derived(
		room?.status === 'playing' && currentPlayerId === profile.playerId
	);
	let currentPlayer = $derived(players.find((p) => p.player_id === currentPlayerId) ?? null);
	let currentTurnColor = $derived(
		resolvePlayerColor(currentPlayerId, profile.playerId, profile.primaryColor, players)
	);

	// Winners calculation when finished
	let winners = $derived.by(() => {
		if (players.length === 0) return [];
		const maxScore = Math.max(...players.map((p) => p.score));
		return players.filter((p) => p.score === maxScore);
	});

	function edgeKey(orientation: 'h' | 'v', row: number, col: number): string {
		return `${orientation}:${row}:${col}`;
	}

	function computeActiveSquaresClient(
		width: number,
		height: number,
		borderSet: Set<string>
	): boolean[][] {
		const outsideReachable: boolean[][] = Array.from({ length: height }, () =>
			Array(width).fill(false)
		);
		const queue: [number, number][] = [];

		for (let c = 0; c < width; c++) {
			if (!borderSet.has(edgeKey('h', 0, c)) && !outsideReachable[0][c]) {
				outsideReachable[0][c] = true;
				queue.push([0, c]);
			}
			if (!borderSet.has(edgeKey('h', height, c)) && !outsideReachable[height - 1][c]) {
				outsideReachable[height - 1][c] = true;
				queue.push([height - 1, c]);
			}
		}

		for (let r = 0; r < height; r++) {
			if (!borderSet.has(edgeKey('v', r, 0)) && !outsideReachable[r][0]) {
				outsideReachable[r][0] = true;
				queue.push([r, 0]);
			}
			if (!borderSet.has(edgeKey('v', r, width)) && !outsideReachable[r][width - 1]) {
				outsideReachable[r][width - 1] = true;
				queue.push([r, width - 1]);
			}
		}

		let head = 0;
		while (head < queue.length) {
			const [r, c] = queue[head++];
			if (r > 0 && !outsideReachable[r - 1][c] && !borderSet.has(edgeKey('h', r, c))) {
				outsideReachable[r - 1][c] = true;
				queue.push([r - 1, c]);
			}
			if (r + 1 < height && !outsideReachable[r + 1][c] && !borderSet.has(edgeKey('h', r + 1, c))) {
				outsideReachable[r + 1][c] = true;
				queue.push([r + 1, c]);
			}
			if (c > 0 && !outsideReachable[r][c - 1] && !borderSet.has(edgeKey('v', r, c))) {
				outsideReachable[r][c - 1] = true;
				queue.push([r, c - 1]);
			}
			if (c + 1 < width && !outsideReachable[r][c + 1] && !borderSet.has(edgeKey('v', r, c + 1))) {
				outsideReachable[r][c + 1] = true;
				queue.push([r, c + 1]);
			}
		}

		const isAllFourDrawn = (r: number, c: number) =>
			borderSet.has(edgeKey('h', r, c)) &&
			borderSet.has(edgeKey('h', r + 1, c)) &&
			borderSet.has(edgeKey('v', r, c)) &&
			borderSet.has(edgeKey('v', r, c + 1));

		const enclosed: [number, number][] = [];
		for (let r = 0; r < height; r++) {
			for (let c = 0; c < width; c++) {
				if (!outsideReachable[r][c] && !isAllFourDrawn(r, c)) {
					enclosed.push([r, c]);
				}
			}
		}

		const active: boolean[][] = Array.from({ length: height }, () => Array(width).fill(false));
		if (enclosed.length > 0) {
			for (const [r, c] of enclosed) {
				active[r][c] = true;
			}
		} else {
			for (let r = 0; r < height; r++) {
				for (let c = 0; c < width; c++) {
					if (!isAllFourDrawn(r, c)) {
						active[r][c] = true;
					}
				}
			}
		}
		return active;
	}

	function edgeTouchesActiveSquare(
		orientation: 'h' | 'v',
		row: number,
		col: number,
		activeGrid: boolean[][],
		w: number,
		h: number
	): boolean {
		if (orientation === 'h') {
			if (row > 0 && activeGrid[row - 1]?.[col]) return true;
			if (row < h && activeGrid[row]?.[col]) return true;
			return false;
		} else {
			if (col > 0 && activeGrid[row]?.[col - 1]) return true;
			if (col < w && activeGrid[row]?.[col]) return true;
			return false;
		}
	}

	function dotVisible(
		r: number,
		c: number,
		activeGrid: boolean[][],
		w: number,
		h: number
	): boolean {
		const neighbors = [
			[r - 1, c - 1],
			[r - 1, c],
			[r, c - 1],
			[r, c]
		];
		return neighbors.some(([nr, nc]) => nr >= 0 && nr < h && nc >= 0 && nc < w && activeGrid[nr]?.[nc]);
	}

	function scribblyLinePath(x1: number, y1: number, x2: number, y2: number, seed: number): string {
		const mx = (x1 + x2) / 2;
		const my = (y1 + y2) / 2;
		const wobble = ((seed * 17) % 5) - 2; // -2..+2 px hand-drawn curve
		if (y1 === y2) {
			return `M ${x1} ${y1} Q ${mx} ${my + wobble * 0.9} ${x2} ${y2}`;
		} else {
			return `M ${x1} ${y1} Q ${mx + wobble * 0.9} ${my} ${x2} ${y2}`;
		}
	}

	function updateDimensions(newWidth: number, newHeight: number) {
		if (!isHost) return;
		// Keep valid border edges within new dimensions
		const filtered = cfgBorderEdges.filter((k) => {
			const [ori, rs, cs] = k.split(':');
			const r = Number(rs);
			const c = Number(cs);
			if (ori === 'h') return r >= 0 && r <= newHeight && c >= 0 && c < newWidth;
			return r >= 0 && r < newHeight && c >= 0 && c <= newWidth;
		});
		client.updateConfig({
			width: newWidth,
			height: newHeight,
			border_edges: filtered
		});
	}

	function setBorderEdge(orientation: 'h' | 'v', row: number, col: number, mode: 'add' | 'remove') {
		if (!isHost) return;
		const key = edgeKey(orientation, row, col);
		const next = new Set(cfgBorderSet);
		if (mode === 'add') {
			if (next.has(key)) return;
			next.add(key);
		} else {
			if (!next.has(key)) return;
			next.delete(key);
		}
		client.updateConfig({ border_edges: Array.from(next) });
	}

	function handleEditorEdgePointerDown(
		e: PointerEvent,
		orientation: 'h' | 'v',
		row: number,
		col: number
	) {
		if (!isHost) return;
		e.preventDefault();
		const key = edgeKey(orientation, row, col);
		const mode: 'add' | 'remove' = cfgBorderSet.has(key) ? 'remove' : 'add';
		dragDrawMode = mode;
		setBorderEdge(orientation, row, col, mode);
	}

	function handleEditorEdgePointerEnter(orientation: 'h' | 'v', row: number, col: number) {
		if (!isHost || !dragDrawMode) return;
		setBorderEdge(orientation, row, col, dragDrawMode);
	}

	function applyShapePreset(preset: 'open' | 'outer_border' | 'cross' | 'diamond') {
		if (!isHost) return;
		const w = cfgWidth;
		const h = cfgHeight;

		if (preset === 'open') {
			client.updateConfig({ border_edges: [] });
			return;
		}

		if (preset === 'outer_border') {
			const edges: string[] = [];
			for (let c = 0; c < w; c++) {
				edges.push(edgeKey('h', 0, c));
				edges.push(edgeKey('h', h, c));
			}
			for (let r = 0; r < h; r++) {
				edges.push(edgeKey('v', r, 0));
				edges.push(edgeKey('v', r, w));
			}
			client.updateConfig({ border_edges: edges });
			return;
		}

		// Build a mask of included cells and extract its boundary edges
		const mask: boolean[][] = Array.from({ length: h }, () => Array(w).fill(false));
		if (preset === 'cross') {
			const cutR = Math.max(1, Math.floor(h / 3));
			const cutC = Math.max(1, Math.floor(w / 3));
			for (let r = 0; r < h; r++) {
				for (let c = 0; c < w; c++) {
					const inCorner =
						(r < cutR && c < cutC) ||
						(r < cutR && c >= w - cutC) ||
						(r >= h - cutR && c < cutC) ||
						(r >= h - cutR && c >= w - cutC);
					mask[r][c] = !inCorner;
				}
			}
		} else if (preset === 'diamond') {
			const cr = (h - 1) / 2;
			const cc = (w - 1) / 2;
			const rad = Math.max(1.2, (Math.min(w, h) - 1) / 2 + 0.35);
			for (let r = 0; r < h; r++) {
				for (let c = 0; c < w; c++) {
					if (Math.abs(r - cr) + Math.abs(c - cc) <= rad) {
						mask[r][c] = true;
					}
				}
			}
		}

		const boundaryEdges: string[] = [];
		for (let r = 0; r <= h; r++) {
			for (let c = 0; c < w; c++) {
				const above = r > 0 ? mask[r - 1][c] : false;
				const below = r < h ? mask[r][c] : false;
				if (above !== below) {
					boundaryEdges.push(edgeKey('h', r, c));
				}
			}
		}
		for (let r = 0; r < h; r++) {
			for (let c = 0; c <= w; c++) {
				const left = c > 0 ? mask[r][c - 1] : false;
				const right = c < w ? mask[r][c] : false;
				if (left !== right) {
					boundaryEdges.push(edgeKey('v', r, c));
				}
			}
		}
		client.updateConfig({ border_edges: boundaryEdges });
	}

	function drawGameLine(orientation: 'h' | 'v', row: number, col: number) {
		if (!isMyTurn) return;
		if (orientation === 'h') {
			if (hEdges[row]?.[col] !== null) return;
		} else {
			if (vEdges[row]?.[col] !== null) return;
		}
		client.sendAction({
			type: 'draw_line',
			orientation,
			row,
			col
		});
	}

	function getEdgeStrokeColor(owner: string | null | undefined): string {
		if (!owner) return 'transparent';
		if (owner === 'border') return '#1a1917';
		return resolvePlayerColor(owner, profile.playerId, profile.primaryColor, players);
	}

	function getPlayerInitial(playerId: string | null | undefined): string {
		if (!playerId) return '';
		const p = players.find((pl) => pl.player_id === playerId);
		if (!p || !p.name) return '•';
		return p.name.trim().slice(0, 1).toUpperCase();
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

	onMount(() => {
		profile.init();
		client.connect({
			gameSlug: 'kaesekaestchen',
			roomId,
			playerId: profile.playerId,
			name: profile.name,
			color: profile.primaryColor
		});

		const unsub = client.onEvent((ev: ServerEvent) => {
			if (ev.type === 'line_drawn' && ev.closed_squares.length > 0) {
				const firstSq = ev.closed_squares[0];
				const id = ++popupCounter;
				scorePopups = [
					...scorePopups,
					{
						id,
						row: firstSq.row,
						col: firstSq.col,
						player_id: ev.player_id,
						points_delta: ev.points_delta
					}
				];
				setTimeout(() => {
					scorePopups = scorePopups.filter((s) => s.id !== id);
				}, 1150);
			}
		});

		const stopDrag = () => {
			dragDrawMode = null;
		};
		window.addEventListener('pointerup', stopDrag);
		window.addEventListener('pointercancel', stopDrag);

		return () => {
			window.removeEventListener('pointerup', stopDrag);
			window.removeEventListener('pointercancel', stopDrag);
			unsub();
			client.disconnect();
		};
	});
</script>

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
				<h1 class="font-hand text-lg leading-none sm:text-xl">Käsekästchen</h1>
				<div class="font-mono-num flex items-center gap-2 text-[11px] text-[#6e6a63]">
					<span>#{roomId}</span>
					<span>•</span>
					<span>{boardWidth}×{boardHeight}</span>
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

					<!-- Dimensions -->
					<div class="grid gap-3 sm:grid-cols-2">
						<div>
							<span class="mb-1 block text-xs font-medium text-[#6e6a63] uppercase">
								Width ({cfgWidth})
							</span>
							<div class="flex flex-wrap gap-1">
								{#each SIZES as w (w)}
									<button
										type="button"
										disabled={!isHost}
										onclick={() => updateDimensions(w, cfgHeight)}
										class="font-mono-num h-7 w-7 cursor-pointer rounded border border-[#1a1917] text-xs font-semibold transition disabled:cursor-not-allowed
										{cfgWidth === w
											? 'bg-[#1a1917] text-[#faf8f4]'
											: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
									>
										{w}
									</button>
								{/each}
							</div>
						</div>

						<div>
							<span class="mb-1 block text-xs font-medium text-[#6e6a63] uppercase">
								Height ({cfgHeight})
							</span>
							<div class="flex flex-wrap gap-1">
								{#each SIZES as h (h)}
									<button
										type="button"
										disabled={!isHost}
										onclick={() => updateDimensions(cfgWidth, h)}
										class="font-mono-num h-7 w-7 cursor-pointer rounded border border-[#1a1917] text-xs font-semibold transition disabled:cursor-not-allowed
										{cfgHeight === h
											? 'bg-[#1a1917] text-[#faf8f4]'
											: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
									>
										{h}
									</button>
								{/each}
							</div>
						</div>
					</div>

					<!-- Shape & Border Presets -->
					<div class="border-t border-[#1a1917]/15 pt-3">
						<div class="mb-2 flex flex-wrap items-center justify-between gap-2">
							<span class="text-xs font-semibold uppercase text-[#1a1917]">
								Board Outline
							</span>
							<span class="font-mono-num rounded border border-[#1a1917]/30 bg-[#f3efe6] px-2 py-0.5 text-xs font-semibold">
								{lobbyActiveCount} square{lobbyActiveCount === 1 ? '' : 's'}
							</span>
						</div>

						{#if isHost}
							<div class="mb-3 flex flex-wrap gap-1.5">
								<button
									type="button"
									onclick={() => applyShapePreset('open')}
									class="cursor-pointer rounded border border-[#1a1917] bg-[#faf8f4] px-2.5 py-1 text-xs font-medium hover:bg-[#f2eee6]"
								>
									Open
								</button>
								<button
									type="button"
									onclick={() => applyShapePreset('outer_border')}
									class="cursor-pointer rounded border border-[#1a1917] bg-[#faf8f4] px-2.5 py-1 text-xs font-medium hover:bg-[#f2eee6]"
								>
									Outer Border
								</button>
								{#if cfgWidth >= 4 && cfgHeight >= 4}
									<button
										type="button"
										onclick={() => applyShapePreset('cross')}
										class="cursor-pointer rounded border border-[#1a1917] bg-[#faf8f4] px-2.5 py-1 text-xs font-medium hover:bg-[#f2eee6]"
									>
										Cross
									</button>
									<button
										type="button"
										onclick={() => applyShapePreset('diamond')}
										class="cursor-pointer rounded border border-[#1a1917] bg-[#faf8f4] px-2.5 py-1 text-xs font-medium hover:bg-[#f2eee6]"
									>
										Diamond
									</button>
								{/if}
							</div>
						{/if}

						<!-- Interactive SVG Outline Editor -->
						<div class="mx-auto max-w-[380px] select-none rounded-md border border-[#1a1917]/20 bg-[#f3efe6]/50 p-2">
							<svg
								viewBox="0 0 {cfgWidth * CELL_STEP + PAD * 2} {cfgHeight * CELL_STEP + PAD * 2}"
								class="h-auto max-h-[320px] w-full touch-none"
								aria-label="Custom Board Outline Editor"
							>
								<!-- Active square shading preview -->
								{#each Array.from({ length: cfgHeight }, (_, r) => r) as r (r)}
									{#each Array.from({ length: cfgWidth }, (_, c) => c) as c (c)}
										{@const isActive = lobbyActivePreview[r]?.[c] ?? true}
										<rect
											x={PAD + c * CELL_STEP + 3}
											y={PAD + r * CELL_STEP + 3}
											width={CELL_STEP - 6}
											height={CELL_STEP - 6}
											rx="3"
											fill={isActive ? '#faf8f4' : 'transparent'}
											stroke={isActive ? '#1a1917' : 'none'}
											stroke-opacity={isActive ? '0.12' : '0'}
											stroke-width="1"
										/>
									{/each}
								{/each}

								<!-- Horizontal edges -->
								{#each Array.from({ length: cfgHeight + 1 }, (_, r) => r) as r (r)}
									{#each Array.from({ length: cfgWidth }, (_, c) => c) as c (c)}
										{@const key = edgeKey('h', r, c)}
										{@const drawn = cfgBorderSet.has(key)}
										{@const x1 = PAD + c * CELL_STEP}
										{@const y1 = PAD + r * CELL_STEP}
										{@const x2 = PAD + (c + 1) * CELL_STEP}
										{@const y2 = y1}
										<!-- Faint guide line -->
										<line
											{x1}
											{y1}
											{x2}
											{y2}
											stroke="#1a1917"
											stroke-opacity="0.16"
											stroke-width="1.5"
											stroke-dasharray="3 3"
										/>
										{#if drawn}
											<path
												d={scribblyLinePath(x1, y1, x2, y2, r * 31 + c * 7)}
												fill="none"
												stroke="#1a1917"
												stroke-width="4.5"
												stroke-linecap="round"
											/>
										{/if}
										{#if isHost}
											<line
												{x1}
												{y1}
												{x2}
												{y2}
												stroke="transparent"
												stroke-width="18"
												class="cursor-pointer"
												role="button"
												tabindex="0"
												aria-label="Toggle horizontal border edge row {r + 1} column {c + 1}"
												onpointerdown={(e) => handleEditorEdgePointerDown(e, 'h', r, c)}
												onpointerenter={() => handleEditorEdgePointerEnter('h', r, c)}
												onkeydown={(e) => {
													if (e.key === 'Enter' || e.key === ' ') {
														e.preventDefault();
														setBorderEdge('h', r, c, cfgBorderSet.has(key) ? 'remove' : 'add');
													}
												}}
											/>
										{/if}
									{/each}
								{/each}

								<!-- Vertical edges -->
								{#each Array.from({ length: cfgHeight }, (_, r) => r) as r (r)}
									{#each Array.from({ length: cfgWidth + 1 }, (_, c) => c) as c (c)}
										{@const key = edgeKey('v', r, c)}
										{@const drawn = cfgBorderSet.has(key)}
										{@const x1 = PAD + c * CELL_STEP}
										{@const y1 = PAD + r * CELL_STEP}
										{@const x2 = x1}
										{@const y2 = PAD + (r + 1) * CELL_STEP}
										<line
											{x1}
											{y1}
											{x2}
											{y2}
											stroke="#1a1917"
											stroke-opacity="0.16"
											stroke-width="1.5"
											stroke-dasharray="3 3"
										/>
										{#if drawn}
											<path
												d={scribblyLinePath(x1, y1, x2, y2, r * 19 + c * 43)}
												fill="none"
												stroke="#1a1917"
												stroke-width="4.5"
												stroke-linecap="round"
											/>
										{/if}
										{#if isHost}
											<line
												{x1}
												{y1}
												{x2}
												{y2}
												stroke="transparent"
												stroke-width="18"
												class="cursor-pointer"
												role="button"
												tabindex="0"
												aria-label="Toggle vertical border edge row {r + 1} column {c + 1}"
												onpointerdown={(e) => handleEditorEdgePointerDown(e, 'v', r, c)}
												onpointerenter={() => handleEditorEdgePointerEnter('v', r, c)}
												onkeydown={(e) => {
													if (e.key === 'Enter' || e.key === ' ') {
														e.preventDefault();
														setBorderEdge('v', r, c, cfgBorderSet.has(key) ? 'remove' : 'add');
													}
												}}
											/>
										{/if}
									{/each}
								{/each}

								<!-- Grid vertices (dots) -->
								{#each Array.from({ length: cfgHeight + 1 }, (_, r) => r) as r (r)}
									{#each Array.from({ length: cfgWidth + 1 }, (_, c) => c) as c (c)}
										<circle
											cx={PAD + c * CELL_STEP}
											cy={PAD + r * CELL_STEP}
											r="3.6"
											fill="#1a1917"
										/>
									{/each}
								{/each}
							</svg>
						</div>
					</div>
				</div>
			{/snippet}
		</Lobby>
	{:else}
		<!-- Active or Finished Käsekästchen Board View -->
		<div class="mx-auto flex w-full max-w-xl flex-1 flex-col justify-between gap-3">
			<!-- Players & Turn Status Bar -->
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
							<span class="max-w-[96px] truncate text-xs font-semibold" style="color: {pColor};">
								{p.name}
							</span>
							<span class="font-mono-num text-xs font-bold text-[#1a1917]">
								{p.score}
							</span>
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

				<div class="font-mono-num text-xs text-[#6e6a63]">
					{gameState.claimed_squares ?? 0}/{gameState.total_squares ?? boardWidth * boardHeight} squares
				</div>
			</div>

			<!-- Current Turn Prompt or Game Over Banner -->
			{#if room.status === 'finished'}
				<ScribblyBox seed={55} class="bg-[#faf8f4] p-4 text-center">
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
					class="flex items-center justify-between rounded-md border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-2 text-xs shadow-[1.5px_1.5px_0px_#1a1917]"
				>
					{#if isMyTurn}
						<div class="flex items-center gap-2 font-semibold" style="color: {profile.primaryColor};">
							<span
								class="inline-block h-2.5 w-2.5 rounded-full border border-[#1a1917]"
								style="background-color: {profile.primaryColor};"
							></span>
							<span>Your turn</span>
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
						<span class="text-[#6e6a63]">Waiting for move…</span>
					{/if}
				</div>
			{/if}

			<!-- Main Scribbly SVG Käsekästchen Board -->
			<div class="relative mx-auto flex w-full max-w-[500px] flex-1 items-center justify-center select-none">
				<svg
					viewBox="0 0 {boardWidth * CELL_STEP + PAD * 2} {boardHeight * CELL_STEP + PAD * 2}"
					class="h-auto max-h-[68vh] w-full touch-manipulation"
					role="application"
					aria-label="Käsekästchen Game Board"
				>
					<!-- 1. Active Squares & Claimed Hatching Fills -->
					{#each Array.from({ length: boardHeight }, (_, r) => r) as r (r)}
						{#each Array.from({ length: boardWidth }, (_, c) => c) as c (c)}
							{@const isActive = activeSquares[r]?.[c] ?? false}
							{@const ownerId = squareOwners[r]?.[c] ?? null}
							{@const x = PAD + c * CELL_STEP}
							{@const y = PAD + r * CELL_STEP}
							{#if isActive}
								{#if ownerId}
									{@const ownerColor = resolvePlayerColor(
										ownerId,
										profile.playerId,
										profile.primaryColor,
										players
									)}
									<g class="animate-scribble-pop" style="transform-origin: {x + CELL_STEP / 2}px {y + CELL_STEP / 2}px;">
										<rect
											x={x + 5}
											y={y + 5}
											width={CELL_STEP - 10}
											height={CELL_STEP - 10}
											rx="4"
											fill={ownerColor}
											fill-opacity="0.16"
										/>
										<!-- Hand-drawn diagonal scribble strokes inside completed square -->
										<path
											d="M {x + 11} {y + CELL_STEP - 13} L {x + 25} {y + 11} M {x + 21} {y + CELL_STEP - 11} L {x + CELL_STEP - 12} {y + 16} M {x + 33} {y + CELL_STEP - 12} L {x + CELL_STEP - 11} {y + 30}"
											stroke={ownerColor}
											stroke-width="1.8"
											stroke-linecap="round"
											stroke-opacity="0.35"
										/>
										<text
											x={x + CELL_STEP / 2}
											y={y + CELL_STEP / 2 + 6}
											text-anchor="middle"
											fill={ownerColor}
											class="font-hand text-[19px] font-bold"
										>
											{getPlayerInitial(ownerId)}
										</text>
									</g>
								{/if}
							{/if}
						{/each}
					{/each}

					<!-- 2. Horizontal Grid Edges -->
					{#each Array.from({ length: boardHeight + 1 }, (_, r) => r) as r (r)}
						{#each Array.from({ length: boardWidth }, (_, c) => c) as c (c)}
							{@const playable = edgeTouchesActiveSquare(
								'h',
								r,
								c,
								activeSquares,
								boardWidth,
								boardHeight
							)}
							{#if playable}
								{@const owner = hEdges[r]?.[c] ?? null}
								{@const isLastMove =
									gameState.last_move?.orientation === 'h' &&
									gameState.last_move?.row === r &&
									gameState.last_move?.col === c}
								{@const isHovered =
									isMyTurn &&
									owner === null &&
									hoveredEdge?.orientation === 'h' &&
									hoveredEdge?.row === r &&
									hoveredEdge?.col === c}
								{@const x1 = PAD + c * CELL_STEP}
								{@const y1 = PAD + r * CELL_STEP}
								{@const x2 = PAD + (c + 1) * CELL_STEP}
								{@const y2 = y1}

								<!-- Faint dotted guide for undrawn playable edge -->
								{#if owner === null}
									<line
										{x1}
										{y1}
										{x2}
										{y2}
										stroke={isHovered ? profile.primaryColor : '#1a1917'}
										stroke-opacity={isHovered ? '0.65' : '0.16'}
										stroke-width={isHovered ? '3.5' : '1.5'}
										stroke-dasharray={isHovered ? 'none' : '3 4'}
										stroke-linecap="round"
									/>
								{:else}
									{@const strokeColor = getEdgeStrokeColor(owner)}
									{#if isLastMove}
										<path
											d={scribblyLinePath(x1, y1, x2, y2, r * 31 + c * 7)}
											fill="none"
											stroke={strokeColor}
											stroke-opacity="0.25"
											stroke-width="10"
											stroke-linecap="round"
										/>
									{/if}
									<path
										d={scribblyLinePath(x1, y1, x2, y2, r * 31 + c * 7)}
										fill="none"
										stroke={strokeColor}
										stroke-width="4.8"
										stroke-linecap="round"
									/>
								{/if}

								<!-- Wide interactive hit target -->
								{#if owner === null && room.status === 'playing'}
									<line
										{x1}
										{y1}
										{x2}
										{y2}
										stroke="transparent"
										stroke-width="22"
										class={isMyTurn ? 'cursor-pointer' : 'cursor-default'}
										role="button"
										tabindex={isMyTurn ? 0 : -1}
										aria-label="Horizontal edge row {r + 1} column {c + 1}"
										onpointerenter={() => (hoveredEdge = { orientation: 'h', row: r, col: c })}
										onpointerleave={() => (hoveredEdge = null)}
										onclick={() => drawGameLine('h', r, c)}
										onkeydown={(e) => {
											if (e.key === 'Enter' || e.key === ' ') {
												e.preventDefault();
												drawGameLine('h', r, c);
											}
										}}
									/>
								{/if}
							{/if}
						{/each}
					{/each}

					<!-- 3. Vertical Grid Edges -->
					{#each Array.from({ length: boardHeight }, (_, r) => r) as r (r)}
						{#each Array.from({ length: boardWidth + 1 }, (_, c) => c) as c (c)}
							{@const playable = edgeTouchesActiveSquare(
								'v',
								r,
								c,
								activeSquares,
								boardWidth,
								boardHeight
							)}
							{#if playable}
								{@const owner = vEdges[r]?.[c] ?? null}
								{@const isLastMove =
									gameState.last_move?.orientation === 'v' &&
									gameState.last_move?.row === r &&
									gameState.last_move?.col === c}
								{@const isHovered =
									isMyTurn &&
									owner === null &&
									hoveredEdge?.orientation === 'v' &&
									hoveredEdge?.row === r &&
									hoveredEdge?.col === c}
								{@const x1 = PAD + c * CELL_STEP}
								{@const y1 = PAD + r * CELL_STEP}
								{@const x2 = x1}
								{@const y2 = PAD + (r + 1) * CELL_STEP}

								{#if owner === null}
									<line
										{x1}
										{y1}
										{x2}
										{y2}
										stroke={isHovered ? profile.primaryColor : '#1a1917'}
										stroke-opacity={isHovered ? '0.65' : '0.16'}
										stroke-width={isHovered ? '3.5' : '1.5'}
										stroke-dasharray={isHovered ? 'none' : '3 4'}
										stroke-linecap="round"
									/>
								{:else}
									{@const strokeColor = getEdgeStrokeColor(owner)}
									{#if isLastMove}
										<path
											d={scribblyLinePath(x1, y1, x2, y2, r * 19 + c * 43)}
											fill="none"
											stroke={strokeColor}
											stroke-opacity="0.25"
											stroke-width="10"
											stroke-linecap="round"
										/>
									{/if}
									<path
										d={scribblyLinePath(x1, y1, x2, y2, r * 19 + c * 43)}
										fill="none"
										stroke={strokeColor}
										stroke-width="4.8"
										stroke-linecap="round"
									/>
								{/if}

								{#if owner === null && room.status === 'playing'}
									<line
										{x1}
										{y1}
										{x2}
										{y2}
										stroke="transparent"
										stroke-width="22"
										class={isMyTurn ? 'cursor-pointer' : 'cursor-default'}
										role="button"
										tabindex={isMyTurn ? 0 : -1}
										aria-label="Vertical edge row {r + 1} column {c + 1}"
										onpointerenter={() => (hoveredEdge = { orientation: 'v', row: r, col: c })}
										onpointerleave={() => (hoveredEdge = null)}
										onclick={() => drawGameLine('v', r, c)}
										onkeydown={(e) => {
											if (e.key === 'Enter' || e.key === ' ') {
												e.preventDefault();
												drawGameLine('v', r, c);
											}
										}}
									/>
								{/if}
							{/if}
						{/each}
					{/each}

					<!-- 4. Grid Dots (Vertices) -->
					{#each Array.from({ length: boardHeight + 1 }, (_, r) => r) as r (r)}
						{#each Array.from({ length: boardWidth + 1 }, (_, c) => c) as c (c)}
							{#if dotVisible(r, c, activeSquares, boardWidth, boardHeight)}
								<circle
									cx={PAD + c * CELL_STEP}
									cy={PAD + r * CELL_STEP}
									r="4.2"
									fill="#1a1917"
								/>
							{/if}
						{/each}
					{/each}

					<!-- 5. Floating Score Popups -->
					{#each scorePopups as pop (pop.id)}
						{@const popColor = resolvePlayerColor(
							pop.player_id,
							profile.playerId,
							profile.primaryColor,
							players
						)}
						{@const px = PAD + (pop.col + 0.5) * CELL_STEP}
						{@const py = PAD + pop.row * CELL_STEP}
						<g class="animate-float-score pointer-events-none">
							<rect
								x={px - 18}
								y={py - 14}
								width="36"
								height="20"
								rx="4"
								fill="#faf8f4"
								stroke="#1a1917"
								stroke-width="1.4"
							/>
							<text
								x={px}
								y={py}
								text-anchor="middle"
								fill={popColor}
								class="font-mono-num text-[12px] font-bold"
							>
								+{pop.points_delta}
							</text>
						</g>
					{/each}
				</svg>
			</div>
		</div>
	{/if}
</div>
