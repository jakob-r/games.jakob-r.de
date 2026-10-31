/** Shared frontend game catalog for hubs, SEO, and the landing page. */

export type GameSlug =
	| 'sudoku'
	| 'kaesekaestchen'
	| 'minesweeper'
	| 'silbenstreit'
	| 'emoji-charades';

export interface GameInfo {
	slug: GameSlug;
	title: string;
	/** One-line blurb for cards and meta description. */
	tagline: string;
	/** Longer copy for the game hub page. */
	description: string;
	playersLabel: string;
	playersAria: string;
	/** Seed for ScribblyBox on the landing/hub. */
	boxSeed: number;
	defaultConfig: Record<string, unknown>;
	createLabel: string;
}

export const SITE_ORIGIN = 'https://games.jakob-r.de';
export const SITE_NAME = 'games.jakob-r.de';

export const GAMES: GameInfo[] = [
	{
		slug: 'sudoku',
		title: 'Multiplayer Sudoku',
		tagline: 'Solve a 9×9 board together in real time.',
		description:
			'Collaborative and competitive 9×9 Sudoku. Share corner notes, race for streak multipliers, and see every teammate’s strokes in their color. Create a room, share the link, and fill the grid together.',
		playersLabel: '1–8',
		playersAria: '1 or more players',
		boxSeed: 19,
		defaultConfig: { difficulty: 'medium', scoring_enabled: true },
		createLabel: 'New Sudoku →'
	},
	{
		slug: 'kaesekaestchen',
		title: 'Käsekästchen',
		tagline: 'Take turns drawing lines — close a square to score and go again.',
		description:
			'Classic Dots & Boxes on a customizable grid. Draw lines in your color, close squares to score a point and earn an extra turn. Shape the board in the lobby, then share the room link with friends.',
		playersLabel: '2+',
		playersAria: '2 or more players',
		boxSeed: 27,
		defaultConfig: { width: 6, height: 6, border_edges: [] },
		createLabel: 'New Käsekästchen →'
	},
	{
		slug: 'minesweeper',
		title: 'Co-op Minesweeper',
		tagline: 'Clear a shared minefield, plant flags, and challenge guesses.',
		description:
			'Clear a shared minefield together. Dig for points, plant flags in your color, and challenge suspect opponent flags. Boom flashes cost points, but the team keeps playing until every mine is secured.',
		playersLabel: '1–8',
		playersAria: '1 or more players',
		boxSeed: 33,
		defaultConfig: { difficulty: 'easy', scoring_enabled: true },
		createLabel: 'New Minesweeper →'
	},
	{
		slug: 'silbenstreit',
		title: 'Silbenstreit',
		tagline: 'Claim letter tiles with words, steal, and protect your territory.',
		description:
			'A 2–4 player word strategy on a 4×4 to 8×8 letter grid. Form valid words in German, English, French, or Spanish to claim letters, score rarity points, and surround your tiles so they cannot be stolen.',
		playersLabel: '2–4',
		playersAria: '2 to 4 players',
		boxSeed: 39,
		defaultConfig: { size: 5, language: 'de', scoring_enabled: true },
		createLabel: 'New Silbenstreit →'
	},
	{
		slug: 'emoji-charades',
		title: 'Emoji Charades',
		tagline: 'Explain words, movies, and quotes using only emojis.',
		description:
			'A party game for the couch or a video call. One player explains a secret word, movie title, or quote with emoji sentences while everyone else guesses — shout it out in person or type it remotely with typo-tolerant matching. Optional timer, German or English words.',
		playersLabel: '2+',
		playersAria: '2 or more players',
		boxSeed: 45,
		defaultConfig: {
			mode: 'in_person',
			timed: false,
			round_seconds: 120,
			language: 'de',
			scoring_enabled: true
		},
		createLabel: 'New Emoji Charades →'
	}
];

const BY_SLUG = Object.fromEntries(GAMES.map((g) => [g.slug, g])) as Record<
	GameSlug,
	GameInfo
>;

export function getGame(slug: string): GameInfo | undefined {
	return BY_SLUG[slug as GameSlug];
}

export function gamePath(slug: GameSlug): string {
	return `/${slug}`;
}

export function roomPath(slug: GameSlug, roomId: string): string {
	return `/${slug}/${roomId}`;
}

export function formatGameTitle(slug: string): string {
	return getGame(slug)?.title ?? slug;
}
