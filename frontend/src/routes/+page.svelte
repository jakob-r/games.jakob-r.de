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
		host_player_id: string;
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

	let creatingSudoku = $state<boolean>(false);
	let creatingKaese = $state<boolean>(false);
	let deletingRoomId = $state<string | null>(null);
	let recentRooms = $state<RecentRoom[]>([]);
	let stats = $state<PlayerStatsSummary | null>(null);
	let joinCode = $state<string>('');
	let joinError = $state<string | null>(null);

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
						difficulty: 'medium',
						scoring_enabled: true
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
						width: 6,
						height: 6,
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

	async function deleteRoom(roomId: string) {
		if (!profile.playerId || deletingRoomId) return;
		deletingRoomId = roomId;
		try {
			const res = await fetch(
				`/api/rooms/${encodeURIComponent(roomId)}?player_id=${encodeURIComponent(profile.playerId)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				recentRooms = recentRooms.filter((r) => r.room_id !== roomId);
				await loadPlayerDashboard();
			}
		} catch (e) {
			console.error('Failed to delete room:', e);
		} finally {
			deletingRoomId = null;
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
				Solve a 9×9 board together in real time.
			</p>

			<div class="mt-4 flex flex-wrap items-center justify-between gap-3">
				<ScribblyButton
					onclick={createSudokuRoom}
					disabled={creatingSudoku}
					variant="primary"
					accentColor={profile.primaryColor}
					class="w-full sm:w-auto"
				>
					{creatingSudoku ? 'Creating Room…' : 'New Sudoku →'}
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
				Take turns drawing lines — close a square to score a point and go again.
			</p>

			<div class="mt-4 flex flex-wrap items-center justify-between gap-3">
				<ScribblyButton
					onclick={createKaesekaestchenRoom}
					disabled={creatingKaese}
					variant="primary"
					accentColor={profile.primaryColor}
					class="w-full sm:w-auto"
				>
					{creatingKaese ? 'Creating Room…' : 'New Käsekästchen →'}
				</ScribblyButton>
			</div>
		</ScribblyBox>

		<!-- Section 3: Recently Played & Resume -->
		<ScribblyBox seed={31} class="bg-[#faf8f4] p-4 sm:p-6">
			<div class="mb-3 flex items-center justify-between">
				<h2 class="font-hand text-xl">Recent Games</h2>
			</div>

			{#if recentRooms.length === 0}
				<p class="py-3 text-sm text-[#6e6a63]">
					No recent games yet.
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

							<div class="flex items-center gap-2">
								<a
									href="/{item.game_slug}/{item.room_id}"
									class="inline-flex items-center rounded border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-1.5 text-xs font-semibold shadow-[1.5px_1.5px_0px_#1a1917] transition hover:bg-[#f2eee6]"
								>
									{item.status === 'finished' ? 'View' : 'Resume →'}
								</a>
								{#if item.host_player_id === profile.playerId}
									<button
										type="button"
										onclick={() => deleteRoom(item.room_id)}
										disabled={deletingRoomId === item.room_id}
										title="Permanently delete this session"
										aria-label="Permanently delete room #{item.room_id}"
										class="inline-flex cursor-pointer items-center justify-center rounded border-[1.6px] border-[#1a1917] bg-[#faf8f4] p-1.5 text-[#6e6a63] shadow-[1.5px_1.5px_0px_#1a1917] transition hover:border-[#dc2626] hover:bg-[#fef2f2] hover:text-[#dc2626] disabled:cursor-not-allowed disabled:opacity-50"
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
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		</ScribblyBox>

		<!-- Section 4: Personal Stats -->
		<ScribblyBox seed={43} class="bg-[#faf8f4] p-4 sm:p-6">
			<h2 class="font-hand mb-3 text-xl">Stats</h2>
			<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
				<div class="rounded border border-[#1a1917]/20 bg-[#f3efe6]/60 p-3">
					<div class="text-xs text-[#6e6a63]">Rooms</div>
					<div class="font-mono-num mt-1 text-2xl font-bold">
						{stats?.rooms_joined ?? 0}
					</div>
				</div>
				<div class="rounded border border-[#1a1917]/20 bg-[#f3efe6]/60 p-3">
					<div class="text-xs text-[#6e6a63]">Completed</div>
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
