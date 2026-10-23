<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import ProfileBadge from '$lib/core/components/ProfileBadge.svelte';
	import ScribblyBox from '$lib/core/components/ScribblyBox.svelte';
	import ScribblyButton from '$lib/core/components/ScribblyButton.svelte';
	import { profile } from '$lib/core/profile.svelte';

	interface RecentRoom {
		room_id: string;
		game_slug: string;
		status: 'lobby' | 'playing' | 'finished';
		config: {
			difficulty?: string;
			scoring_enabled?: boolean;
			width?: number;
			height?: number;
		};
		score: number;
		player_count: number;
		updated_at: string | null;
	}

	interface PlayerStatsSummary {
		rooms_joined: number;
		active_rooms: number;
		games_completed: number;
		games_won: number;
		total_score: number;
		best_score: number;
	}

	let difficulty = $state<'easy' | 'medium' | 'hard' | 'expert'>('medium');
	let scoringEnabled = $state<boolean>(true);
	let kaeseWidth = $state<number>(6);
	let kaeseHeight = $state<number>(6);
	let creatingSudoku = $state<boolean>(false);
	let creatingKaese = $state<boolean>(false);
	let recentRooms = $state<RecentRoom[]>([]);
	let stats = $state<PlayerStatsSummary | null>(null);
	let joinCode = $state<string>('');
	let joinError = $state<string | null>(null);

	const BOARD_PRESET_SIZES: { label: string; w: number; h: number }[] = [
		{ label: '4×4', w: 4, h: 4 },
		{ label: '6×6', w: 6, h: 6 },
		{ label: '8×8', w: 8, h: 8 },
		{ label: '10×10', w: 10, h: 10 }
	];

	async function loadPlayerDashboard() {
		if (!profile.playerId) return;
		try {
			const [recentRes, statsRes] = await Promise.all([
				fetch(`/api/players/${encodeURIComponent(profile.playerId)}/recent`),
				fetch(`/api/players/${encodeURIComponent(profile.playerId)}/stats`)
			]);
			if (recentRes.ok) {
				recentRooms = await recentRes.json();
			}
			if (statsRes.ok) {
				const data = await statsRes.json();
				stats = data.summary;
			}
		} catch (e) {
			console.error('Failed to load player dashboard:', e);
		}
	}

	onMount(() => {
		profile.init();
		loadPlayerDashboard();
	});

	async function createSudokuRoom() {
		if (creatingSudoku) return;
		creatingSudoku = true;
		try {
			const res = await fetch('/api/rooms', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					game_slug: 'sudoku',
					host_player_id: profile.playerId,
					host_name: profile.name,
					host_color: profile.primaryColor,
					config: {
						difficulty,
						scoring_enabled: scoringEnabled
					}
				})
			});
			if (res.ok) {
				const room = await res.json();
				await goto(`/sudoku/${room.room_id}`);
			}
		} finally {
			creatingSudoku = false;
		}
	}

	async function createKaesekaestchenRoom() {
		if (creatingKaese) return;
		creatingKaese = true;
		try {
			const res = await fetch('/api/rooms', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					game_slug: 'kaesekaestchen',
					host_player_id: profile.playerId,
					host_name: profile.name,
					host_color: profile.primaryColor,
					config: {
						width: kaeseWidth,
						height: kaeseHeight,
						border_edges: []
					}
				})
			});
			if (res.ok) {
				const room = await res.json();
				await goto(`/kaesekaestchen/${room.room_id}`);
			}
		} finally {
			creatingKaese = false;
		}
	}

	async function handleJoinByCode(e: SubmitEvent) {
		e.preventDefault();
		joinError = null;
		const code = joinCode.trim().toLowerCase().replace(/^#/, '');
		if (!code) return;
		try {
			const res = await fetch(`/api/rooms/${encodeURIComponent(code)}`);
			if (res.ok) {
				const room = await res.json();
				await goto(`/${room.game_slug}/${room.room_id}`);
			} else {
				joinError = `Room #${code} not found`;
			}
		} catch {
			await goto(`/sudoku/${code}`);
		}
	}

	function formatGameTitle(slug: string): string {
		if (slug === 'kaesekaestchen') return 'Käsekästchen';
		if (slug === 'sudoku') return 'Sudoku';
		return slug;
	}

	function formatRoomSubtitle(item: RecentRoom): string {
		if (item.game_slug === 'kaesekaestchen') {
			const w = item.config?.width ?? 6;
			const h = item.config?.height ?? 6;
			return `${w}×${h}`;
		}
		return item.config?.difficulty ?? 'medium';
	}

	function formatRelativeTime(iso: string | null): string {
		if (!iso) return '';
		const diffSec = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
		if (diffSec < 60) return 'just now';
		if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
		if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
		return `${Math.floor(diffSec / 86400)}d ago`;
	}
</script>

<svelte:head>
	<title>games.jakob-r.de • Minimalistic Multiplayer Games</title>
</svelte:head>

<main class="mx-auto w-full max-w-2xl flex-1 px-4 py-6 sm:px-6 sm:py-10">
	<!-- Header -->
	<header class="mb-7 flex flex-wrap items-baseline justify-between gap-3 border-b-2 border-[#1a1917] pb-3">
		<div>
			<h1 class="font-hand text-3xl tracking-tight sm:text-4xl">games.jakob-r.de</h1>
		</div>

		<form onsubmit={handleJoinByCode} class="flex items-center gap-2">
			<input
				type="text"
				bind:value={joinCode}
				placeholder="Room ID…"
				maxlength="12"
				class="font-mono-num w-28 rounded-md border-[1.6px] border-[#1a1917] bg-white px-2.5 py-1.5 text-xs focus:outline-none"
			/>
			<ScribblyButton type="submit">Join Room</ScribblyButton>
		</form>
	</header>

	{#if joinError}
		<div class="mb-4 rounded border border-[#dc2626] bg-[#faf8f4] px-3 py-2 text-xs font-medium text-[#dc2626]">
			{joinError}
		</div>
	{/if}

	<div class="space-y-6">
		<!-- Section 1: Player Identity & Primary Color -->
		<ScribblyBox seed={7} class="bg-[#faf8f4] p-4 sm:p-6">
			<h2 class="font-hand mb-3 text-xl">1. Who are you?</h2>
			<ProfileBadge />
		</ScribblyBox>

		<!-- Section 2A: Multiplayer Sudoku -->
		<ScribblyBox seed={19} class="bg-[#faf8f4] p-4 sm:p-6">
			<div class="flex items-center justify-between gap-2">
				<h2 class="font-hand text-2xl">Multiplayer Sudoku</h2>
				<span
					title="1 or more players"
					aria-label="1 or more players"
					class="inline-flex items-center gap-1 text-xs font-medium text-[#6e6a63]"
				>
					<svg
						class="h-4 w-4"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
						<circle cx="9" cy="7" r="4" />
						<path d="M22 21v-2a4 4 0 0 0-3-3.87" />
						<path d="M16 3.13a4 4 0 0 1 0 7.75" />
					</svg>
					<span class="font-mono-num">1–8</span>
				</span>
			</div>

			<p class="mt-1.5 text-sm text-[#6e6a63]">
				Solve the same 9×9 board together in real time. Add corner notes (1–9), see every player's
				strokes in their own ink color, and build a 1.1× speed multiplier within 10 seconds.
			</p>

			<div class="mt-4 grid gap-4 border-t border-[#1a1917]/15 pt-4 sm:grid-cols-2">
				<div>
					<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">
						Starting Difficulty
					</span>
					<div class="grid grid-cols-4 gap-1.5">
						{#each ['easy', 'medium', 'hard', 'expert'] as const as d}
							<button
								type="button"
								onclick={() => (difficulty = d)}
								class="cursor-pointer rounded border-[1.5px] border-[#1a1917] py-1.5 text-xs font-semibold capitalize transition
								{difficulty === d
									? 'bg-[#1a1917] text-[#faf8f4]'
									: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
							>
								{d}
							</button>
						{/each}
					</div>
				</div>

				<div>
					<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">
						Scoring Mode
					</span>
					<button
						type="button"
						onclick={() => (scoringEnabled = !scoringEnabled)}
						class="flex w-full cursor-pointer items-center justify-between rounded border-[1.5px] border-[#1a1917] px-3 py-1.5 text-xs font-semibold transition
						{scoringEnabled ? 'bg-[#1a1917] text-[#faf8f4]' : 'bg-[#faf8f4] text-[#6e6a63]'}"
					>
						<span>{scoringEnabled ? 'Scoring Enabled' : 'Relaxed (Scoring Off)'}</span>
						<span>{scoringEnabled ? 'ON' : 'OFF'}</span>
					</button>
				</div>
			</div>

			<div class="mt-5 flex flex-wrap items-center justify-between gap-3">
				<ScribblyButton
					onclick={createSudokuRoom}
					disabled={creatingSudoku}
					variant="primary"
					accentColor={profile.primaryColor}
					class="w-full sm:w-auto"
				>
					{creatingSudoku ? 'Creating Room…' : 'Create New Sudoku Game →'}
				</ScribblyButton>
			</div>
		</ScribblyBox>

		<!-- Section 2B: Käsekästchen -->
		<ScribblyBox seed={27} class="bg-[#faf8f4] p-4 sm:p-6">
			<div class="flex items-center justify-between gap-2">
				<h2 class="font-hand text-2xl">Käsekästchen</h2>
				<span
					title="2 or more players"
					aria-label="2 or more players"
					class="inline-flex items-center gap-1 text-xs font-medium text-[#6e6a63]"
				>
					<svg
						class="h-4 w-4"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
						<circle cx="9" cy="7" r="4" />
						<path d="M22 21v-2a4 4 0 0 0-3-3.87" />
						<path d="M16 3.13a4 4 0 0 1 0 7.75" />
					</svg>
					<span class="font-mono-num">2+</span>
				</span>
			</div>

			<p class="mt-1.5 text-sm text-[#6e6a63]">
				Round-based Dots & Boxes on a customizable grid. Take turns drawing lines in your color —
				close a square to score a point and immediately draw another line! Custom board outlines can
				be sketched in the lobby.
			</p>

			<div class="mt-4 border-t border-[#1a1917]/15 pt-4">
				<span class="mb-1.5 block text-xs font-medium text-[#6e6a63] uppercase">
					Starting Grid Size (Customizable in Lobby)
				</span>
				<div class="grid grid-cols-4 gap-1.5 sm:max-w-xs">
					{#each BOARD_PRESET_SIZES as preset (preset.label)}
						<button
							type="button"
							onclick={() => {
								kaeseWidth = preset.w;
								kaeseHeight = preset.h;
							}}
							class="font-mono-num cursor-pointer rounded border-[1.5px] border-[#1a1917] py-1.5 text-xs font-semibold transition
							{kaeseWidth === preset.w && kaeseHeight === preset.h
								? 'bg-[#1a1917] text-[#faf8f4]'
								: 'bg-[#faf8f4] text-[#1a1917] hover:bg-[#f2eee6]'}"
						>
							{preset.label}
						</button>
					{/each}
				</div>
			</div>

			<div class="mt-5 flex flex-wrap items-center justify-between gap-3">
				<ScribblyButton
					onclick={createKaesekaestchenRoom}
					disabled={creatingKaese}
					variant="primary"
					accentColor={profile.primaryColor}
					class="w-full sm:w-auto"
				>
					{creatingKaese ? 'Creating Room…' : 'Create New Käsekästchen Game →'}
				</ScribblyButton>
			</div>
		</ScribblyBox>

		<!-- Section 3: Recently Played & Resume -->
		<ScribblyBox seed={31} class="bg-[#faf8f4] p-4 sm:p-6">
			<div class="mb-3 flex items-center justify-between">
				<h2 class="font-hand text-xl">Recently Played Games</h2>
				<span class="text-xs text-[#6e6a63]">Resume where you left off</span>
			</div>

			{#if recentRooms.length === 0}
				<p class="py-3 text-sm text-[#6e6a63]">
					No recent games yet. Create a room above to start playing!
				</p>
			{:else}
				<ul class="divide-y divide-[#1a1917]/10">
					{#each recentRooms as item (item.room_id)}
						<li class="flex items-center justify-between gap-3 py-2.5">
							<div>
								<div class="flex items-center gap-2">
									<span class="font-hand text-sm font-bold">
										{formatGameTitle(item.game_slug)}
									</span>
									<span class="font-mono-num text-xs font-semibold text-[#6e6a63]">
										#{item.room_id}
									</span>
									<span class="text-xs capitalize text-[#6e6a63]">
										{formatRoomSubtitle(item)}
									</span>
									<span
										class="rounded border border-[#1a1917]/30 px-1.5 py-0.2 text-[10px] font-medium uppercase
										{item.status === 'playing'
											? 'bg-[#1a1917] text-[#faf8f4]'
											: 'text-[#6e6a63]'}"
									>
										{item.status}
									</span>
								</div>
								<div class="font-mono-num mt-0.5 text-xs text-[#6e6a63]">
									Score: {item.score} • {item.player_count} player{item.player_count === 1 ? '' : 's'}
									{#if item.updated_at}
										• {formatRelativeTime(item.updated_at)}
									{/if}
								</div>
							</div>

							<a
								href="/{item.game_slug}/{item.room_id}"
								class="inline-flex items-center rounded border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-1.5 text-xs font-semibold shadow-[1.5px_1.5px_0px_#1a1917] transition hover:bg-[#f2eee6]"
							>
								{item.status === 'finished' ? 'View' : 'Resume →'}
							</a>
						</li>
					{/each}
				</ul>
			{/if}
		</ScribblyBox>

		<!-- Section 4: Personal Stats -->
		<ScribblyBox seed={43} class="bg-[#faf8f4] p-4 sm:p-6">
			<h2 class="font-hand mb-3 text-xl">Your Personal Stats</h2>
			<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
				<div class="rounded border border-[#1a1917]/20 bg-[#f3efe6]/60 p-3">
					<div class="text-xs text-[#6e6a63]">Rooms Joined</div>
					<div class="font-mono-num mt-1 text-2xl font-bold">
						{stats?.rooms_joined ?? 0}
					</div>
				</div>
				<div class="rounded border border-[#1a1917]/20 bg-[#f3efe6]/60 p-3">
					<div class="text-xs text-[#6e6a63]">Boards Completed</div>
					<div class="font-mono-num mt-1 text-2xl font-bold">
						{stats?.games_completed ?? 0}
					</div>
				</div>
				<div class="rounded border border-[#1a1917]/20 bg-[#f3efe6]/60 p-3">
					<div class="text-xs text-[#6e6a63]">Best Score</div>
					<div class="font-mono-num mt-1 text-2xl font-bold">
						{stats?.best_score ?? 0}
					</div>
				</div>
				<div class="rounded border border-[#1a1917]/20 bg-[#f3efe6]/60 p-3">
					<div class="text-xs text-[#6e6a63]">Total Points</div>
					<div class="font-mono-num mt-1 text-2xl font-bold">
						{stats?.total_score ?? 0}
					</div>
				</div>
			</div>
		</ScribblyBox>
	</div>
</main>
