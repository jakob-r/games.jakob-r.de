import { expect, test, type Page } from '@playwright/test';
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
