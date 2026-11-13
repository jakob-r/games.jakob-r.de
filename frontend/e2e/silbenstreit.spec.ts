import { expect, test, type Browser, type Page } from '@playwright/test';
import { createRoom, newPlayer } from './helpers';

// The backend runs in E2E fixed mode: 5×5 German boards are always these rows (each a word),
// and the host opens a game started from the lobby.
const ROWS = ['TISCH', 'BLUME', 'KATZE', 'STERN', 'WOLKE'] as const;

async function startGame(page: Page): Promise<void> {
	await page.getByRole('button', { name: 'Start Game →' }).click();
	await expect(page.getByRole('grid', { name: 'Silbenstreit Letter Grid' })).toBeVisible();
}

async function expectMyTurn(page: Page): Promise<void> {
	await expect(page.getByText('Select letters to form a word…')).toBeVisible();
}

async function expectWaiting(page: Page): Promise<void> {
	await expect(page.getByText('Waiting for opponent…')).toBeVisible();
}

/** Play the word in board row `row` (0-based) by tapping its tiles left to right. */
async function playRow(page: Page, row: number, playedSoFar: number): Promise<void> {
	await expectMyTurn(page);
	const word = ROWS[row];
	for (let col = 0; col < word.length; col++) {
		await page
			.getByRole('button', { name: new RegExp(`^Row ${row + 1} Column ${col + 1}: ${word[col]} `) })
			.click();
	}
	await page.getByRole('button', { name: 'Submit Word' }).click();
	await expectPlayed(page, playedSoFar + 1, word);
}

async function expectPlayed(page: Page, count: number, lastWord: string): Promise<void> {
	await expect(page.getByText(`Played Words (${count})`)).toBeVisible();
	await expect(page.getByText(lastWord, { exact: true })).toBeVisible();
}

test('single player: start alone and play two words', async ({ browser }) => {
	const a = await newPlayer(browser, 'Alice');
	await createRoom(a, 'silbenstreit', 'New Silbenstreit →');
	await startGame(a);

	await playRow(a, 0, 0);
	await playRow(a, 1, 1);
});

test('multiplayer from the lobby: both ready, host starts, two words each', async ({ browser }) => {
	const a = await newPlayer(browser, 'Alice');
	const b = await newPlayer(browser, 'Bob');
	const url = await createRoom(a, 'silbenstreit', 'New Silbenstreit →');

	await b.goto(url);
	await expect(a.getByText('Players (2)')).toBeVisible();
	await expect(b.getByText('Waiting for host…')).toBeVisible();

	await a.getByRole('button', { name: 'Ready', exact: true }).click();
	await b.getByRole('button', { name: 'Ready', exact: true }).click();
	await expect(a.getByText('2/2 ready')).toBeVisible();
	await expect(b.getByText('2/2 ready')).toBeVisible();

	await startGame(a);
	await expect(b.getByRole('grid', { name: 'Silbenstreit Letter Grid' })).toBeVisible();
	await expectWaiting(b);

	await playRow(a, 0, 0);
	await expectPlayed(b, 1, ROWS[0]);
	await playRow(b, 1, 1);
	await expectPlayed(a, 2, ROWS[1]);
	await playRow(a, 2, 2);
	await expectPlayed(b, 3, ROWS[2]);
	await playRow(b, 3, 3);
	await expectPlayed(a, 4, ROWS[3]);
	await expectWaiting(b);
});

test('joining a game started alone before any move: the host keeps the opening move', async ({
	browser
}) => {
	const a = await newPlayer(browser, 'Alice');
	const b = await newPlayer(browser, 'Bob');
	const url = await createRoom(a, 'silbenstreit', 'New Silbenstreit →');
	await startGame(a);

	// The joiner only takes the turn once the solo player has moved.
	await b.goto(url);
	await expectWaiting(b);

	await playRow(a, 0, 0);
	await expectPlayed(b, 1, ROWS[0]);
	await playRow(b, 1, 1);
	await expectPlayed(a, 2, ROWS[1]);
	await playRow(a, 2, 2);
	await expectPlayed(b, 3, ROWS[2]);
	await playRow(b, 3, 3);
	await expectPlayed(a, 4, ROWS[3]);
});

test('joining after the host already moved: the joiner takes the turn', async ({
	browser
}) => {
	const a = await newPlayer(browser, 'Alice');
	const b = await newPlayer(browser, 'Bob');
	const url = await createRoom(a, 'silbenstreit', 'New Silbenstreit →');
	await startGame(a);
	await playRow(a, 0, 0);

	await b.goto(url);
	await expectPlayed(b, 1, ROWS[0]);
	await expectWaiting(a);

	await playRow(b, 1, 1);
	await expectPlayed(a, 2, ROWS[1]);
	await playRow(a, 2, 2);
	await expectPlayed(b, 3, ROWS[2]);
	await playRow(b, 3, 3);
	await expectPlayed(a, 4, ROWS[3]);
});

