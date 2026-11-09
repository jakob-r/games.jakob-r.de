<script lang="ts">
	import { page } from '$app/state';
	import { roomDocumentTitle } from '#lib/core/notifications.svelte.ts';
	import SpellsprawlGame from '#lib/games/spellsprawl/SpellsprawlGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
	let title = $derived(roomDocumentTitle.text ?? `Spellsprawl #${roomId} • games.jakob-r.de`);
</script>

<svelte:head>
	<title>{title}</title>
</svelte:head>

{#key roomId}
	<SpellsprawlGame {roomId} />
{/key}
