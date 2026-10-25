<script lang="ts">
	import type { GameSlug } from './catalog';

	let {
		slug,
		class: className = 'h-12 w-12',
		title: titleAttr = undefined
	}: {
		slug: GameSlug;
		class?: string;
		title?: string;
	} = $props();
</script>

{#if slug === 'sudoku'}
	<svg
		class={className}
		viewBox="0 0 48 48"
		fill="none"
		role="img"
		aria-hidden={titleAttr ? undefined : true}
		aria-label={titleAttr}
	>
		{#if titleAttr}<title>{titleAttr}</title>{/if}
		<!-- Slightly wonky 3×3 grid with a few filled cells -->
		<rect
			x="5.5"
			y="5.5"
			width="37"
			height="37"
			rx="3"
			stroke="#1a1917"
			stroke-width="1.7"
			stroke-linejoin="round"
			filter="url(#scribble-filter)"
		/>
		<path
			d="M17.2 6.2v35.5M30.8 6.5v35M6.2 17.3h35.5M6.5 30.7h35"
			stroke="#1a1917"
			stroke-width="1.45"
			stroke-linecap="round"
			filter="url(#scribble-filter)"
		/>
		<text
			x="11.2"
			y="14.8"
			font-family="Architects Daughter, cursive"
			font-size="9"
			fill="#1a1917"
		>5</text>
		<text
			x="23.6"
			y="28.2"
			font-family="Architects Daughter, cursive"
			font-size="9"
			fill="#1a1917"
		>9</text>
		<text
			x="35.2"
			y="41.2"
			font-family="Architects Daughter, cursive"
			font-size="9"
			fill="#1a1917"
		>2</text>
	</svg>
{:else if slug === 'kaesekaestchen'}
	<svg
		class={className}
		viewBox="0 0 48 48"
		fill="none"
		role="img"
		aria-hidden={titleAttr ? undefined : true}
		aria-label={titleAttr}
	>
		{#if titleAttr}<title>{titleAttr}</title>{/if}
		<!-- Dots & one claimed square with hatched fill -->
		<circle cx="12" cy="12" r="2.2" fill="#1a1917" />
		<circle cx="24" cy="12" r="2.2" fill="#1a1917" />
		<circle cx="36" cy="12" r="2.2" fill="#1a1917" />
		<circle cx="12" cy="24" r="2.2" fill="#1a1917" />
		<circle cx="24" cy="24" r="2.2" fill="#1a1917" />
		<circle cx="36" cy="24" r="2.2" fill="#1a1917" />
		<circle cx="12" cy="36" r="2.2" fill="#1a1917" />
		<circle cx="24" cy="36" r="2.2" fill="#1a1917" />
		<circle cx="36" cy="36" r="2.2" fill="#1a1917" />
		<path
			d="M12 12h12M24 12v12M24 24h-12M12 24v-12"
			stroke="#1a1917"
			stroke-width="1.8"
			stroke-linecap="round"
			filter="url(#scribble-filter)"
		/>
		<path
			d="M14.5 15.5l7 7M21.5 15.5l-7 7"
			stroke="#1a1917"
			stroke-width="1.2"
			stroke-linecap="round"
			opacity="0.55"
		/>
		<path
			d="M24 24h12M36 12v12"
			stroke="#1a1917"
			stroke-width="1.55"
			stroke-linecap="round"
			stroke-dasharray="2.5 2.2"
			opacity="0.55"
			filter="url(#scribble-filter)"
		/>
	</svg>
{:else if slug === 'minesweeper'}
	<svg
		class={className}
		viewBox="0 0 48 48"
		fill="none"
		role="img"
		aria-hidden={titleAttr ? undefined : true}
		aria-label={titleAttr}
	>
		{#if titleAttr}<title>{titleAttr}</title>{/if}
		<!-- Soft mine body + tiny flag -->
		<circle
			cx="22"
			cy="26"
			r="11.5"
			stroke="#1a1917"
			stroke-width="1.7"
			fill="#faf8f4"
			filter="url(#scribble-filter)"
		/>
		<path
			d="M22 12.5v4.2M22 35.3v4.2M10.5 26h4.2M29.3 26h4.2M13.8 17.8l3 3M27.2 31.2l3 3M13.8 34.2l3-3M27.2 20.8l3-3"
			stroke="#1a1917"
			stroke-width="1.55"
			stroke-linecap="round"
		/>
		<circle cx="19.5" cy="23.5" r="1.6" fill="#1a1917" />
		<circle cx="25.2" cy="27.8" r="1.2" fill="#1a1917" opacity="0.7" />
		<!-- Flag -->
		<path
			d="M34 10v22"
			stroke="#1a1917"
			stroke-width="1.6"
			stroke-linecap="round"
		/>
		<path
			d="M34 11.2l11 5.2-11 5.2z"
			stroke="#1a1917"
			stroke-width="1.45"
			stroke-linejoin="round"
			fill="#1a1917"
			fill-opacity="0.12"
			filter="url(#scribble-filter)"
		/>
	</svg>
{:else}
	<svg
		class={className}
		viewBox="0 0 48 48"
		fill="none"
		role="img"
		aria-hidden={titleAttr ? undefined : true}
		aria-label={titleAttr}
	>
		{#if titleAttr}<title>{titleAttr}</title>{/if}
		<!-- Letter tiles with a claimed accent -->
		<rect
			x="5"
			y="8"
			width="17"
			height="17"
			rx="2.5"
			stroke="#1a1917"
			stroke-width="1.65"
			fill="#faf8f4"
			filter="url(#scribble-filter)"
		/>
		<rect
			x="26"
			y="8"
			width="17"
			height="17"
			rx="2.5"
			stroke="#1a1917"
			stroke-width="1.65"
			fill="#1a1917"
			fill-opacity="0.08"
			filter="url(#scribble-filter)"
		/>
		<rect
			x="5"
			y="28"
			width="17"
			height="17"
			rx="2.5"
			stroke="#1a1917"
			stroke-width="1.65"
			fill="#faf8f4"
			filter="url(#scribble-filter)"
		/>
		<rect
			x="26"
			y="28"
			width="17"
			height="17"
			rx="2.5"
			stroke="#1a1917"
			stroke-width="1.65"
			stroke-dasharray="3 2.2"
			fill="#faf8f4"
			opacity="0.7"
		/>
		<text
			x="9.5"
			y="20.5"
			font-family="Architects Daughter, cursive"
			font-size="12"
			fill="#1a1917"
		>S</text>
		<text
			x="30.5"
			y="20.5"
			font-family="Architects Daughter, cursive"
			font-size="12"
			fill="#1a1917"
		>I</text>
		<text
			x="9.8"
			y="40.5"
			font-family="Architects Daughter, cursive"
			font-size="12"
			fill="#1a1917"
		>L</text>
		<!-- Small rarity badge on dashed tile -->
		<circle cx="39.5" cy="32.5" r="4.2" stroke="#1a1917" stroke-width="1.2" fill="#faf8f4" />
		<text
			x="37.4"
			y="34.2"
			font-family="JetBrains Mono, monospace"
			font-size="6"
			fill="#1a1917"
		>8</text>
	</svg>
{/if}
