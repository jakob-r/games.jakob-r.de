<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		class: className = '',
		stroke = '#1a1917',
		strokeWidth = 1.8,
		fill = 'none',
		seed = 1,
		children
	}: {
		class?: string;
		stroke?: string;
		strokeWidth?: number;
		fill?: string;
		seed?: number;
		children: Snippet;
	} = $props();

	let w = $state(200);
	let h = $state(100);

	// Generate deterministic slight wobble offsets from seed so each box looks hand-sketched
	let pathData = $derived.by(() => {
		const pad = 3;
		const x0 = pad;
		const y0 = pad;
		const x1 = Math.max(pad + 10, w - pad);
		const y1 = Math.max(pad + 10, h - pad);
		const s = ((seed * 9301 + 49297) % 233280) / 233280;
		const j1 = (s - 0.5) * 2.2;
		const j2 = ((s * 7) % 1 - 0.5) * 2.2;

		// Two slightly offset passes for a hand-drawn ink rectangle
		return `M ${x0} ${y0 + j1} Q ${w / 2} ${y0 - j2}, ${x1} ${y0}
		        Q ${x1 + j1} ${h / 2}, ${x1} ${y1}
		        Q ${w / 2} ${y1 + j2}, ${x0} ${y1}
		        Q ${x0 - j1} ${h / 2}, ${x0} ${y0 + j1} Z`;
	});
</script>

<div
	bind:clientWidth={w}
	bind:clientHeight={h}
	class="relative {className}"
>
	<svg
		class="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
		viewBox="0 0 {w} {h}"
		preserveAspectRatio="none"
		aria-hidden="true"
	>
		<path
			d={pathData}
			{fill}
			{stroke}
			stroke-width={strokeWidth}
			stroke-linecap="round"
			stroke-linejoin="round"
			style="filter: url(#scribble-filter);"
		/>
	</svg>
	<div class="relative z-10">
		{@render children()}
	</div>
</div>
