<script lang="ts">
	import { page } from '$app/state';
	import { roomDocumentTitle } from '$lib/core/notifications.svelte';
	import EmojiCharadesGame from '$lib/games/emoji-charades/EmojiCharadesGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
	let title = $derived(roomDocumentTitle.text ?? `Emoji Charades #${roomId} • games.jakob-r.de`);
</script>

<svelte:head>
	<title>{title}</title>
</svelte:head>

{#key roomId}
	<EmojiCharadesGame {roomId} />
{/key}
