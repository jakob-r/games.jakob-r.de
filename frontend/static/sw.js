/// <reference lib="webworker" />

self.addEventListener('install', () => {
	self.skipWaiting();
});

self.addEventListener('activate', (event) => {
	event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
	if (!event.data) return;

	let payload = {
		title: "It's your turn!",
		body: 'Your opponent made a move.',
		url: '/',
		tag: 'turn-notification'
	};

	try {
		const parsed = event.data.json();
		payload = { ...payload, ...parsed };
	} catch {
		payload.body = event.data.text() || payload.body;
	}

	event.waitUntil(
		self.clients
			.matchAll({ type: 'window', includeUncontrolled: true })
			.then((windowClients) => {
				// Suppress OS notification if the user already has this room open and focused
				const isRoomFocused = windowClients.some((client) => {
					try {
						const clientPath = new URL(client.url).pathname;
						return client.focused && clientPath === payload.url;
					} catch {
						return false;
					}
				});

				if (isRoomFocused) {
					return;
				}

				return self.registration.showNotification(payload.title, {
					body: payload.body,
					tag: payload.tag,
					renotify: true,
					data: { url: payload.url }
				});
			})
	);
});

self.addEventListener('notificationclick', (event) => {
	event.notification.close();
	const targetUrl = event.notification.data?.url || '/';

	event.waitUntil(
		self.clients
			.matchAll({ type: 'window', includeUncontrolled: true })
			.then((windowClients) => {
				for (const client of windowClients) {
					try {
						const clientPath = new URL(client.url).pathname;
						if (clientPath === targetUrl && 'focus' in client) {
							return client.focus();
						}
					} catch {
						// ignore invalid URL
					}
				}
				if (self.clients.openWindow) {
					return self.clients.openWindow(targetUrl);
				}
			})
	);
});
