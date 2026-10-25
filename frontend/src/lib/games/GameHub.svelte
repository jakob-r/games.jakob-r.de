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
		SITE_ORIGIN,
		type GameInfo,
		type GameSlug,
		roomPath
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
		};
		score: number;
		player_count: number;
		updated_at: string | null;
	}

	let { game }: { game: GameInfo } = $props();

	let creating = $state(false);
	let deletingRoomId = $state<string | null>(null);
	let roomPendingDelete = $state<string | null>(null);
	let leavingRoomId = $state<string | null>(null);
	let openSessions = $state<RecentRoom[]>([]);
	let createError = $state<string | null>(null);

	const jsonLd = $derived({
		'@type': 'WebApplication',
		'@id': `${SITE_ORIGIN}/${game.slug}#game`,
		name: game.title,
		url: `${SITE_ORIGIN}/${game.slug}`,
		description: game.description,
		applicationCategory: 'GameApplication',
		operatingSystem: 'Any (web browser)',
		browserRequirements: 'Requires JavaScript',
		isAccessibleForFree: true,
		offers: { '@type': 'Offer', price: '0', priceCurrency: 'EUR' },
		isPartOf: { '@id': `${SITE_ORIGIN}/#app` },
		featureList: [
			`Players: ${game.playersLabel}`,
			'Real-time multiplayer rooms',
			'No ads, no tracking',
			'Hosted in Europe (Germany)'
		]
	});

	async function loadOpenSessions() {
		if (!profile.playerId) return;
		try {
			const res = await fetch(
				`/api/players/${encodeURIComponent(profile.playerId)}/recent`
			);
			if (!res.ok) return;
			const rooms: RecentRoom[] = await res.json();
			openSessions = rooms.filter(
				(r) => r.game_slug === game.slug && r.status !== 'finished'
			);
		} catch (e) {
			console.error('Failed to load open sessions:', e);
		}
	}

	onMount(() => {
		profile.init();
		loadOpenSessions();
	});

	async function createRoom() {
		if (creating) return;
		creating = true;
		createError = null;
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
				await goto(roomPath(game.slug as GameSlug, room.room_id));
			} else {
				createError = 'Could not create room. Try again.';
			}
		} catch (e) {
			console.error('Failed to create room:', e);
			createError = 'Could not create room. Try again.';
		} finally {
			creating = false;
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
				openSessions = openSessions.filter((r) => r.room_id !== roomId);
				roomPendingDelete = null;
			}
		} catch (e) {
			console.error('Failed to delete room:', e);
		} finally {
			deletingRoomId = null;
		}
	}

	async function leaveRoom(roomId: string) {
		if (!profile.playerId || leavingRoomId) return;
		const target = openSessions.find((r) => r.room_id === roomId);
		if (target?.host_player_id === profile.playerId) return;
		leavingRoomId = roomId;
		try {
			const res = await fetch(
				`/api/rooms/${encodeURIComponent(roomId)}/players/${encodeURIComponent(profile.playerId)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				openSessions = openSessions.filter((r) => r.room_id !== roomId);
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
	title={game.title}
	description={game.tagline}
	path="/{game.slug}"
	jsonLd={jsonLd}
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
	<nav class="mb-5 text-sm text-[#6e6a63]">
		<a
			href="/"
			class="font-medium text-[#1a1917] underline decoration-[#1a1917]/30 underline-offset-4 transition hover:decoration-[#1a1917]"
		>games.jakob-r.de</a>
		<span aria-hidden="true" class="mx-1.5">/</span>
		<span class="text-[#1a1917]">{game.title}</span>
	</nav>

	<header class="mb-7 flex flex-wrap items-start gap-4 border-b-2 border-[#1a1917] pb-4">
		<GameLogo slug={game.slug as GameSlug} class="h-16 w-16 shrink-0 sm:h-20 sm:w-20" title={game.title} />
		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-center gap-2">
				<h1 class="font-hand text-3xl tracking-tight sm:text-4xl">{game.title}</h1>
				<span
					title={game.playersAria}
					aria-label={game.playersAria}
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
					<span class="font-mono-num">{game.playersLabel}</span>
				</span>
			</div>
			<p class="mt-2 max-w-prose text-sm leading-relaxed text-[#6e6a63]">
				{game.description}
			</p>
		</div>
	</header>

	<div class="space-y-6">
		<ScribblyBox seed={7} class="bg-[#faf8f4] p-4 sm:p-6">
			<ProfileBadge />
		</ScribblyBox>

		<ScribblyBox seed={game.boxSeed} class="bg-[#faf8f4] p-4 sm:p-6">
			<h2 class="font-hand text-xl">Play</h2>
			<p class="mt-1.5 text-sm text-[#6e6a63]">
				Create a room and share the link so friends can join.
			</p>
			{#if createError}
				<p class="mt-2 text-xs font-medium text-[#dc2626]">{createError}</p>
			{/if}
			<div class="mt-4">
				<ScribblyButton
					onclick={createRoom}
					disabled={creating}
					variant="primary"
					accentColor={profile.primaryColor}
					class="w-full sm:w-auto"
				>
					{creating ? 'Creating Room…' : game.createLabel}
				</ScribblyButton>
			</div>
		</ScribblyBox>

		<ScribblyBox seed={game.boxSeed + 8} class="bg-[#faf8f4] p-4 sm:p-6">
			<div class="mb-3 flex items-center justify-between">
				<h2 class="font-hand text-xl">Your open sessions</h2>
			</div>

			{#if openSessions.length === 0}
				<p class="py-3 text-sm text-[#6e6a63]">
					No open {game.title} rooms yet. Start one above.
				</p>
			{:else}
				<ul class="divide-y divide-[#1a1917]/10">
					{#each openSessions as item (item.room_id)}
						<li class="flex items-center justify-between gap-3 py-2.5">
							<div>
								<div class="flex flex-wrap items-center gap-2">
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

							<div class="flex items-center gap-2">
								<a
									href={roomPath(game.slug as GameSlug, item.room_id)}
									class="inline-flex items-center rounded border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-3 py-1.5 text-xs font-semibold shadow-[1.5px_1.5px_0px_#1a1917] transition hover:bg-[#f2eee6]"
								>
									Resume →
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
	</div>

	<footer class="mt-10 border-t border-[#1a1917]/15 pt-6 text-center text-sm text-[#6e6a63]">
		<a
			href="/"
			class="font-medium text-[#1a1917] underline decoration-[#1a1917]/30 underline-offset-4 transition hover:decoration-[#1a1917]"
		>← All games</a>
	</footer>
</main>
