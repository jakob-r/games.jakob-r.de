<script lang="ts">
	import { page } from '$app/state';
	import { roomDocumentTitle } from '#lib/core/notifications.svelte.ts';
	import SudokuZeroGame from '#lib/games/sudoku-zero/SudokuZeroGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
	let title = $derived(roomDocumentTitle.text ?? `Sudoku Zero #${roomId} • games.jakob-r.de`);
</script>

<svelte:head>
	<title>{title}</title>
</svelte:head>

{#key roomId}
	<SudokuZeroGame {roomId} />
{/key}
