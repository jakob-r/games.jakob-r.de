<script lang="ts">
	// Quiet "install as app" hint for the bottom of the landing page.
	// The <pwa-install> dialog (khmyznikov/pwa-install) never opens by itself:
	// both manual-* flags are set, so it only shows when the button is clicked.
	import { onMount } from 'svelte';
	import ScribblyButton from './ScribblyButton.svelte';

	type PwaInstallElement = HTMLElement & {
		showDialog: (forced?: boolean) => void;
		externalPromptEvent: Event | null;
	};

	let visible = $state(false);
	let dialog: PwaInstallElement | null = null;

	function isStandalone(): boolean {
		return (
			window.matchMedia('(display-mode: standalone)').matches ||
			(navigator as Navigator & { standalone?: boolean }).standalone === true
		);
	}

	onMount(() => {
		if (isStandalone()) return;
		visible = true;
		let cancelled = false;
		void import('@khmyznikov/pwa-install').then(() => {
			if (cancelled) return;
			const el = document.createElement('pwa-install') as PwaInstallElement;
			el.setAttribute('manifest-url', '/manifest.json');
			el.setAttribute('manual-apple', '');
			el.setAttribute('manual-chrome', '');
			el.setAttribute('install-description', 'Opens full screen and starts like any other app.');
			el.setAttribute('styles', JSON.stringify({ '--tint-color': '#1a1917' }));
			// Chromium may have fired beforeinstallprompt before this module loaded (see app.html).
			const early = (window as Window & { __installPrompt?: Event }).__installPrompt;
			if (early) el.externalPromptEvent = early;
			el.addEventListener('pwa-install-success-event', () => (visible = false));
			document.body.appendChild(el);
			dialog = el;
		});
		return () => {
			cancelled = true;
			dialog?.remove();
			dialog = null;
		};
	});

	function open() {
		dialog?.showDialog(true);
	}
</script>

{#if visible}
	<section
		class="mt-10 flex flex-col items-center gap-3 text-center text-sm text-[#6e6a63] sm:flex-row sm:justify-center sm:text-left"
		aria-label="Install as app"
	>
		<img src="/icons/icon-192.png" alt="" width="40" height="40" class="h-10 w-10 rounded-lg" />
		<p>
			<span class="font-hand text-base text-[#1a1917]">Play like an app.</span>
			Add <span class="font-medium text-[#1a1917]">games j</span> to your home screen or dock.
		</p>
		<ScribblyButton onclick={open} class="shrink-0">Install</ScribblyButton>
	</section>
{/if}
