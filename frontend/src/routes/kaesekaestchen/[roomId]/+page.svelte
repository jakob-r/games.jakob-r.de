<script lang="ts">
	import { page } from '$app/state';
	import KaesekaestchenGame from '$lib/games/kaesekaestchen/KaesekaestchenGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
</script>

<svelte:head>
	<title>Käsekästchen #{roomId} • games.jakob-r.de</title>
</svelte:head>

{#key roomId}
	<KaesekaestchenGame {roomId} />
{/key}