/** Tile button at 0-based `row`/`col`. */
function tile(page: Page, row: number, col: number) {
	return page.getByRole('button', { name: new RegExp(`^Row ${row + 1} Column ${col + 1}: `) });
}

/** A and B in a lobby game that A (host) has started; A has the turn. */
async function startTwoPlayerGame(browser: Browser): Promise<{ a: Page; b: Page; url: string }> {
	const a = await newPlayer(browser, 'Alice');
	const b = await newPlayer(browser, 'Bob');
	const url = await createRoom(a, 'silbenstreit', 'New Silbenstreit →');
	await b.goto(url);
	await expect(a.getByText('Players (2)')).toBeVisible();
	await startGame(a);
	await expect(b.getByRole('grid', { name: 'Silbenstreit Letter Grid' })).toBeVisible();
	return { a, b, url };
}

test('full game: claiming every tile ends it and shows the winner', async ({ browser }) => {
	const { a, b } = await startTwoPlayerGame(browser);

	// TISCH 9 + KATZE 10 + WOLKE 12 = 31 for Alice; BLUME 10 + STERN 5 = 15 for Bob.
	for (let row = 0; row < ROWS.length; row++) {
		await playRow(row % 2 === 0 ? a : b, row, row);
	}

	for (const page of [a, b]) {
		await expect(page.getByText('Alice wins (31 pts)!')).toBeVisible();
		await expect(page.getByText('0 open')).toBeVisible();
		await expect(page.getByRole('button', { name: 'Submit Word' })).toHaveCount(0);
	}
	await expect(b.getByText('Waiting for the host to start a new round…')).toBeVisible();
});

test('new round: the host returns everyone to the lobby and starts again', async ({ browser }) => {
	const { a, b } = await startTwoPlayerGame(browser);
	for (let row = 0; row < ROWS.length; row++) {
		await playRow(row % 2 === 0 ? a : b, row, row);
	}
	await expect(a.getByText('Alice wins (31 pts)!')).toBeVisible();

	await a.getByRole('button', { name: 'New Round' }).click();
	await expect(a.getByRole('button', { name: 'Start Game →' })).toBeVisible();
	await expect(b.getByText('Waiting for host…')).toBeVisible();

	await startGame(a);
	await expect(b.getByRole('grid', { name: 'Silbenstreit Letter Grid' })).toBeVisible();
	await expect(a.getByText('25 open')).toBeVisible();
	await expect(a.getByText(/Played Words/)).toHaveCount(0);
	await playRow(a, 0, 0);
	await expectPlayed(b, 1, ROWS[0]);
});

test('protected tiles: a fully surrounded row cannot be taken by the opponent', async ({
	browser
}) => {
	const { a, b } = await startTwoPlayerGame(browser);
	await playRow(a, 0, 0);
	await playRow(b, 3, 1);
	// Alice owns the top two rows, so every top-row tile has only Alice's neighbours.
	await playRow(a, 1, 2);
	await expectMyTurn(b);

	for (let col = 0; col < 5; col++) {
		await expect(tile(b, 0, col)).toBeDisabled();
		await expect(tile(b, 1, col)).toBeEnabled();
	}
	await tile(b, 0, 0).click({ force: true });
	await expect(b.getByText('Select letters to form a word…')).toBeVisible();
});

test('reload and resume: the game survives a reload and is listed on the hub', async ({
	browser
}) => {
	const a = await newPlayer(browser, 'Alice');
	const url = await createRoom(a, 'silbenstreit', 'New Silbenstreit →');
	const roomId = url.split('/').pop() ?? '';
	await startGame(a);
	await playRow(a, 0, 0);

	await a.reload();
	await expectPlayed(a, 1, ROWS[0]);
	await expect(a.getByText('20 open')).toBeVisible();
	await expectMyTurn(a);

	await a.goto('/silbenstreit');
	await expect(a.getByText(`#${roomId}`)).toBeVisible();
	await a.getByRole('link', { name: 'Resume →' }).click();
	await expect(a).toHaveURL(url);
	await expectPlayed(a, 1, ROWS[0]);
	await playRow(a, 1, 1);
});

