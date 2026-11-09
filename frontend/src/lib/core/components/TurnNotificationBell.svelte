<script lang="ts">
	import { onMount } from 'svelte';
	import { pushNotifications, roomDocumentTitle } from '$lib/core/notifications.svelte';

	let {
		roomId,
		gameSlug,
		gameTitle,
		isMyTurn = false,
		isPlaying = false,
		turnHint = ''
	}: {
		roomId: string;
		gameSlug: string;
		gameTitle: string;
		isMyTurn?: boolean;
		isPlaying?: boolean;
		turnHint?: string;
	} = $props();

	// The bell is a shortcut to the one per-device switch (also on the account page).
	const notifier = pushNotifications;

	let initializedTurnTracking = false;
	let previousIsMyTurn = false;
	let ringing = $state<boolean>(false);
	let toastMessage = $state<string | null>(null);
	let toastTimer: ReturnType<typeof setTimeout> | null = null;

	let buttonTitle = $derived.by(() => {
		if (notifier.permission === 'unsupported') {
			return 'Browser notifications are not supported in this browser';
		}
		if (notifier.permission === 'denied') {
			return 'Notifications blocked in browser settings';
		}
		if (notifier.enabled) {
			return "Notifications on for all your games on this device — click to turn off";
		}
		return "Notify me when it's my turn (all games)";
	});

	function showToast(msg: string) {
		if (!msg) return;
		toastMessage = msg;
		if (toastTimer) clearTimeout(toastTimer);
		toastTimer = setTimeout(() => {
			toastMessage = null;
		}, 2800);
	}

	async function handleBellClick() {
		const wasEnabled = notifier.enabled;
		showToast(await notifier.setEnabled(!wasEnabled, { roomId }));
		if (!wasEnabled && notifier.enabled) {
			ringing = true;
			setTimeout(() => {
				ringing = false;
			}, 600);
		}
	}

	// Watch for turn transitions to fire notifications and publish the tab title.
	$effect(() => {
		const activeTurn = isPlaying && isMyTurn;
		const hint = turnHint;

		roomDocumentTitle.text = activeTurn
			? `🔔 Your turn! • ${gameTitle}`
			: `${gameTitle} #${roomId} • games.jakob-r.de`;

		if (!initializedTurnTracking) {
			initializedTurnTracking = true;
			previousIsMyTurn = activeTurn;
			return;
		}

		if (activeTurn && !previousIsMyTurn) {
			void notifier.notifyTurnIfNeeded({ roomId, gameSlug, gameTitle, body: hint || undefined });
		}
		previousIsMyTurn = activeTurn;
	});

	onMount(() => {
		notifier.init();
		return () => {
			if (toastTimer) clearTimeout(toastTimer);
			roomDocumentTitle.text = null;
		};
	});
</script>

<div class="relative inline-flex items-center">
	<button
		type="button"
		onclick={handleBellClick}
		disabled={notifier.busy}
		title={buttonTitle}
		aria-label={buttonTitle}
		aria-pressed={notifier.enabled}
		class="relative inline-flex cursor-pointer items-center justify-center rounded border-[1.5px] border-[#1a1917] p-1.5 shadow-[1.5px_1.5px_0px_#1a1917] transition disabled:cursor-not-allowed disabled:opacity-50
		{notifier.enabled
			? 'bg-[#fef3c7] text-[#b45309] hover:bg-[#fde68a]'
			: notifier.permission === 'denied'
				? 'bg-[#faf8f4] text-[#9ca3af] hover:bg-[#f2eee6]'
				: 'bg-[#faf8f4] text-[#6e6a63] hover:bg-[#f2eee6] hover:text-[#1a1917]'}"
	>
		<svg
			class="h-3.5 w-3.5 {ringing ? 'animate-bounce' : ''}"
			viewBox="0 0 24 24"
			fill={notifier.enabled ? 'currentColor' : 'none'}
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
			<path d="M13.73 21a2 2 0 0 1-3.46 0" />
			{#if notifier.enabled}
				<path d="M4 3C2.8 4.3 2 6 2 8" fill="none" />
				<path d="M20 3c1.2 1.3 2 3 2 5" fill="none" />
			{:else if notifier.permission === 'denied'}
				<line x1="2" y1="2" x2="22" y2="22" />
			{/if}
		</svg>

		{#if notifier.enabled}
			<span
				class="absolute -top-1 -right-1 h-2 w-2 rounded-full border border-[#1a1917] bg-[#16a34a]"
				aria-hidden="true"
			></span>
		{/if}
	</button>

	{#if toastMessage}
		<div
			role="status"
			class="pointer-events-none absolute top-full right-0 z-40 mt-1.5 w-56 rounded border-[1.5px] border-[#1a1917] bg-[#faf8f4] px-2.5 py-1.5 text-[11px] leading-snug font-medium text-[#1a1917] shadow-[2px_2px_0px_#1a1917]"
		>
			{toastMessage}
		</div>
	{/if}
</div>
