<script lang="ts">
	import { getGame } from '#lib/games/catalog.ts';
	import GameHub from '#lib/games/GameHub.svelte';

	const game = getGame('sudoku')!;
</script>

<GameHub {game} />
