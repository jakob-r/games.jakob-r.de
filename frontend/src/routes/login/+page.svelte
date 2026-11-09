<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import AuthShell from '#lib/core/components/AuthShell.svelte';
	import ScribblyButton from '#lib/core/components/ScribblyButton.svelte';
	import { auth, authRequest, type AccountUser } from '#lib/core/auth.svelte.ts';
	import { profile } from '#lib/core/profile.svelte.ts';

	type Mode = 'login' | 'register' | 'forgot';

	let mode = $state<Mode>('login');
	let email = $state('');
	let password = $state('');
	let name = $state('');
	let busy = $state(false);
	let error = $state('');
	let message = $state('');

	const next = $derived.by(() => {
		const n = page.url.searchParams.get('next') ?? '/';
		return n.startsWith('/') && !n.startsWith('//') ? n : '/';
	});
	const title = $derived(
		mode === 'register' ? 'Create account' : mode === 'forgot' ? 'Reset password' : 'Sign in'
	);
	const googleHref = $derived(
		`/api/auth/oauth/google/start?next=${encodeURIComponent(next)}&player_id=${encodeURIComponent(profile.playerId)}`
	);

	onMount(() => {
		if (page.url.searchParams.get('error') === 'google') {
			error = 'Google sign-in failed. Please try again.';
		}
	});

	function setMode(m: Mode) {
		mode = m;
		error = '';
		message = '';
	}

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		message = '';
		if (mode === 'forgot') {
			const res = await authRequest<{ message: string }>('/forgot-password', { email });
			if (res.ok) message = res.data?.message ?? 'Check your inbox.';
			else error = res.error;
		} else {
			// A new account adopts this browser's player id, keeping its stats and rooms.
			const res =
				mode === 'register'
					? await authRequest<AccountUser>('/register', {
							email,
							password,
							name: name || (profile.nameConfigured ? profile.name : ''),
							player_id: profile.playerId
						})
					: await authRequest<AccountUser>('/login', { email, password });
			if (res.ok && res.data) {
				auth.setUser(res.data);
				await goto(next);
			} else {
				error = res.error;
			}
		}
		busy = false;
	}

	const inputClass =
		'w-full rounded-md border-[1.8px] border-[#1a1917] bg-white px-3 py-2 text-base shadow-[2px_2px_0px_#1a1917] focus:outline-none';
</script>

<AuthShell {title}>
	{#if mode !== 'forgot' && auth.googleEnabled}
		<a
			href={googleHref}
			class="inline-flex w-full cursor-pointer items-center justify-center gap-2 rounded-md border-[1.8px] border-[#1a1917] bg-white px-3.5 py-2 text-sm font-medium shadow-[2px_2px_0px_#1a1917] transition hover:bg-[#f2eee6]"
		>
			<svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
				<path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6.1C12.3 13.6 17.7 9.5 24 9.5z" />
				<path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z" />
				<path fill="#FBBC05" d="M10.4 28.7A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.9-4.7l-7.8-6.1A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.8l7.8-6.1z" />
				<path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.9 2.3-8.4 2.3-6.3 0-11.7-4.1-13.6-9.8l-7.8 6.1C6.5 42.6 14.6 48 24 48z" />
			</svg>
			Continue with Google
		</a>
		<div class="flex items-center gap-3 text-xs text-[#6e6a63]">
			<span class="h-px flex-1 bg-[#1a1917]/20"></span>or with email<span class="h-px flex-1 bg-[#1a1917]/20"></span>
		</div>
	{/if}

	<form onsubmit={submit} class="space-y-3">
		{#if mode === 'register'}
			<input
				type="text"
				bind:value={name}
				maxlength="32"
				placeholder="Display name (optional)"
				aria-label="Display name"
				autocomplete="nickname"
				class={inputClass}
			/>
		{/if}
		<input
			type="email"
			bind:value={email}
			required
			placeholder="Email"
			aria-label="Email"
			autocomplete="email"
			class={inputClass}
		/>
		{#if mode !== 'forgot'}
			<input
				type="password"
				bind:value={password}
				required
				minlength={mode === 'register' ? 8 : undefined}
				placeholder={mode === 'register' ? 'Password (min. 8 characters)' : 'Password'}
				aria-label="Password"
				autocomplete={mode === 'register' ? 'new-password' : 'current-password'}
				class={inputClass}
			/>
		{/if}

		{#if error}
			<p class="text-xs font-medium text-[#dc2626]" role="alert">{error}</p>
		{/if}
		{#if message}
			<p class="text-xs font-medium text-[#15803d]" role="status">{message}</p>
		{/if}

		<ScribblyButton type="submit" variant="primary" disabled={busy} class="w-full">
			{mode === 'register' ? 'Create account' : mode === 'forgot' ? 'Send reset link' : 'Sign in'}
		</ScribblyButton>
	</form>

	<div class="flex flex-wrap justify-between gap-2 text-sm">
		{#if mode === 'login'}
			<button type="button" class="cursor-pointer underline underline-offset-4" onclick={() => setMode('register')}>
				Create account
			</button>
			<button type="button" class="cursor-pointer underline underline-offset-4" onclick={() => setMode('forgot')}>
				Forgot password?
			</button>
		{:else}
			<button type="button" class="cursor-pointer underline underline-offset-4" onclick={() => setMode('login')}>
				Back to sign in
			</button>
		{/if}
	</div>
	<p class="text-xs text-[#6e6a63]">
		An account is optional. It keeps your stats and rooms across devices. See the
		<a href="/privacy" class="underline underline-offset-2">privacy policy</a>.
	</p>
</AuthShell>
