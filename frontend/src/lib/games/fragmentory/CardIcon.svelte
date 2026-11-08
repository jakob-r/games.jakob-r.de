<script lang="ts">
	import { CARD_SHAPES, type CardType } from './board';

	let { type, rot = 0, size = 24 }: { type: CardType; rot?: number; size?: number } = $props();
</script>

<svg viewBox="-0.05 -0.05 1.1 1.1" width={size} height={size} class="inline-block shrink-0" aria-hidden="true">
	<rect x="0" y="0" width="1" height="1" rx="0.05" fill="#fff" stroke="#1a1917" stroke-width="0.05" />
	<g transform="rotate({rot * 90} .5 .5)">
		<path d={CARD_SHAPES[type].lines} stroke="#1a1917" stroke-width="0.09" stroke-linecap="round" fill="none" />
		{#if type === 'end'}
			<circle cx=".5" cy=".45" r=".07" fill="#1a1917" />
		{/if}
	</g>
</svg>
