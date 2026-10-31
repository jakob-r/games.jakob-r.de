<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import DeleteRoomModal from '$lib/core/components/DeleteRoomModal.svelte';
	import ProfileBadge from '$lib/core/components/ProfileBadge.svelte';
	import SeoHead from '$lib/core/components/SeoHead.svelte';
	import ScribblyBox from '$lib/core/components/ScribblyBox.svelte';
	import ScribblyButton from '$lib/core/components/ScribblyButton.svelte';
	import { profile } from '$lib/core/profile.svelte';
	import {
		GAMES,
		SITE_ORIGIN,
		formatGameTitle,
		gamePath,
		roomPath,
		type GameInfo,
		type GameSlug
	} from '$lib/games/catalog';
	import GameLogo from '$lib/games/GameLogo.svelte';

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
			size?: number;
			language?: string;
			mode?: string;
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

	let creatingSlug = $state<GameSlug | null>(null);
	let deletingRoomId = $state<string | null>(null);
	let roomPendingDelete = $state<string | null>(null);
	let leavingRoomId = $state<string | null>(null);
	let recentRooms = $state<RecentRoom[]>([]);
	let stats = $state<PlayerStatsSummary | null>(null);
	let joinCode = $state<string>('');
	let joinError = $state<string | null>(null);

	const landingJsonLd = {
		'@type': 'ItemList',
		'@id': `${SITE_ORIGIN}/#games`,
		name: 'Games on games.jakob-r.de',
		itemListElement: GAMES.map((g, i) => ({
			'@type': 'ListItem',
			position: i + 1,
			url: `${SITE_ORIGIN}${gamePath(g.slug)}`,
			name: g.title,
			description: g.tagline
		}))
	};

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

	async function createRoom(game: GameInfo) {
		if (creatingSlug) return;
		creatingSlug = game.slug;
		try {
			const res = await fetch('/api/rooms', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					game_slug: game.slug,
					host_player_id: profile.playerId,
					host_name: profile.name,
					host_color: profile.primaryColor,
					config: game.defaultConfig
				})
			});
			if (res.ok) {
				const room = await res.json();
				await goto(roomPath(game.slug, room.room_id));
			}
		} finally {
			creatingSlug = null;
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
				roomPendingDelete = null;
				await loadPlayerDashboard();
			}
		} catch (e) {
			console.error('Failed to delete room:', e);
		} finally {
			deletingRoomId = null;
		}
	}

	async function leaveRoom(roomId: string) {
		if (!profile.playerId || leavingRoomId) return;
		const target = recentRooms.find((r) => r.room_id === roomId);
		if (target?.host_player_id === profile.playerId) return;
		leavingRoomId = roomId;
		try {
			const res = await fetch(
				`/api/rooms/${encodeURIComponent(roomId)}/players/${encodeURIComponent(profile.playerId)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				recentRooms = recentRooms.filter((r) => r.room_id !== roomId);
				await loadPlayerDashboard();
			}
		} catch (e) {
			console.error('Failed to leave room:', e);
		} finally {
			leavingRoomId = null;
		}
	}

	function formatRoomSubtitle(item: RecentRoom): string {
		if (item.game_slug === 'kaesekaestchen') {
			const w = item.config?.width ?? 6;
			const h = item.config?.height ?? 6;
			return `${w}×${h}`;
		}
		if (item.game_slug === 'silbenstreit') {
			const sz = item.config?.size ?? 5;
			const lang = (item.config?.language ?? 'de').toUpperCase();
			return `${sz}×${sz} • ${lang}`;
		}
		if (item.game_slug === 'emoji-charades') {
			const mode = item.config?.mode === 'remote' ? 'Remote' : 'In person';
			return `${mode} • ${(item.config?.language ?? 'de').toUpperCase()}`;
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

<SeoHead
	title="Minimalistic multiplayer games"
	description="Minimalistic multiplayer games with a scribbly look. Create a room, share the link, play together. No ads, no tracking, hosted in Europe (Germany)."
	path="/"
	jsonLd={landingJsonLd}
/>

<DeleteRoomModal
	open={roomPendingDelete !== null}
	roomId={roomPendingDelete ?? ''}
	deleting={deletingRoomId === roomPendingDelete}
	onConfirm={() => {
		if (roomPendingDelete) return deleteRoom(roomPendingDelete);
	}}
	onClose={() => {
		if (!deletingRoomId) roomPendingDelete = null;
	}}
/>

<main class="mx-auto w-full max-w-2xl flex-1 px-4 py-6 sm:px-6 sm:py-10">
	<!-- Header -->
	<header class="mb-7 flex flex-wrap items-baseline justify-between gap-3 border-b-2 border-[#1a1917] pb-3">
		<h1 class="font-hand text-3xl tracking-tight sm:text-4xl">games.jakob-r.de</h1>

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

		<!-- Games -->
		{#each GAMES as game (game.slug)}
			<ScribblyBox seed={game.boxSeed} class="bg-[#faf8f4] p-4 sm:p-6">
				<div class="flex items-start gap-3 sm:gap-4">
					<a
						href={gamePath(game.slug)}
						class="shrink-0 transition-transform duration-150 hover:-rotate-2 hover:scale-105"
						aria-label="{game.title} details"
					>
						<GameLogo slug={game.slug} class="h-14 w-14 sm:h-16 sm:w-16" />
					</a>
					<div class="min-w-0 flex-1">
						<div class="flex items-center justify-between gap-2">
							<a href={gamePath(game.slug)} class="group min-w-0">
								<h2 class="font-hand text-2xl group-hover:underline group-hover:decoration-[#1a1917]/40 group-hover:underline-offset-4">
									{game.title}
								</h2>
							</a>
							<span
								title={game.playersAria}
								aria-label={game.playersAria}
								class="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-[#6e6a63]"
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
								<span class="font-mono-num">{game.playersLabel}</span>
							</span>
						</div>

						<p class="mt-1.5 text-sm text-[#6e6a63]">
							{game.tagline}
						</p>

						<div class="mt-4 flex flex-wrap items-center gap-2">
							<ScribblyButton
								onclick={() => createRoom(game)}
								disabled={creatingSlug === game.slug}
								variant="primary"
								accentColor={profile.primaryColor}
								class="w-full sm:w-auto"
							>
								{creatingSlug === game.slug ? 'Creating Room…' : game.createLabel}
							</ScribblyButton>
							<a
								href={gamePath(game.slug)}
								class="inline-flex w-full items-center justify-center rounded-md border-[1.8px] border-[#1a1917] bg-[#faf8f4] px-3.5 py-2 text-sm font-medium shadow-[2px_2px_0px_#1a1917] transition hover:bg-[#f2eee6] sm:w-auto"
							>
								About →
							</a>
						</div>
					</div>
				</div>
			</ScribblyBox>
		{/each}

		<!-- Recently Played & Resume -->
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
							<div class="flex min-w-0 items-start gap-2.5">
								<a href={gamePath(item.game_slug as GameSlug)} class="mt-0.5 shrink-0">
									<GameLogo
										slug={item.game_slug as GameSlug}
										class="h-8 w-8"
										title={formatGameTitle(item.game_slug)}
									/>
								</a>
								<div class="min-w-0">
									<div class="flex flex-wrap items-center gap-2">
										<a
											href={gamePath(item.game_slug as GameSlug)}
											class="font-hand text-sm font-bold hover:underline hover:decoration-[#1a1917]/40 hover:underline-offset-2"
										>
											{formatGameTitle(item.game_slug)}
										</a>
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
										Score: {item.score} • {item.player_count} player{item.player_count === 1
											? ''
											: 's'}
										{#if item.updated_at}
											• {formatRelativeTime(item.updated_at)}
										{/if}
									</div>
								</div>
							</div>

							<div class="flex shrink-0 items-center gap-2">
								<a
									href="/{item.game_slug}/{item.room_id}"
									class="inline-flex items-center rounded border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-1.5 text-xs font-semibold shadow-[1.5px_1.5px_0px_#1a1917] transition hover:bg-[#f2eee6]"
								>
									{item.status === 'finished' ? 'View' : 'Resume →'}
								</a>
								{#if item.host_player_id === profile.playerId}
									<button
										type="button"
										onclick={() => (roomPendingDelete = item.room_id)}
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
								{:else}
									<button
										type="button"
										onclick={() => leaveRoom(item.room_id)}
										disabled={leavingRoomId === item.room_id}
										title="Leave this game"
										aria-label="Leave room #{item.room_id}"
										class="inline-flex cursor-pointer items-center justify-center rounded border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-2 py-1.5 text-xs font-medium text-[#6e6a63] shadow-[1.5px_1.5px_0px_#1a1917] transition hover:border-[#dc2626] hover:bg-[#fef2f2] hover:text-[#dc2626] disabled:cursor-not-allowed disabled:opacity-50"
									>
										Leave
									</button>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		</ScribblyBox>

		<!-- Personal Stats -->
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

	<footer class="mt-10 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 border-t border-[#1a1917]/15 pt-6 text-sm text-[#6e6a63]">
		<span>Source available under PolyForm Noncommercial · hosted in Europe (Germany)</span>
		<span aria-hidden="true">·</span>
		<a
			href="https://github.com/jakob-r/games.jakob-r.de"
			class="inline-flex items-center gap-1 font-medium text-[#1a1917] underline decoration-[#1a1917]/30 underline-offset-4 transition hover:decoration-[#1a1917]"
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
				<path d="M16 18l6-6-6-6" />
				<path d="M8 6l-6 6 6 6" />
			</svg>
			Source on GitHub
		</a>
		<span aria-hidden="true">·</span>
		<a
			href="https://github.com/jakob-r/games.jakob-r.de/blob/main/LICENSE"
			class="font-medium text-[#1a1917] underline decoration-[#1a1917]/30 underline-offset-4 transition hover:decoration-[#1a1917]"
		>
			License
		</a>
	</footer>
</main>
