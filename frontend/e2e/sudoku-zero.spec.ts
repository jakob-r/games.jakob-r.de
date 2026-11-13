import { expect, test, type Page } from '@playwright/test';
import { createRoom, newPlayer } from './helpers';

test('solo: place a clue, see the counter, give up', async ({ browser }) => {
	const a = await newPlayer(browser, 'Alice');
	await createRoom(a, 'sudoku-zero', 'New Sudoku Zero →');

	await a.getByTestId('zero-solo-toggle').click();
	await expect(a.getByTestId('zero-solo-toggle')).toHaveAttribute('aria-pressed', 'true');
	await a.getByRole('button', { name: 'Start Game →' }).click();
	await expect(a.getByRole('grid', { name: 'Sudoku Zero board' })).toBeVisible();
	await expect(a.getByTestId('zero-solutions')).toHaveText('1000+');

	await a.getByRole('button', { name: 'Row 1 Column 1', exact: true }).click();
	await a.getByRole('button', { name: 'Number 5' }).click();
	await a.getByTestId('zero-place').click();
	await expect(a.getByRole('button', { name: 'Row 1 Column 1, 5' })).toBeVisible();
	await expect(a.getByTestId('zero-counter')).toContainText('1 clue');

	// A second 5 in the same row is not offered.
	await a.getByRole('button', { name: 'Row 1 Column 2', exact: true }).click();
	await expect(a.getByRole('button', { name: 'Number 5' })).toBeDisabled();

	await a.getByTestId('zero-pass').click();
	await a.getByTestId('zero-pass').click();
	await expect(a.getByTestId('zero-finished')).toContainText('Stopped at 1 clue');
});

async function placeClue(page: Page, row: number, col: number, value: number): Promise<void> {
	await page.getByRole('button', { name: `Row ${row} Column ${col}`, exact: true }).click();
	await page.getByRole('button', { name: `Number ${value}` }).click();
	await page.getByTestId('zero-place').click();
	await expect(
		page.getByRole('button', { name: `Row ${row} Column ${col}, ${value}` })
	).toBeVisible();
}

test('solo: a clue without a solution ends the round with −50', async ({ browser }) => {
	const a = await newPlayer(browser, 'Alice');
	await createRoom(a, 'sudoku-zero', 'New Sudoku Zero →');
	await a.getByTestId('zero-solo-toggle').click();
	await expect(a.getByTestId('zero-solo-toggle')).toHaveAttribute('aria-pressed', 'true');
	await a.getByRole('button', { name: 'Start Game →' }).click();

	// Row 1 gets 1–8, so its last cell must be 9 — a 9 in column 9 leaves no solution.
	for (let col = 1; col <= 8; col++) await placeClue(a, 1, col, col);
	await a.getByRole('button', { name: 'Row 5 Column 9', exact: true }).click();
	await a.getByRole('button', { name: 'Number 9' }).click();
	await a.getByTestId('zero-place').click();
	await expect(a.getByTestId('zero-finished')).toContainText('left no solution');
});

test('two players: turns alternate, two passes end the round', async ({ browser }) => {
	const a = await newPlayer(browser, 'Alice');
	const b = await newPlayer(browser, 'Bob');
	const url = await createRoom(a, 'sudoku-zero', 'New Sudoku Zero →');
	await b.goto(url);
	await expect(a.getByText('Players (2)')).toBeVisible();
	await a.getByRole('button', { name: 'Ready', exact: true }).click();
	await b.getByRole('button', { name: 'Ready', exact: true }).click();
	await expect(a.getByText('2/2 ready')).toBeVisible();
	await a.getByRole('button', { name: 'Start Game →' }).click();

	await expect(b.getByText('Waiting for Alice…')).toBeVisible();
	await placeClue(a, 1, 1, 5);
	await expect(b.getByRole('button', { name: 'Row 1 Column 1, 5' })).toBeVisible();
	await expect(a.getByText('Waiting for Bob…')).toBeVisible();

	await b.getByTestId('zero-pass').click();
	await expect(a.getByText('Bob passed — passing now ends the round.')).toBeVisible();
	await a.getByTestId('zero-pass').click();
	await expect(a.getByTestId('zero-finished')).toContainText('Both players passed');
	await expect(b.getByTestId('zero-finished')).toContainText('Alice wins');
});
