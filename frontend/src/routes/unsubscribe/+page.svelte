<script lang="ts">
	import { page } from '$app/state';
	import AuthShell from '#lib/core/components/AuthShell.svelte';
	import ScribblyButton from '#lib/core/components/ScribblyButton.svelte';

	// A button (not an automatic request) so link scanners in mail clients don't unsubscribe.
	let busy = $state(false);
	let done = $state<'turn' | 'invite' | null>(null);
	let error = $state('');

	async function unsubscribe() {
		busy = true;
		error = '';
		try {
			const token = page.url.searchParams.get('token') ?? '';
			const res = await fetch(`/api/mail/unsubscribe?token=${encodeURIComponent(token)}`, {
				method: 'POST'
			});
			const data = await res.json().catch(() => null);
			if (res.ok) done = data?.kind ?? 'turn';
			else error = typeof data?.detail === 'string' ? data.detail : 'Something went wrong.';
		} catch {
			error = 'Could not reach the server.';
		} finally {
			busy = false;
		}
	}
</script>

<AuthShell title="Emails">
	{#if done}
		<p>
			Done — you won't get {done === 'invite' ? 'invite' : '"your turn"'} emails any more. You can turn
			them back on in your <a href="/account" class="underline">account</a>.
		</p>
	{:else}
		<p class="text-sm">Turn off this kind of notification email?</p>
		{#if error}
			<p class="text-xs font-medium text-[#dc2626]" role="alert">{error}</p>
		{/if}
		<ScribblyButton variant="primary" onclick={unsubscribe} disabled={busy}>
			{busy ? 'Turning off…' : 'Turn off emails'}
		</ScribblyButton>
	{/if}
</AuthShell>
