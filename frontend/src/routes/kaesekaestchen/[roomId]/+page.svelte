<script lang="ts">
	import { page } from '$app/state';
	import { roomDocumentTitle } from '$lib/core/notifications.svelte';
	import KaesekaestchenGame from '$lib/games/kaesekaestchen/KaesekaestchenGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
	let title = $derived(roomDocumentTitle.text ?? `Käsekästchen #${roomId} • games.jakob-r.de`);
</script>

<svelte:head>
	<title>{title}</title>
</svelte:head>

{#key roomId}
	<KaesekaestchenGame {roomId} />
{/key}
