<script lang="ts">
	import { onMount } from 'svelte';
	import { roomDocumentTitle, TurnNotificationController } from '$lib/core/notifications.svelte';

	let {
		roomId,
		playerId,
		gameSlug,
		gameTitle,
		isMyTurn = false,
		isPlaying = false,
		turnHint = ''
	}: {
		roomId: string;
		playerId: string;
		gameSlug: string;
		gameTitle: string;
		isMyTurn?: boolean;
		isPlaying?: boolean;
		turnHint?: string;
	} = $props();

	const notifier = new TurnNotificationController();

	let initializedTurnTracking = false;
	let previousIsMyTurn = false;
	let ringing = $state<boolean>(false);

	let buttonTitle = $derived.by(() => {
		if (notifier.permission === 'unsupported') {
			return 'Browser notifications are not supported in this browser';
		}
		if (notifier.permission === 'denied') {
			return 'Notifications blocked in browser settings';
		}
		if (notifier.enabled) {
			return notifier.pushSubscribed
				? 'Turn notifications active (including when this tab is in the background) — click to mute'
				: 'Turn notifications active — click to mute';
		}
		return "Notify me when it's my turn";
	});

	async function handleBellClick() {
		const wasEnabled = notifier.enabled;
		await notifier.toggle();
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
			void notifier.notifyTurnIfNeeded(hint || undefined);
		}
		previousIsMyTurn = activeTurn;
	});

	onMount(() => {
		void notifier.init({
			roomId,
			playerId,
			gameSlug,
			gameTitle
		});

		return () => {
			notifier.destroy();
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

	{#if notifier.toastMessage}
		<div
			role="status"
			class="pointer-events-none absolute top-full right-0 z-40 mt-1.5 w-56 rounded border-[1.5px] border-[#1a1917] bg-[#faf8f4] px-2.5 py-1.5 text-[11px] leading-snug font-medium text-[#1a1917] shadow-[2px_2px_0px_#1a1917]"
		>
			{notifier.toastMessage}
		</div>
	{/if}
</div>
