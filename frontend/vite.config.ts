import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
	// `make dev` passes BACKEND_PORT, so a second server can run on other ports.
	const backendPort = loadEnv(mode, '.', '').BACKEND_PORT || '8000';
	return {
		plugins: [
			tailwindcss(),
			sveltekit({
				preprocess: vitePreprocess(),
				adapter: adapter({
					// Keep prerendered index.html / {slug}.html; SPA rooms use 200.html
					fallback: '200.html',
					precompress: false
				})
			})
		],
		server: {
			port: 5173,
			proxy: {
				'/api': {
					target: `http://localhost:${backendPort}`,
					changeOrigin: true
				},
				'/ws': {
					target: `ws://localhost:${backendPort}`,
					ws: true
				}
			}
		}
	};
});
