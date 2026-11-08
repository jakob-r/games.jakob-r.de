<script lang="ts">
	import { page } from '$app/state';
	import { roomDocumentTitle } from '$lib/core/notifications.svelte';
	import NorthSouthSortGame from '$lib/games/north-south-sort/NorthSouthSortGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
	let title = $derived(roomDocumentTitle.text ?? `North South Sort #${roomId} • games.jakob-r.de`);
</script>

<svelte:head>
	<title>{title}</title>
</svelte:head>

{#key roomId}
	<NorthSouthSortGame {roomId} />
{/key}
