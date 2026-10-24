<script lang="ts">
	import { page } from '$app/state';
	import SilbenstreitGame from '$lib/games/silbenstreit/SilbenstreitGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
</script>

<svelte:head>
	<title>Silbenstreit #{roomId} • games.jakob-r.de</title>
</svelte:head>

{#key roomId}
	<SilbenstreitGame {roomId} />
{/key}
