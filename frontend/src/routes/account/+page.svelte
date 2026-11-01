<script lang="ts">
	import { goto } from '$app/navigation';
	import AuthShell from '$lib/core/components/AuthShell.svelte';
	import ScribblyButton from '$lib/core/components/ScribblyButton.svelte';
	import { auth, authRequest, type AccountUser } from '$lib/core/auth.svelte';
	import { profile } from '$lib/core/profile.svelte';

	let name = $state('');
	let currentPassword = $state('');
	let newPassword = $state('');
	let deleteConfirmation = $state('');
	let confirmingDelete = $state(false);
	let notice = $state('');
	let error = $state('');

	$effect(() => {
		if (auth.loaded && !auth.user) void goto('/login?next=/account', { replaceState: true });
	});
	$effect(() => {
		if (auth.user) name = auth.user.name;
	});

	async function run(fn: () => Promise<{ ok: boolean; error: string }>, success: string) {
		error = '';
		notice = '';
		const res = await fn();
		if (res.ok) notice = success;
		else error = res.error;
		return res.ok;
	}

	function saveName() {
		return run(async () => {
			const res = await authRequest<AccountUser>('/account/name', { name });
			if (res.ok && res.data) {
				auth.user = res.data;
				if (res.data.name) profile.setName(res.data.name);
			}
			return res;
		}, 'Name saved.');
	}

	async function changePassword() {
		const ok = await run(
			() =>
				authRequest('/account/password', {
					current_password: auth.user?.has_password ? currentPassword : null,
					new_password: newPassword
				}),
			'Password updated.'
		);
		if (ok) {
			currentPassword = newPassword = '';
			await auth.load();
		}
	}

	function resend() {
		return run(() => authRequest('/resend-verification'), 'Verification email sent.');
	}

	async function deleteAccount() {
		const ok = await run(
			() => authRequest('/account/delete', { confirmation: deleteConfirmation }),
			''
		);
		if (ok) {
			auth.setUser(null);
			await goto('/');
		}
	}

	async function signOut() {
		await auth.logout();
		await goto('/');
	}

	const inputClass =
		'w-full rounded-md border-[1.8px] border-[#1a1917] bg-white px-3 py-2 text-base shadow-[2px_2px_0px_#1a1917] focus:outline-none';
</script>

<AuthShell title="Account">
	{#if auth.user}
		<p class="text-sm">
			Signed in as <strong class="break-all">{auth.user.email}</strong>
		</p>
		{#if !auth.user.email_verified}
			<p class="rounded border border-[#1a1917]/40 bg-white px-3 py-2 text-xs">
				Your email isn't confirmed yet. Check your inbox or
				<button type="button" class="cursor-pointer underline" onclick={resend}>send the link again</button>.
			</p>
		{/if}

		{#if error}
			<p class="text-xs font-medium text-[#dc2626]" role="alert">{error}</p>
		{/if}
		{#if notice}
			<p class="text-xs font-medium text-[#15803d]" role="status">{notice}</p>
		{/if}

		<form
			class="space-y-2"
			onsubmit={(e) => {
				e.preventDefault();
				void saveName();
			}}
		>
			<label for="acc-name" class="text-sm font-medium">Display name</label>
			<input id="acc-name" type="text" bind:value={name} maxlength="32" class={inputClass} />
			<ScribblyButton type="submit">Save name</ScribblyButton>
		</form>

		<form
			class="space-y-2"
			onsubmit={(e) => {
				e.preventDefault();
				void changePassword();
			}}
		>
			<h2 class="text-sm font-medium">{auth.user.has_password ? 'Change password' : 'Set a password'}</h2>
			{#if auth.user.has_password}
				<input
					type="password"
					bind:value={currentPassword}
					required
					placeholder="Current password"
					aria-label="Current password"
					autocomplete="current-password"
					class={inputClass}
				/>
			{/if}
			<input
				type="password"
				bind:value={newPassword}
				required
				minlength="8"
				placeholder="New password (min. 8 characters)"
				aria-label="New password"
				autocomplete="new-password"
				class={inputClass}
			/>
			<ScribblyButton type="submit">Update password</ScribblyButton>
		</form>

		<div class="flex flex-wrap gap-3 border-t border-[#1a1917]/20 pt-4">
			<ScribblyButton onclick={signOut}>Sign out</ScribblyButton>
			<ScribblyButton variant="danger" onclick={() => (confirmingDelete = !confirmingDelete)}>
				Delete account
			</ScribblyButton>
		</div>

		{#if confirmingDelete}
			<form
				class="space-y-2"
				onsubmit={(e) => {
					e.preventDefault();
					void deleteAccount();
				}}
			>
				<p class="text-xs">
					This permanently deletes your account, your stats and the rooms you host.
					{auth.user.has_password ? 'Enter your password to confirm.' : 'Type your email address to confirm.'}
				</p>
				<input
					type={auth.user.has_password ? 'password' : 'email'}
					bind:value={deleteConfirmation}
					required
					aria-label="Confirmation"
					class={inputClass}
				/>
				<ScribblyButton type="submit" variant="danger">Delete forever</ScribblyButton>
			</form>
		{/if}
	{:else}
		<p>Loading…</p>
	{/if}
</AuthShell>
