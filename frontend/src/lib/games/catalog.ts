/** Shared frontend game catalog for hubs, SEO, and the landing page. */

export type GameSlug =
	| 'sudoku'
	| 'kaesekaestchen'
	| 'minesweeper'
	| 'silbenstreit'
	| 'emoji-charades'
	| 'spellsprawl'
	| 'north-south-sort'
	| 'fragmentory';

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
			'A 1–4 player word strategy on a 4×4 to 8×8 letter grid. Form valid words in German, English, French, or Spanish to claim letters, score rarity points, and surround your tiles so they cannot be stolen. Play solo to fill the board on your own: reusing your own protected letters costs their points.',
		playersLabel: '1–4',
		playersAria: '1 to 4 players',
		boxSeed: 39,
		defaultConfig: { size: 5, language: 'de', scoring_enabled: true, solo: false },
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
			show_category: true,
			scoring_enabled: true
		},
		createLabel: 'New Emoji Charades →'
	},
	{
		slug: 'spellsprawl',
		title: 'Spellsprawl',
		tagline: 'Spell words on an endless grid — only reused letters score.',
		description:
			'A 1–8 player word game on an infinite grid. Type words across or down anywhere, Scrabble-style, in German, English, French, or Spanish. New letters score nothing: only letters already on the grid count, so weave your words through rare letters. Play to 50 words, 500 points, or until the grid sprawls past 500 cells.',
		playersLabel: '1–8',
		playersAria: '1 to 8 players',
		boxSeed: 51,
		defaultConfig: { language: 'de', end_condition: 'words', end_target: 50 },
		createLabel: 'New Spellsprawl →'
	},
	{
		slug: 'north-south-sort',
		title: 'North South Sort',
		tagline: 'Is it further north or south? Sort cities, sights and history on one axis.',
		description:
			'A 1–8 player geography game. Take turns placing cities, landmarks and historical events north or south of the locations already on a shared axis. The tighter the gap you squeeze a card into, the more it scores — landmarks count double, events triple. Wrong guesses cost points and vanish until the end. Play the whole world or a single continent, with an optional speed bonus.',
		playersLabel: '1–8',
		playersAria: '1 to 8 players',
		boxSeed: 57,
		defaultConfig: {
			language: 'de',
			continent: 'world',
			difficulty: 'medium',
			categories: ['city', 'landmark', 'event'],
			timed: false,
			end_condition: 'rounds',
			end_target: 10
		},
		createLabel: 'New North South Sort →'
	},
	{
		slug: 'fragmentory',
		title: 'Fragmentory',
		tagline: 'Place line cards, claim areas, and grow the biggest territory.',
		description:
			'A turn-based territory game for 1–8 players. Rotate square cards with straight, curved, crossing and T-shaped lines so every edge matches, claim an area in your color, and let neighbouring areas merge into big territories. Bigger colors swallow smaller ones, ties turn gray, enclosed areas score double — but every row or column the board grows costs points.',
		playersLabel: '1–8',
		playersAria: '1 to 8 players',
		boxSeed: 63,
		defaultConfig: {},
		createLabel: 'New Fragmentory →'
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
