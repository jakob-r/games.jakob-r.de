import { profile } from '$lib/core/profile.svelte';

/** One switch per browser/device: on means pushes for every room where it's your turn. */
const STORAGE_KEY = 'games_push_notifications_v2';
/** Before v2, notifications were switched on per room ({ [roomId]: true }). */
const LEGACY_ROOMS_KEY = 'games_turn_notifications_v1';

/** Page title owned by the turn bell. Route heads fall back when this is null. */
export const roomDocumentTitle = $state<{ text: string | null }>({ text: null });

function urlBase64ToUint8Array(base64String: string): Uint8Array {
	const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
	const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
	const rawData = window.atob(base64);
	const outputArray = new Uint8Array(rawData.length);
	for (let i = 0; i < rawData.length; ++i) {
		outputArray[i] = rawData.charCodeAt(i);
	}
	return outputArray;
}

function applicationServerKeysMatch(existing: ArrayBuffer | null, publicKey: string): boolean {
	if (!existing) return false;
	const current = urlBase64ToUint8Array(publicKey);
	const previous = new Uint8Array(existing);
	if (previous.length !== current.length) return false;
	for (let i = 0; i < previous.length; i++) {
		if (previous[i] !== current[i]) return false;
	}
	return true;
}

function readStoredEnabled(): boolean {
	try {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored !== null) return stored === '1';
		// Anyone who had the bell on in some room keeps notifications on.
		const legacy = JSON.parse(localStorage.getItem(LEGACY_ROOMS_KEY) ?? '{}');
		const enabled =
			!!legacy && typeof legacy === 'object' && Object.values(legacy).some((v) => v === true);
		localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0');
		localStorage.removeItem(LEGACY_ROOMS_KEY);
		return enabled;
	} catch {
		return false;
	}
}

function writeStoredEnabled(enabled: boolean): void {
	try {
		localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0');
	} catch {
		// ignore storage errors
	}
}

function pushSupported(): boolean {
	return (
		typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window
	);
}

async function currentEndpoint(): Promise<string | null> {
	if (!pushSupported()) return null;
	try {
		const registration = await navigator.serviceWorker.getRegistration('/');
		const sub = await registration?.pushManager.getSubscription();
		return sub?.endpoint ?? null;
	} catch {
		return null;
	}
}

class PushNotificationStore {
	enabled = $state<boolean>(false);
	permission = $state<NotificationPermission | 'unsupported'>('default');
	pushSubscribed = $state<boolean>(false);
	busy = $state<boolean>(false);

	private initialized = false;
	/** Player id the device is registered for on the server. */
	private syncedPlayerId = '';

	/** Read the stored switch and register this device for the current player. */
	init(): void {
		if (this.initialized || typeof window === 'undefined') return;
		this.initialized = true;
		if (!('Notification' in window)) {
			this.permission = 'unsupported';
			return;
		}
		this.permission = Notification.permission;
		const stored = readStoredEnabled();
		if (stored && this.permission === 'granted') {
			this.enabled = true;
		} else if (stored) {
			writeStoredEnabled(false);
		}
	}

	/**
	 * Keep the server registration on the current player id. Called whenever the
	 * player id changes (sign in/out); the server moves the device to the new id.
	 */
	async syncPlayer(playerId: string): Promise<void> {
		if (!this.enabled || !playerId || playerId === this.syncedPlayerId) return;
		await this.subscribe(playerId);
	}

	/** Switch notifications on/off for this device. Returns a short message for the UI. */
	async setEnabled(on: boolean, opts: { roomId?: string } = {}): Promise<string> {
		this.init();
		if (this.permission === 'unsupported') {
			return 'Browser notifications are not supported on this device.';
		}
		if (this.busy) return '';
		this.busy = true;
		try {
			if (!on) {
				this.enabled = false;
				writeStoredEnabled(false);
				await this.unsubscribe();
				return 'Notifications off on this device.';
			}

			let perm = Notification.permission;
			if (perm === 'default') {
				perm = await Notification.requestPermission();
			}
			this.permission = perm;
			if (perm !== 'granted') {
				this.enabled = false;
				writeStoredEnabled(false);
				return 'Notifications blocked — allow them in the browser site settings.';
			}

			this.enabled = true;
			writeStoredEnabled(true);
			const pushOk = await this.subscribe(profile.playerId, opts.roomId);
			return pushOk
				? "Notifications on. You'll be notified when it's your turn in any game."
				: 'Notifications on while a game tab stays open.';
		} finally {
			this.busy = false;
		}
	}

