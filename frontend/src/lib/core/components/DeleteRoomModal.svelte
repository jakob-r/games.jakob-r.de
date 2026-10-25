<script lang="ts">
	import ScribblyBox from './ScribblyBox.svelte';
	import ScribblyButton from './ScribblyButton.svelte';

	let {
		open = false,
		roomId = '',
		deleting = false,
		onConfirm,
		onClose
	}: {
		open?: boolean;
		roomId?: string;
		deleting?: boolean;
		onConfirm: () => Promise<unknown> | unknown;
		onClose: () => void;
	} = $props();

	async function handleDelete() {
		if (!open || deleting) return;
		await onConfirm();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (!open || deleting) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			onClose();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-[#1a1917]/40 p-4"
		role="dialog"
		tabindex="-1"
		aria-modal="true"
		aria-labelledby="delete-room-title"
		onclick={(e) => {
			if (e.target === e.currentTarget && !deleting) onClose();
		}}
	>
		<ScribblyBox seed={81} class="w-full max-w-sm bg-[#faf8f4] p-5 sm:p-6">
			<h2 id="delete-room-title" class="font-hand text-2xl">Delete this session?</h2>
			<p class="mt-2 text-sm text-[#6e6a63]">
				Permanently delete room
				{#if roomId}
					<span class="font-mono-num font-semibold text-[#1a1917]">#{roomId}</span>
				{/if}
				for everyone. This cannot be undone.
			</p>
			<div class="mt-5 flex flex-wrap justify-end gap-2">
				<ScribblyButton onclick={onClose} disabled={deleting}>Cancel</ScribblyButton>
				<ScribblyButton variant="danger" onclick={handleDelete} disabled={deleting}>
					{deleting ? 'Deleting…' : 'Delete Session'}
				</ScribblyButton>
			</div>
		</ScribblyBox>
	</div>
{/if}
