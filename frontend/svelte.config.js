import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({
			// Keep prerendered index.html / {slug}.html; SPA rooms use 200.html
			fallback: '200.html',
			precompress: false
		})
	}
};

export default config;
