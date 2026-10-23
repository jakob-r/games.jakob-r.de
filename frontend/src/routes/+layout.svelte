<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import type { Snippet } from 'svelte';
	import { profile } from '$lib/core/profile.svelte';

	let { children }: { children: Snippet } = $props();

	onMount(() => {
		profile.init();
	});
</script>

<!-- Subtle SVG hand-drawn displacement filter used by scribbly boxes and board grid lines -->
<svg class="pointer-events-none fixed h-0 w-0 opacity-0" aria-hidden="true">
	<defs>
		<filter id="scribble-filter" x="-5%" y="-5%" width="110%" height="110%">
			<feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" result="noise" />
			<feDisplacementMap in="SourceGraphic" in2="noise" scale="1.35" xChannelSelector="R" yChannelSelector="G" />
		</filter>
	</defs>
</svg>

<div class="min-h-dvh flex flex-col">
	{@render children()}
</div>
