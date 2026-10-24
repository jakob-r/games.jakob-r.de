<script lang="ts">
	import { page } from '$app/state';
	import MinesweeperGame from '$lib/games/minesweeper/MinesweeperGame.svelte';

	let roomId = $derived(page.params.roomId ?? '');
</script>

<svelte:head>
	<title>Minesweeper #{roomId} • games.jakob-r.de</title>
</svelte:head>

{#key roomId}
	<MinesweeperGame {roomId} />
{/key}
