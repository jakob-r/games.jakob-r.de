<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import DeleteRoomModal from '#lib/core/components/DeleteRoomModal.svelte';
	import ProfileBadge from '#lib/core/components/ProfileBadge.svelte';
	import SeoHead from '#lib/core/components/SeoHead.svelte';
	import ScribblyBox from '#lib/core/components/ScribblyBox.svelte';
	import ScribblyButton from '#lib/core/components/ScribblyButton.svelte';
	import { auth } from '#lib/core/auth.svelte.ts';
	import { profile } from '#lib/core/profile.svelte.ts';
	import {
		GAMES,
		SITE_ORIGIN,
		formatGameTitle,
		gamePath,
		roomPath,
		type GameInfo,
		type GameSlug
	} from '#lib/games/catalog.ts';
	import GameLogo from '#lib/games/GameLogo.svelte';
	import InstallAppPrompt from '#lib/core/components/InstallAppPrompt.svelte';
	import { friends } from '#lib/core/friends.svelte.ts';

	interface RecentRoom {
		room_id: string;
		game_slug: string;
		status: 'lobby' | 'playing' | 'finished';
		host_player_id: string;
		config: {
			difficulty?: string;
			solo?: boolean;
			scoring_enabled?: boolean;
			width?: number;
			height?: number;
			size?: number;
			language?: string;
			mode?: string;
			end_condition?: string;
			end_target?: number;
			continent?: string;
		};
		score: number;
		player_count: number;
		updated_at: string | null;
	}

	interface PlayerStatsSummary {
		games_completed: number;
	}

	interface ServerTotals {
		rounds_played: number;
		points_scored: number;
	}

	interface GameStats {
		game_slug: string;
		games_played: number;
		best_score_single: number | null;
		best_score_multi: number | null;
	}

	let creatingSlug = $state<GameSlug | null>(null);
	let deletingRoomId = $state<string | null>(null);
	let roomPendingDelete = $state<string | null>(null);
	let leavingRoomId = $state<string | null>(null);
	let recentRooms = $state<RecentRoom[]>([]);
	let inviteCount = $state(0);

	$effect(() => {
		if (!auth.user) {
			inviteCount = 0;
			return;
		}
		void friends.inbox().then((res) => (inviteCount = res.data?.invites.length ?? 0));
	});
	let stats = $state<PlayerStatsSummary | null>(null);
	let statsByGame = $state<GameStats[]>([]);
	let serverTotals = $state<ServerTotals | null>(null);
	// Most played first, then catalog title.
	const sortedStatsByGame = $derived(
		[...statsByGame]
			.filter((g) => g.games_played > 0)
			.sort(
				(a, b) =>
					b.games_played - a.games_played ||
					formatGameTitle(a.game_slug).localeCompare(formatGameTitle(b.game_slug))
			)
	);
	let joinCode = $state<string>('');
	let joinError = $state<string | null>(null);
	let playCounts = $state<Record<string, number>>({});
	// Most played first; stable sort keeps catalog order for ties and before counts load.
	const sortedGames = $derived(
		[...GAMES].sort((a, b) => (playCounts[b.slug] ?? 0) - (playCounts[a.slug] ?? 0))
	);

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
				statsByGame = data.by_game ?? [];
				serverTotals = data.server ?? null;
			}
		} catch (e) {
			console.error('Failed to load player dashboard:', e);
		}
	}

	async function loadPlayCounts() {
		try {
			const res = await fetch('/api/games');
			if (!res.ok) return;
			const games: { slug: string; play_count?: number }[] = await res.json();
			playCounts = Object.fromEntries(games.map((g) => [g.slug, g.play_count ?? 0]));
		} catch (e) {
			console.error('Failed to load play counts:', e);
		}
	}

	onMount(() => {
		profile.init();
		loadPlayerDashboard();
		loadPlayCounts();
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

	/** Accepts "abc123", "#abc123" or a pasted room link like https://…/sudoku/abc123?x#y. */
	function parseRoomCode(input: string): string {
		let text = input.trim();
		if (text.includes('/')) {
			try {
				text = new URL(text, window.location.origin).pathname;
			} catch {
				text = text.split(/[?#]/)[0];
			}
			text = text.split('/').filter(Boolean).pop() ?? '';
		}
		return text.toLowerCase().replace(/^#/, '');
	}

	async function handleJoinByCode(e: SubmitEvent) {
		e.preventDefault();
		joinError = null;
		const code = parseRoomCode(joinCode);
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
		if (item.game_slug === 'sudoku-zero') {
			return item.config?.solo ? 'Solo' : '2 players';
		}
		if (item.game_slug === 'silbenstreit') {
			const sz = item.config?.size ?? 5;
			const lang = (item.config?.language ?? 'de').toUpperCase();
			return `${sz}×${sz} • ${lang}`;
		}
		if (item.game_slug === 'spellsprawl') {
			const lang = (item.config?.language ?? 'de').toUpperCase();
			const target = item.config?.end_target ?? 50;
			const end =
				item.config?.end_condition === 'points'
					? `${target} pts`
					: item.config?.end_condition === 'area'
						? `grid ${target}`
						: `${target} words`;
			return `${lang} • ${end}`;
		}
		if (item.game_slug === 'north-south-sort') {
			const continent = String(item.config?.continent ?? 'world').replace('_', ' ');
			const target = item.config?.end_target ?? 10;
			const end =
				item.config?.end_condition === 'points'
					? `${target} pts`
					: item.config?.end_condition === 'failed_round'
						? 'until all miss'
						: `${target} rounds`;
			return `${continent} • ${item.config?.difficulty ?? 'medium'} • ${end}`;
		}
		if (item.game_slug === 'fragmentory') {
			return '42 cards';
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
				placeholder="Room ID or link…"
				aria-label="Room ID or link"
				maxlength="300"
				class="font-mono-num w-32 rounded-md border-[1.6px] border-[#1a1917] bg-white px-2.5 py-1.5 text-xs focus:outline-none"
			/>
			<ScribblyButton type="submit">Join Room</ScribblyButton>
			{#if auth.user}
				<ScribblyButton
					onclick={() => goto('/friends')}
					title={inviteCount ? `Friends — ${inviteCount} open invite${inviteCount === 1 ? '' : 's'}` : "Friends' lobbies and invites"}
					class="relative !px-2.5"
				>
					<span class="sr-only">Friends</span>
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<circle cx="9" cy="8" r="3.5" />
						<path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6" />
						<circle cx="17" cy="9" r="2.5" />
						<path d="M17 14c2.6 0 4.5 1.9 4.5 4.5" />
					</svg>
					{#if inviteCount}
						<span class="font-mono-num absolute -top-1.5 -right-1.5 min-w-4 rounded-full border border-[#1a1917] bg-[#fef3c7] px-1 text-[10px] leading-4 font-bold">{inviteCount}</span>
					{/if}
				</ScribblyButton>
			{/if}
			<ScribblyButton
				onclick={() => goto(auth.user ? '/account' : '/login')}
				title={auth.user ? 'Account settings' : 'Sign in or create account'}
				class="!px-2.5"
			>
				<span class="sr-only">{auth.user ? 'Account settings' : 'Sign in'}</span>
				<svg width="18" height="18" viewBox="0 0 24 24" fill={auth.user ? profile.primaryColor : 'none'} stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
					<circle cx="12" cy="8" r="4" />
					<path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" />
				</svg>
			</ScribblyButton>
		</form>
	</header>

	{#if joinError}
		<div class="mb-4 rounded border border-[#dc2626] bg-[#faf8f4] px-3 py-2 text-xs font-medium text-[#dc2626]">
			{joinError}
		</div>
	{/if}

	<div class="space-y-6">
		<!-- Player identity & color (signed-in users edit this under Account) -->
		{#if !auth.user}
			<ScribblyBox seed={7} class="bg-[#faf8f4] p-4 sm:p-6">
				<ProfileBadge />
			</ScribblyBox>
		{/if}

		<!-- Recently Played & Resume -->
		{#if recentRooms.length > 0}
			<ScribblyBox seed={31} class="bg-[#faf8f4] p-4 sm:p-6">
				<div class="mb-3 flex items-center justify-between">
					<h2 class="font-hand text-xl">Recent Games</h2>
				</div>

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
			</ScribblyBox>
		{/if}

		<!-- Games -->
		{#each sortedGames as game (game.slug)}
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

		<!-- Personal Stats -->
		<ScribblyBox seed={43} class="bg-[#faf8f4] p-4 sm:p-6">
			<h2 class="font-hand mb-3 text-xl">Your stats</h2>
			<p class="text-sm">
				Completed games: <span class="font-mono-num font-bold">{stats?.games_completed ?? 0}</span>
			</p>
			{#if sortedStatsByGame.length > 0}
				<ul class="mt-3 space-y-2 text-sm">
					{#each sortedStatsByGame as g (g.game_slug)}
						<li>
							<span class="font-medium">{formatGameTitle(g.game_slug)}</span>
							<ul class="ml-5 list-disc text-[#6e6a63] marker:text-[#1a1917]/40">
								<li>
									Played: <span class="font-mono-num text-[#1a1917]">{g.games_played}</span>
								</li>
								<li>
									Best single player:
									<span class="font-mono-num text-[#1a1917]">{g.best_score_single ?? '–'}</span>
								</li>
								<li>
									Best multiplayer:
									<span class="font-mono-num text-[#1a1917]">{g.best_score_multi ?? '–'}</span>
								</li>
							</ul>
						</li>
					{/each}
				</ul>
			{/if}
			{#if serverTotals}
				<div class="mt-5 border-t border-[#1a1917]/15 pt-4">
					<h3 class="font-hand mb-2 text-lg">Server stats</h3>
					<ul class="ml-5 list-disc space-y-0.5 text-sm text-[#6e6a63] marker:text-[#1a1917]/40">
						<li>
							<span class="font-mono-num text-[#1a1917]"
								>{serverTotals.rounds_played.toLocaleString('en')}</span
							> rounds played
						</li>
						<li>
							<span class="font-mono-num text-[#1a1917]"
								>{serverTotals.points_scored.toLocaleString('en')}</span
							> points scored
						</li>
					</ul>
				</div>
			{/if}
		</ScribblyBox>
	</div>

	<InstallAppPrompt />

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
		<span aria-hidden="true">·</span>
		<a
			href="https://www.jakob-r.de/coding/"
			class="font-medium text-[#1a1917] underline decoration-[#1a1917]/30 underline-offset-4 transition hover:decoration-[#1a1917]"
		>by jakob-r</a>
		<span aria-hidden="true">·</span>
		<a
			href="https://www.jakob-r.de/legal-notice/"
			class="font-medium text-[#1a1917] underline decoration-[#1a1917]/30 underline-offset-4 transition hover:decoration-[#1a1917]"
		>Legal notice</a>
		<span aria-hidden="true">·</span>
		<a
			href="/privacy"
			class="font-medium text-[#1a1917] underline decoration-[#1a1917]/30 underline-offset-4 transition hover:decoration-[#1a1917]"
		>Privacy</a>
	</footer>
</main>
