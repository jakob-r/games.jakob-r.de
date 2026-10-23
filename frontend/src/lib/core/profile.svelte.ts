import { PRESET_PLAYER_COLORS } from './color';

const STORAGE_KEY_ID = 'games_jakob_player_id';
const STORAGE_KEY_NAME = 'games_jakob_player_name';
const STORAGE_KEY_COLOR = 'games_jakob_player_color';

const ADJECTIVES = ['Scribbly', 'Swift', 'Clever', 'Quiet', 'Inky', 'Dotted', 'Sharp', 'Nimble'];
const NOUNS = ['Fox', 'Owl', 'Badger', 'Raven', 'Otter', 'Finch', 'Lynx', 'Hedgehog'];

function generateRandomId(): string {
	if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
		return crypto.randomUUID();
	}
	return 'p_' + Math.random().toString(36).slice(2, 11) + Date.now().toString(36);
}

function generateDefaultName(): string {
	const adj = ADJECTIVES[Math.floor(Math.random() * ADJECTIVES.length)];
	const noun = NOUNS[Math.floor(Math.random() * NOUNS.length)];
	return `${adj} ${noun}`;
}

class ProfileStore {
	playerId = $state<string>('');
	name = $state<string>('Scribbly Fox');
	primaryColor = $state<string>(PRESET_PLAYER_COLORS[0].hex);
	hydrated = $state<boolean>(false);

	init(): void {
		if (typeof window === 'undefined' || this.hydrated) return;

		let storedId = localStorage.getItem(STORAGE_KEY_ID);
		if (!storedId) {
			storedId = generateRandomId();
			localStorage.setItem(STORAGE_KEY_ID, storedId);
		}
		this.playerId = storedId;

		let storedName = localStorage.getItem(STORAGE_KEY_NAME);
		if (!storedName) {
			storedName = generateDefaultName();
			localStorage.setItem(STORAGE_KEY_NAME, storedName);
		}
		this.name = storedName;

		let storedColor = localStorage.getItem(STORAGE_KEY_COLOR);
		if (!storedColor) {
			storedColor = PRESET_PLAYER_COLORS[0].hex;
			localStorage.setItem(STORAGE_KEY_COLOR, storedColor);
		}
		this.primaryColor = storedColor;
		this.hydrated = true;
	}

	setName(newName: string): void {
		const trimmed = newName.trim().slice(0, 32);
		this.name = trimmed || 'Player';
		if (typeof window !== 'undefined') {
			localStorage.setItem(STORAGE_KEY_NAME, this.name);
		}
	}

	setColor(newColor: string): void {
		this.primaryColor = newColor;
		if (typeof window !== 'undefined') {
			localStorage.setItem(STORAGE_KEY_COLOR, newColor);
		}
	}
}

export const profile = new ProfileStore();
