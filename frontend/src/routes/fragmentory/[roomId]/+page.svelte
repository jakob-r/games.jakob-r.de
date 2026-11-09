<script lang="ts">
	import { page } from '$app/state';
	import { roomDocumentTitle } from '#lib/core/notifications.svelte.ts';
	import FragmentoryGame from '#lib/games/fragmentory/FragmentoryGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
	let title = $derived(roomDocumentTitle.text ?? `Fragmentory #${roomId} • games.jakob-r.de`);
</script>

<svelte:head>
	<title>{title}</title>
</svelte:head>

{#key roomId}
	<FragmentoryGame {roomId} />
{/key}
