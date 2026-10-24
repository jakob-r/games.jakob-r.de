const STORAGE_KEY = 'games_turn_notifications_v1';

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

function readStoredRooms(): Record<string, boolean> {
	if (typeof window === 'undefined') return {};
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return {};
		const parsed = JSON.parse(raw);
		if (parsed && typeof parsed === 'object') {
			return parsed as Record<string, boolean>;
		}
	} catch {
		// ignore corrupt storage
	}
	return {};
}

function writeStoredRoom(roomId: string, active: boolean): void {
	if (typeof window === 'undefined') return;
	try {
		const map = readStoredRooms();
		if (active) {
			map[roomId] = true;
		} else {
			delete map[roomId];
		}
		localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
	} catch {
		// ignore storage quota errors
	}
}

export class TurnNotificationController {
	enabled = $state<boolean>(false);
	permission = $state<NotificationPermission | 'unsupported'>('default');
	pushSubscribed = $state<boolean>(false);
	busy = $state<boolean>(false);
	toastMessage = $state<string | null>(null);

	private roomId = '';
	private playerId = '';
	private gameSlug = '';
	private gameTitle = '';
	private toastTimer: ReturnType<typeof setTimeout> | null = null;

	private showToast(msg: string, durationMs = 2800): void {
		this.toastMessage = msg;
		if (this.toastTimer) clearTimeout(this.toastTimer);
		this.toastTimer = setTimeout(() => {
			this.toastMessage = null;
		}, durationMs);
	}

	async init(params: {
		roomId: string;
		playerId: string;
		gameSlug: string;
		gameTitle: string;
	}): Promise<void> {
		this.roomId = params.roomId;
		this.playerId = params.playerId;
		this.gameSlug = params.gameSlug;
		this.gameTitle = params.gameTitle;

		if (typeof window === 'undefined' || !('Notification' in window)) {
			this.permission = 'unsupported';
			this.enabled = false;
			return;
		}

		this.permission = Notification.permission;
		const stored = readStoredRooms()[this.roomId] === true;

		if (stored && this.permission === 'granted') {
			this.enabled = true;
			await this.syncWebPushSubscription();
		} else {
			this.enabled = false;
			if (stored && this.permission !== 'granted') {
				writeStoredRoom(this.roomId, false);
			}
		}
	}

	async toggle(): Promise<void> {
		if (this.busy) return;
		if (typeof window === 'undefined' || !('Notification' in window)) {
			this.permission = 'unsupported';
			this.showToast('Browser notifications are not supported on this device.');
			return;
		}

		this.busy = true;
		try {
			if (this.enabled) {
				this.enabled = false;
				writeStoredRoom(this.roomId, false);
				await this.unsubscribeWebPush();
				this.showToast('Turn notifications muted.');
				return;
			}

			let currentPerm = Notification.permission;
			if (currentPerm === 'default') {
				currentPerm = await Notification.requestPermission();
			}
			this.permission = currentPerm;

			if (currentPerm !== 'granted') {
				this.enabled = false;
				writeStoredRoom(this.roomId, false);
				this.showToast('Notifications blocked — allow them in browser site settings.');
				return;
			}

			this.enabled = true;
			writeStoredRoom(this.roomId, true);
			const pushOk = await this.syncWebPushSubscription();
			if (pushOk) {
				this.showToast("Turn notifications active (works in background & closed tab).");
			} else {
				this.showToast("Turn notifications active while this tab stays open.");
			}
		} finally {
			this.busy = false;
		}
	}

	private async syncWebPushSubscription(): Promise<boolean> {
		if (
			typeof window === 'undefined' ||
			!('serviceWorker' in navigator) ||
			!('PushManager' in window) ||
			!this.roomId ||
			!this.playerId
		) {
			this.pushSubscribed = false;
			return false;
		}

		try {
			const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
			await navigator.serviceWorker.ready;

			const keyRes = await fetch('/api/notifications/vapid-public-key');
			if (!keyRes.ok) {
				this.pushSubscribed = false;
				return false;
			}
			const { public_key: publicKey } = (await keyRes.json()) as { public_key: string };
			if (!publicKey) {
				this.pushSubscribed = false;
				return false;
			}

			let sub = await registration.pushManager.getSubscription();
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
			if (!endpoint || !p256dh || !auth) {
				this.pushSubscribed = false;
				return false;
			}

			const subRes = await fetch(
				`/api/rooms/${encodeURIComponent(this.roomId)}/notifications/subscribe`,
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({
						player_id: this.playerId,
						endpoint,
						keys: { p256dh, auth }
					})
				}
			);
			this.pushSubscribed = subRes.ok;
			return subRes.ok;
		} catch {
			this.pushSubscribed = false;
			return false;
		}
	}

	private async unsubscribeWebPush(): Promise<void> {
		this.pushSubscribed = false;
		if (!this.roomId || !this.playerId) return;

		let endpointParam = '';
		try {
			if (typeof window !== 'undefined' && 'serviceWorker' in navigator) {
				const registration = await navigator.serviceWorker.getRegistration('/');
				const sub = await registration?.pushManager.getSubscription();
				if (sub?.endpoint) {
					endpointParam = `&endpoint=${encodeURIComponent(sub.endpoint)}`;
				}
			}
		} catch {
			// ignore
		}

		try {
			await fetch(
				`/api/rooms/${encodeURIComponent(this.roomId)}/notifications/subscribe?player_id=${encodeURIComponent(this.playerId)}${endpointParam}`,
				{ method: 'DELETE' }
			);
		} catch {
			// ignore network errors on unsubscribe
		}
	}

	async notifyTurnIfNeeded(body?: string): Promise<void> {
		if (!this.enabled || typeof window === 'undefined' || !('Notification' in window)) {
			return;
		}
		if (Notification.permission !== 'granted') {
			return;
		}

		// Only show an OS notification if the tab is in the background or window is unfocused
		const isHiddenOrUnfocused =
			document.visibilityState === 'hidden' || !document.hasFocus();
		if (!isHiddenOrUnfocused) {
			return;
		}

		const title = `${this.gameTitle} — It's your turn!`;
		const messageBody =
			body || `Your opponent finished their move in #${this.roomId}. Your turn!`;
		const tag = `turn-${this.roomId}`;
		const url = `/${this.gameSlug}/${this.roomId}`;

		try {
			if ('serviceWorker' in navigator) {
				const registration = await navigator.serviceWorker.getRegistration('/');
				if (registration && 'showNotification' in registration) {
					await registration.showNotification(title, {
						body: messageBody,
						tag,
						data: { url }
					});
					return;
				}
			}
		} catch {
			// Fall back to standard Notification API
		}

		try {
			const n = new Notification(title, {
				body: messageBody,
				tag
			});
			n.onclick = () => {
				window.focus();
				n.close();
			};
		} catch {
			// Ignore on environments where direct Notification constructor is restricted
		}
	}

	destroy(): void {
		if (this.toastTimer) {
			clearTimeout(this.toastTimer);
			this.toastTimer = null;
		}
	}
}
