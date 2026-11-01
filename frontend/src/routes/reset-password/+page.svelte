<script lang="ts">
	import { page } from '$app/state';
	import AuthShell from '$lib/core/components/AuthShell.svelte';
	import ScribblyButton from '$lib/core/components/ScribblyButton.svelte';
	import { authRequest } from '$lib/core/auth.svelte';

	let password = $state('');
	let busy = $state(false);
	let error = $state('');
	let done = $state(false);

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		const res = await authRequest('/reset-password', {
			token: page.url.searchParams.get('token') ?? '',
			password
		});
		if (res.ok) done = true;
		else error = res.error;
		busy = false;
	}
</script>

<AuthShell title="New password">
	{#if done}
		<p>Your password was updated.</p>
		<a href="/login" class="underline underline-offset-4">Sign in</a>
	{:else}
		<form onsubmit={submit} class="space-y-3">
			<input
				type="password"
				bind:value={password}
				required
				minlength="8"
				placeholder="New password (min. 8 characters)"
				aria-label="New password"
				autocomplete="new-password"
				class="w-full rounded-md border-[1.8px] border-[#1a1917] bg-white px-3 py-2 text-base shadow-[2px_2px_0px_#1a1917] focus:outline-none"
			/>
			{#if error}
				<p class="text-xs font-medium text-[#dc2626]" role="alert">{error}</p>
			{/if}
			<ScribblyButton type="submit" variant="primary" disabled={busy} class="w-full">
				Set password
			</ScribblyButton>
		</form>
	{/if}
</AuthShell>
