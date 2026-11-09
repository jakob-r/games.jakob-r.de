<script lang="ts">
	import AuthShell from '$lib/core/components/AuthShell.svelte';
	import ScribblyButton from '$lib/core/components/ScribblyButton.svelte';
	import { auth } from '$lib/core/auth.svelte';
	import { friends, type FriendLobby, type RoomInvite } from '$lib/core/friends.svelte';
	import GameLogo from '$lib/games/GameLogo.svelte';
	import { GAMES, getGame, roomPath, type GameSlug } from '$lib/games/catalog';

	let invites = $state<RoomInvite[] | null>(null);
	let lobbies = $state<FriendLobby[] | null>(null);
	let error = $state('');

	async function load() {
		const [inboxRes, lobbiesRes] = await Promise.all([friends.inbox(), friends.lobbies()]);
		error = inboxRes.error || lobbiesRes.error;
		invites = inboxRes.data?.invites ?? [];
		lobbies = lobbiesRes.data?.lobbies ?? [];
	}

	$effect(() => {
		if (auth.user) void load();
	});

	async function dismiss(roomId: string) {
		const res = await friends.dismissInvite(roomId);
		if (res.ok && invites) invites = invites.filter((i) => i.room_id !== roomId);
		else error = res.error;
	}

	const gameOrder = new Map(GAMES.map((g, i) => [g.slug as string, i]));
	let lobbyGroups = $derived.by(() => {
		const groups = new Map<string, FriendLobby[]>();
		for (const lobby of lobbies ?? []) {
			const group = groups.get(lobby.game_slug) ?? [];
			group.push(lobby);
			groups.set(lobby.game_slug, group);
		}
		return [...groups.entries()].sort(
			([a], [b]) => (gameOrder.get(a) ?? 99) - (gameOrder.get(b) ?? 99)
		);
	});

	function gameTitle(slug: string): string {
		return getGame(slug)?.title ?? slug;
	}
</script>

<AuthShell title="Friends">
	{#if !auth.loaded}
		<p>Loading…</p>
	{:else if !auth.user}
		<p class="text-sm">
			<a href="/login?next=/friends" class="underline">Sign in</a> to add friends, invite them and see
			their open lobbies.
		</p>
	{:else}
		{#if error}
			<p class="text-xs font-medium text-[#dc2626]" role="alert">{error}</p>
		{/if}

		<section class="space-y-2">
			<h2 class="text-sm font-medium">Invites</h2>
			{#if invites === null}
				<p class="text-sm text-[#6e6a63]">Loading…</p>
			{:else if invites.length === 0}
				<p class="text-sm text-[#6e6a63]">No open invites.</p>
			{:else}
				<ul class="divide-y divide-[#1a1917]/10">
					{#each invites as invite (invite.room_id)}
						<li class="flex items-center gap-3 py-2">
							<GameLogo slug={invite.game_slug as GameSlug} class="h-9 w-9 shrink-0" />
							<div class="min-w-0 flex-1 text-sm">
								<p class="truncate">
									<strong style="color: {invite.from.color || '#1a1917'};">{invite.from.label}</strong>
									invites you
								</p>
								<p class="truncate text-xs text-[#6e6a63]">
									{gameTitle(invite.game_slug)} · {invite.status === 'playing'
										? 'game running'
										: 'in the lobby'}
								</p>
							</div>
							<a
								href={roomPath(invite.game_slug as GameSlug, invite.room_id)}
								class="rounded border-[1.5px] border-[#1a1917] bg-[#1a1917] px-2.5 py-1 text-xs font-medium text-[#faf8f4] shadow-[1.5px_1.5px_0px_#1a1917]"
							>
								Join
							</a>
							<button
								type="button"
								class="cursor-pointer text-xs underline"
								onclick={() => dismiss(invite.room_id)}
							>
								Dismiss
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		<section class="space-y-2 border-t border-[#1a1917]/15 pt-4">
			<h2 class="text-sm font-medium">Friends' lobbies</h2>
			<p class="text-xs text-[#6e6a63]">Rooms your friends created that haven't started yet.</p>
			{#if lobbies === null}
				<p class="text-sm text-[#6e6a63]">Loading…</p>
			{:else if lobbies.length === 0}
				<p class="text-sm text-[#6e6a63]">No open lobbies right now.</p>
			{:else}
				{#each lobbyGroups as [slug, group] (slug)}
					<div class="space-y-1">
						<h3 class="flex items-center gap-2 text-xs font-medium tracking-wide text-[#6e6a63] uppercase">
							<GameLogo slug={slug as GameSlug} class="h-6 w-6" />
							{gameTitle(slug)}
						</h3>
						<ul>
							{#each group as lobby (lobby.room_id)}
								<li class="flex items-center gap-2 py-1 pl-8 text-sm">
									<span
										class="h-3 w-3 shrink-0 rounded-full border border-[#1a1917]"
										style="background-color: {lobby.host.color || '#faf8f4'};"
									></span>
									<span class="min-w-0 flex-1 truncate">
										<span class="font-medium">{lobby.host.label}</span>
										<span class="text-xs text-[#6e6a63]">
											· {lobby.players}
											{lobby.players === 1 ? 'player' : 'players'}
										</span>
									</span>
									<a
										href={roomPath(lobby.game_slug as GameSlug, lobby.room_id)}
										class="text-xs font-medium underline"
									>
										{lobby.joined ? 'Open' : 'Join'}
									</a>
								</li>
							{/each}
						</ul>
					</div>
				{/each}
			{/if}
		</section>

		<div class="flex flex-wrap gap-3 border-t border-[#1a1917]/15 pt-4">
			<ScribblyButton onclick={load}>Refresh</ScribblyButton>
			<a href="/account" class="self-center text-sm underline">Manage friends</a>
		</div>
	{/if}
</AuthShell>
