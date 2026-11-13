import { defineConfig, devices } from '@playwright/test';

// E2E runs its own backend (fixed mode: deterministic boards, host opens) and Vite dev server
// on separate ports, so it never reuses a `make dev` server. Postgres must be up (`make e2e`).
const BACKEND_PORT = process.env.E2E_BACKEND_PORT ?? '8100';
const FRONTEND_PORT = process.env.E2E_FRONTEND_PORT ?? '5180';
const baseURL = `http://localhost:${FRONTEND_PORT}`;

export default defineConfig({
	testDir: './e2e',
	timeout: 60_000,
	expect: { timeout: 10_000 },
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	reporter: process.env.CI ? 'github' : 'list',
	use: {
		baseURL,
		trace: 'retain-on-failure'
	},
	projects: [{ name: 'mobile-chrome', use: { ...devices['Pixel 7'] } }],
	webServer: [
		{
			command: `uv run uvicorn games_platform.main:app --port ${BACKEND_PORT}`,
			cwd: '../backend',
			env: { GAMES_E2E_FIXED: '1' },
			url: `http://localhost:${BACKEND_PORT}/api/games`,
			reuseExistingServer: false,
			timeout: 60_000
		},
		{
			command: `pnpm exec vite dev --port ${FRONTEND_PORT} --strictPort`,
			env: { BACKEND_PORT },
			url: baseURL,
			reuseExistingServer: false,
			timeout: 60_000
		}
	]
});