test('composing: points, removing a letter and clearing the word', async ({ browser }) => {
	const a = await newPlayer(browser, 'Alice');
	await createRoom(a, 'silbenstreit', 'New Silbenstreit →');
	await startGame(a);
	const composer = a.getByRole('list', { name: /Selected word letters/ });

	// T I S C H are worth 1 1 1 4 2.
	await tile(a, 0, 0).click();
	await tile(a, 0, 1).click();
	await tile(a, 0, 3).click();
	await expect(a.getByText('6 pts')).toBeVisible();
	await expect(a.getByRole('button', { name: 'Pass Turn' })).toBeDisabled();

	await composer.getByRole('button', { name: 'C', exact: true }).click();
	await expect(a.getByText('2 pts')).toBeVisible();
	await expect(composer.getByRole('button')).toHaveCount(2);

	await a.getByRole('button', { name: 'Clear' }).click();
	await expect(composer).toHaveCount(0);
	await expectMyTurn(a);
	await expect(a.getByRole('button', { name: 'Submit Word' })).toBeDisabled();

	await playRow(a, 0, 0);
});

test('passing: the turn moves on and four passes in a row end the game', async ({ browser }) => {
	const { a, b } = await startTwoPlayerGame(browser);

	for (const [actor, other] of [
		[a, b],
		[b, a],
		[a, b],
		[b, a]
	] as const) {
		await expectMyTurn(actor);
		await actor.getByRole('button', { name: 'Pass Turn' }).click();
		if (actor === a) await expectMyTurn(other);
	}

	for (const page of [a, b]) {
		await expect(page.getByText("It's a tie! (Alice & Bob — 0 pts)")).toBeVisible();
	}
});

test('lobby settings: the host changes them and the guest sees them live', async ({
	browser
}) => {
	const a = await newPlayer(browser, 'Alice');
	const b = await newPlayer(browser, 'Bob');
	const url = await createRoom(a, 'silbenstreit', 'New Silbenstreit →');
	await b.goto(url);
	await expect(b.getByText('Configured by host')).toBeVisible();

	await a.getByRole('button', { name: '6×6' }).click();
	await a.getByRole('button', { name: 'English' }).click();
	await a.getByRole('button', { name: 'Enabled' }).click();

	await expect(b.getByText('Board Size (6×6)')).toBeVisible();
	await expect(b.getByText('EN', { exact: true })).toBeVisible();
	await expect(b.getByRole('button', { name: 'Off' })).toBeVisible();
	for (const name of ['4×4', '8×8', 'Deutsch', 'Off']) {
		await expect(b.getByRole('button', { name })).toBeDisabled();
	}

	await startGame(a);
	// English 6×6 boards are random, so only the shape is checked.
	await expect(b.getByRole('button', { name: /^Row \d+ Column \d+: / })).toHaveCount(36);
	await expect(b.getByText('36 open')).toBeVisible();
});

test('rejected words: unknown words and parts of played words are refused', async ({
	browser
}) => {
	const a = await newPlayer(browser, 'Alice');
	await createRoom(a, 'silbenstreit', 'New Silbenstreit →');
	await startGame(a);

	// W O L K E tapped as L O W K E.
	for (const col of [2, 1, 0, 3, 4]) await tile(a, 4, col).click();
	await a.getByRole('button', { name: 'Submit Word' }).click();
	await expect(a.getByText(/"LOWKE" is not in the .* dictionary\./)).toBeVisible();
	await expect(a.getByText(/Played Words/)).toHaveCount(0);
	await a.getByRole('button', { name: 'Clear' }).click();

	await playRow(a, 0, 0);
	for (const col of [0, 1, 2]) await tile(a, 0, col).click();
	await expect(a.getByText('"TIS" is part of the played word "TISCH".')).toBeVisible();
	await expect(a.getByRole('button', { name: 'Submit Word' })).toBeDisabled();
});

test('solo: the game is full, nobody can join, ending the game shows the score', async ({ browser }) => {
	const a = await newPlayer(browser, 'Alice');
	const url = await createRoom(a, 'silbenstreit', 'New Silbenstreit →');
	await a.getByTestId('silben-solo-toggle').click();
	await expect(a.getByTestId('silben-solo-toggle')).toHaveText('On');

	const b = await newPlayer(browser, 'Bob');
	await b.goto(url);
	await expect(b.getByText('This game is full. It cannot be joined.')).toBeVisible();
	await expect(a.getByText('Players (1)')).toBeVisible();

	await startGame(a);
	await playRow(a, 0, 0);
	await playRow(a, 1, 1);
	await a.getByRole('button', { name: 'End Game' }).click();
	await expect(a.getByText(/Game over! You scored \d+ pts\./)).toBeVisible();
});
