<script lang="ts">
	// Fonts are self-hosted (bundled by Vite) so no request goes to Google Fonts.
	import '@fontsource/architects-daughter/400.css';
	import '@fontsource/plus-jakarta-sans/400.css';
	import '@fontsource/plus-jakarta-sans/500.css';
	import '@fontsource/plus-jakarta-sans/600.css';
	import '@fontsource/plus-jakarta-sans/700.css';
	import '@fontsource/jetbrains-mono/400.css';
	import '@fontsource/jetbrains-mono/600.css';
	import '../app.css';
	import { onMount } from 'svelte';
	import type { Snippet } from 'svelte';
	import { auth } from '#lib/core/auth.svelte.ts';
	import { profile } from '#lib/core/profile.svelte.ts';
	import { pushNotifications } from '#lib/core/notifications.svelte.ts';

	let { children }: { children: Snippet } = $props();

	onMount(() => {
		profile.init();
		pushNotifications.init();
		void auth.load();
	});

	// Keep this device's push registration on the current player (moves on sign in/out).
	$effect(() => {
		if (auth.loaded && profile.playerId) void pushNotifications.syncPlayer(profile.playerId);
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

<div
	class="flex min-h-dvh flex-col pt-[env(safe-area-inset-top)] pr-[env(safe-area-inset-right)] pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)]"
>
	{@render children()}
</div>
