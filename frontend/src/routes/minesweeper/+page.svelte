<script lang="ts">
	import { getGame } from '$lib/games/catalog';
	import GameHub from '$lib/games/GameHub.svelte';

	const game = getGame('minesweeper')!;
</script>

<GameHub {game} />
