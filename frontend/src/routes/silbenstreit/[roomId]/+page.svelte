<script lang="ts">
	import { page } from '$app/state';
	import { roomDocumentTitle } from '$lib/core/notifications.svelte';
	import SilbenstreitGame from '$lib/games/silbenstreit/SilbenstreitGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
	let title = $derived(roomDocumentTitle.text ?? `Silbenstreit #${roomId} • games.jakob-r.de`);
</script>

<svelte:head>
	<title>{title}</title>
</svelte:head>

{#key roomId}
	<SilbenstreitGame {roomId} />
{/key}
