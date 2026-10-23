<script lang="ts">
	import { page } from '$app/state';
	import SudokuGame from '$lib/games/sudoku/SudokuGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
</script>

<svelte:head>
	<title>Sudoku #{roomId} • games.jakob-r.de</title>
</svelte:head>

{#key roomId}
	<SudokuGame {roomId} />
{/key}