	private async subscribe(playerId: string, roomId?: string): Promise<boolean> {
		if (!pushSupported() || !playerId) {
			this.pushSubscribed = false;
			return false;
		}
		try {
			const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
			await navigator.serviceWorker.ready;

			const keyRes = await fetch('/api/notifications/vapid-public-key');
			if (!keyRes.ok) throw new Error('no key');
			const { public_key: publicKey } = (await keyRes.json()) as { public_key: string };
			if (!publicKey) throw new Error('no key');

			let sub = await registration.pushManager.getSubscription();
			if (sub && !applicationServerKeysMatch(sub.options.applicationServerKey, publicKey)) {
				await sub.unsubscribe();
				sub = null;
			}
			if (!sub) {
				const appServerKey = urlBase64ToUint8Array(publicKey);
				sub = await registration.pushManager.subscribe({
					userVisibleOnly: true,
					applicationServerKey: appServerKey.buffer as ArrayBuffer
				});
			}

			const subJson = sub.toJSON();
			const endpoint = subJson.endpoint ?? '';
			const p256dh = subJson.keys?.p256dh ?? '';
			const auth = subJson.keys?.auth ?? '';
			if (!endpoint || !p256dh || !auth) throw new Error('incomplete subscription');

			const res = await fetch('/api/notifications/subscribe', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					player_id: playerId,
					endpoint,
					keys: { p256dh, auth },
					...(roomId ? { room_id: roomId } : {})
				})
			});
			this.pushSubscribed = res.ok;
			this.syncedPlayerId = res.ok ? playerId : '';
			return res.ok;
		} catch {
			this.pushSubscribed = false;
			this.syncedPlayerId = '';
			return false;
		}
	}

	private async unsubscribe(): Promise<void> {
		const playerId = this.syncedPlayerId || profile.playerId;
		this.pushSubscribed = false;
		this.syncedPlayerId = '';
		const endpoint = await currentEndpoint();
		if (!endpoint || !playerId) return;
		try {
			await fetch(
				`/api/notifications/subscribe?player_id=${encodeURIComponent(playerId)}&endpoint=${encodeURIComponent(endpoint)}`,
				{ method: 'DELETE' }
			);
		} catch {
			// ignore network errors on unsubscribe
		}
	}

	/** In-tab fallback when Web Push isn't available but notifications are allowed. */
	async notifyTurnIfNeeded(params: {
		roomId: string;
		gameSlug: string;
		gameTitle: string;
		body?: string;
	}): Promise<void> {
		if (!this.enabled || typeof window === 'undefined' || !('Notification' in window)) return;
		if (Notification.permission !== 'granted') return;
		// The service worker shows the Web Push unless this room's tab is focused.
		if (this.pushSubscribed) return;
		if (document.visibilityState !== 'hidden' && document.hasFocus()) return;

		const title = `${params.gameTitle} — It's your turn!`;
		const body =
			params.body || `Your opponent finished their move in #${params.roomId}. Your turn!`;
		const tag = `turn-${params.roomId}`;
		const url = `/${params.gameSlug}/${params.roomId}`;

		try {
			if ('serviceWorker' in navigator) {
				const registration = await navigator.serviceWorker.getRegistration('/');
				if (registration && 'showNotification' in registration) {
					await registration.showNotification(title, { body, tag, data: { url } });
					return;
				}
			}
		} catch {
			// Fall back to standard Notification API
		}

		try {
			const n = new Notification(title, { body, tag });
			n.onclick = () => {
				window.focus();
				n.close();
			};
		} catch {
			// Ignore environments where the Notification constructor is restricted
		}
	}
}

export const pushNotifications = new PushNotificationStore();
