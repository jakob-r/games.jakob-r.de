<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		onclick,
		disabled = false,
		variant = 'default',
		accentColor = '#1a1917',
		type = 'button',
		class: className = '',
		title = '',
		children
	}: {
		onclick?: (e: MouseEvent) => void;
		disabled?: boolean;
		variant?: 'default' | 'primary' | 'ghost';
		accentColor?: string;
		type?: 'button' | 'submit';
		class?: string;
		title?: string;
		children: Snippet;
	} = $props();
</script>

<button
	{type}
	{onclick}
	{disabled}
	{title}
	style="--accent: {accentColor};"
	class="group relative inline-flex cursor-pointer items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-transform duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-45
	{variant === 'primary'
		? 'bg-[var(--accent)] text-[#faf8f4] shadow-[2px_2px_0px_#1a1917]'
		: variant === 'default'
			? 'border-[1.8px] border-[#1a1917] bg-[#faf8f4] text-[#1a1917] shadow-[2px_2px_0px_#1a1917] hover:bg-[#f2eee6]'
			: 'border border-transparent text-[#1a1917] hover:border-[#1a1917]/30 hover:bg-[#f2eee6]/70'} {className}"
>
	{@render children()}
</button>
