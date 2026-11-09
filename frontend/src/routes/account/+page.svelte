<script lang="ts">
	import { goto } from '$app/navigation';
	import AuthShell from '$lib/core/components/AuthShell.svelte';
	import ProfileBadge from '$lib/core/components/ProfileBadge.svelte';
	import ScribblyButton from '$lib/core/components/ScribblyButton.svelte';
	import { auth, authRequest } from '$lib/core/auth.svelte';
	import { profile } from '$lib/core/profile.svelte';
	import { pushNotifications } from '$lib/core/notifications.svelte';
	import { friends, type FriendsOverview } from '$lib/core/friends.svelte';

	let currentPassword = $state('');
	let newPassword = $state('');
	let deleteConfirmation = $state('');
	let confirmingDelete = $state(false);
	let notice = $state('');
	let error = $state('');
	let pushMessage = $state('');
	let friendData = $state<FriendsOverview | null>(null);
	let friendError = $state('');
	let removingFriend = $state<number | null>(null);

	async function loadFriends() {
		const res = await friends.overview();
		if (res.ok) friendData = res.data;
		else friendError = res.error;
	}

	$effect(() => {
		if (auth.user) void loadFriends();
	});

	async function friendAction(action: () => Promise<{ ok: boolean; error: string }>) {
		friendError = '';
		const res = await action();
		if (!res.ok) friendError = res.error;
		removingFriend = null;
		await loadFriends();
	}

	async function togglePush(input: HTMLInputElement) {
		pushMessage = await pushNotifications.setEnabled(input.checked);
		// Permission may have been refused: show the real state.
		input.checked = pushNotifications.enabled;
	}

	$effect(() => {
		if (auth.loaded && !auth.user) void goto('/login?next=/account', { replaceState: true });
	});

	async function run(fn: () => Promise<{ ok: boolean; error: string }>, success: string) {
		error = '';
		notice = '';
		const res = await fn();
		if (res.ok) notice = success;
		else error = res.error;
		return res.ok;
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

		<section class="space-y-2">
			<h2 class="text-sm font-medium">Name &amp; color</h2>
			<p class="text-xs text-[#6e6a63]">Saved to your account and used in every game.</p>
			<ProfileBadge />
		</section>

		<section class="space-y-2">
			<h2 class="text-sm font-medium">Friends</h2>
			<p class="text-xs text-[#6e6a63]">
				Add friends by tapping their name in a game you play together (both need an account).
				Friends never see whether you're online.
			</p>
			{#if friendError}
				<p class="text-xs font-medium text-[#dc2626]" role="alert">{friendError}</p>
			{/if}
			{#if friendData}
				{#if friendData.incoming.length}
					<ul class="space-y-1.5">
						{#each friendData.incoming as person (person.user_id)}
							<li class="flex flex-wrap items-center justify-between gap-2 text-sm">
								<span class="flex items-center gap-2">
									<span
										class="h-3 w-3 shrink-0 rounded-full border border-[#1a1917]"
										style="background-color: {person.color || '#faf8f4'};"
									></span>
									<span><strong>{person.name}</strong> wants to be friends</span>
								</span>
								<span class="flex gap-2">
									<ScribblyButton onclick={() => friendAction(() => friends.accept(person.user_id))}>
										Accept
									</ScribblyButton>
									<ScribblyButton onclick={() => friendAction(() => friends.decline(person.user_id))}>
										Decline
									</ScribblyButton>
								</span>
							</li>
						{/each}
					</ul>
				{/if}

				{#if friendData.friends.length}
					<ul class="divide-y divide-[#1a1917]/10">
						{#each friendData.friends as friend (friend.user_id)}
							<li class="flex flex-wrap items-center justify-between gap-2 py-1.5 text-sm">
								<span class="flex items-center gap-2">
									<span
										class="h-3 w-3 shrink-0 rounded-full border border-[#1a1917]"
										style="background-color: {friend.color || '#faf8f4'};"
									></span>
									<span class="font-medium">{friend.label}</span>
								</span>
								{#if removingFriend === friend.user_id}
									<span class="flex gap-2">
										<ScribblyButton
											variant="danger"
											onclick={() => friendAction(() => friends.remove(friend.user_id))}
										>
											Remove
										</ScribblyButton>
										<ScribblyButton onclick={() => (removingFriend = null)}>Keep</ScribblyButton>
									</span>
								{:else}
									<button
										type="button"
										class="cursor-pointer text-xs underline"
										onclick={() => (removingFriend = friend.user_id)}
									>
										Remove
									</button>
								{/if}
							</li>
						{/each}
					</ul>
				{:else}
					<p class="text-sm">No friends yet.</p>
				{/if}

				{#if friendData.outgoing.length}
					<p class="text-xs text-[#6e6a63]">
						Waiting for: {friendData.outgoing.map((p) => p.name).join(', ')}
					</p>
				{/if}
			{/if}
		</section>

		<section class="space-y-2">
			<h2 class="text-sm font-medium">Notifications</h2>
			<label class="flex cursor-pointer items-start gap-2 text-sm">
				<input
					type="checkbox"
					class="mt-0.5 h-4 w-4 cursor-pointer accent-[#1a1917]"
					checked={pushNotifications.enabled}
					disabled={pushNotifications.busy || pushNotifications.permission === 'unsupported'}
					onchange={(e) => togglePush(e.currentTarget)}
				/>
				<span>Push notification on this device when it's my turn</span>
			</label>
			<p class="text-xs text-[#6e6a63]">
				{#if pushNotifications.permission === 'unsupported'}
					This browser doesn't support notifications.
				{:else if pushNotifications.permission === 'denied'}
					Notifications are blocked — allow them in the browser site settings.
				{:else}
					Applies to all your games. Turn it on on each device you play on; the bell in a game is the same switch.
				{/if}
			</p>
			{#if pushMessage}
				<p class="text-xs font-medium" role="status">{pushMessage}</p>
			{/if}
		</section>

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
