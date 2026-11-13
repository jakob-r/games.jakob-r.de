import { expect, type Browser, type Page } from '@playwright/test';

/** A player in their own browser context (own localStorage, so own player id). */
export async function newPlayer(browser: Browser, name: string): Promise<Page> {
	const context = await browser.newContext();
	// A stored name skips the "What's your name?" prompt.
	await context.addInitScript((n) => {
		localStorage.setItem('games_jakob_player_name', n);
	}, name);
	return context.newPage();
}

/** Create a room from the game hub and return its URL. */
export async function createRoom(page: Page, slug: string, createLabel: string): Promise<string> {
	await page.goto(`/${slug}`);
	// The hub is prerendered: a click before hydration does nothing, so retry until we navigate.
	const roomUrl = new RegExp(`/${slug}/[^/]+$`);
	await expect(async () => {
		await page.getByRole('button', { name: createLabel }).click();
		await expect(page).toHaveURL(roomUrl, { timeout: 5_000 });
	}).toPass({ timeout: 30_000 });
	await expect(page.getByRole('button', { name: 'Start Game →' })).toBeVisible();
	return page.url();
}
