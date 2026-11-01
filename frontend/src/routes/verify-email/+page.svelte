<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import AuthShell from '$lib/core/components/AuthShell.svelte';
	import { auth, authRequest, type AccountUser } from '$lib/core/auth.svelte';

	let status = $state<'working' | 'ok' | 'error'>('working');
	let error = $state('');

	onMount(async () => {
		const token = page.url.searchParams.get('token') ?? '';
		const res = await authRequest<AccountUser>('/verify-email', { token });
		if (res.ok) {
			status = 'ok';
			if (auth.user && res.data && auth.user.id === res.data.id) auth.user = res.data;
		} else {
			status = 'error';
			error = res.error;
		}
	});
</script>

<AuthShell title="Confirm email">
	{#if status === 'working'}
		<p>Checking your link…</p>
	{:else if status === 'ok'}
		<p>Your email address is confirmed. 🎉</p>
		<a href="/account" class="underline underline-offset-4">Go to your account</a>
	{:else}
		<p class="font-medium text-[#dc2626]" role="alert">{error}</p>
		<a href="/account" class="underline underline-offset-4">Request a new link in your account</a>
	{/if}
</AuthShell>
