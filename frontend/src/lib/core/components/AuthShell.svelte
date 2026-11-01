<script lang="ts">
	import type { Snippet } from 'svelte';
	import ScribblyBox from './ScribblyBox.svelte';

	let { title, children }: { title: string; children: Snippet } = $props();
</script>

<svelte:head>
	<title>{title} • games.jakob-r.de</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<main class="mx-auto w-full max-w-md flex-1 px-4 py-6 sm:px-6 sm:py-10">
	<a
		href="/"
		class="text-sm font-medium text-[#6e6a63] underline decoration-[#1a1917]/30 underline-offset-4 transition hover:text-[#1a1917] hover:decoration-[#1a1917]"
	>← All games</a>
	<h1 class="font-hand mt-4 mb-4 text-3xl tracking-tight sm:text-4xl">{title}</h1>
	<ScribblyBox seed={11} class="bg-[#faf8f4] p-4 sm:p-6">
		<div class="space-y-4">
			{@render children()}
		</div>
	</ScribblyBox>
</main>
