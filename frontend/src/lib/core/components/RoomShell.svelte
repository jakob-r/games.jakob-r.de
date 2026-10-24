<script lang="ts">
	import type { Snippet } from 'svelte';
	import { goto } from '$app/navigation';
	import { profile } from '$lib/core/profile.svelte';
	import type { PlayerInfo, RoomSocketClient } from '$lib/core/ws.svelte';
	import Lobby from './Lobby.svelte';
	import NamePromptModal from './NamePromptModal.svelte';
	import ProfileBadge from './ProfileBadge.svelte';
	import ScribblyBox from './ScribblyBox.svelte';

	let {
		client,
		roomId,
		title,
		subtitleItems = [],
		maxWidthClass = 'max-w-3xl',
		startLabel = 'Start Game →',
		configSlot,
		children
	}: {
		client: RoomSocketClient;
		roomId: string;
		title: string;
		subtitleItems?: string[];
		maxWidthClass?: string;
		startLabel?: string;
		configSlot?: Snippet;
		children: Snippet;
	} = $props();

	let deletingRoom = $state<boolean>(false);
	let leavingRoom = $state<boolean>(false);

	let room = $derived(client.room);
	let players = $derived<PlayerInfo[]>(room?.players ?? []);
	let isHost = $derived(room?.host_player_id === profile.playerId);

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
</script>

<NamePromptModal onConfirm={(name, color) => client.syncProfile(profile.playerId, name, color)} />

<div class="mx-auto flex w-full {maxWidthClass} flex-1 flex-col px-3 py-3 sm:px-6 sm:py-5">
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
				<h1 class="font-hand text-lg leading-none sm:text-xl">{title}</h1>
				<div class="font-mono-num flex flex-wrap items-center gap-2 text-[11px] text-[#6e6a63]">
					<span>#{roomId}</span>
					{#each subtitleItems as item, idx (idx)}
						<span>•</span>
						<span>{item}</span>
					{/each}
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
			{startLabel}
			onToggleReady={(r) => client.setReady(r)}
			onStartGame={() => client.startGame()}
			onLeaveRoom={isHost ? undefined : leaveRoom}
			onRemovePlayer={(id) => client.removePlayer(id)}
			{configSlot}
		/>
	{:else}
		{@render children()}
	{/if}
</div>
