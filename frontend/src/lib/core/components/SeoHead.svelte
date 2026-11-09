<script lang="ts">
	import { SITE_NAME, SITE_ORIGIN } from '#lib/games/catalog.ts';

	let {
		title,
		description,
		path = '/',
		type = 'website',
		jsonLd = null
	}: {
		title: string;
		description: string;
		path?: string;
		type?: 'website' | 'article';
		jsonLd?: Record<string, unknown> | Record<string, unknown>[] | null;
	} = $props();

	const canonical = $derived(
		path.startsWith('http') ? path : `${SITE_ORIGIN}${path.startsWith('/') ? path : `/${path}`}`
	);
	const fullTitle = $derived(
		title.includes(SITE_NAME) ? title : `${title} • ${SITE_NAME}`
	);
	const jsonLdScript = $derived(
		jsonLd ? JSON.stringify(Array.isArray(jsonLd) ? { '@context': 'https://schema.org', '@graph': jsonLd } : { '@context': 'https://schema.org', ...jsonLd }) : null
	);
</script>

<svelte:head>
	<title>{fullTitle}</title>
	<meta name="description" content={description} />
	<link rel="canonical" href={canonical} />

	<meta property="og:type" content={type} />
	<meta property="og:site_name" content={SITE_NAME} />
	<meta property="og:url" content={canonical} />
	<meta property="og:title" content={fullTitle} />
	<meta property="og:description" content={description} />
	<meta property="og:locale" content="en_US" />
	<meta property="og:image" content={`${SITE_ORIGIN}/og.png`} />
	<meta property="og:image:width" content="1200" />
	<meta property="og:image:height" content="630" />

	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content={fullTitle} />
	<meta name="twitter:description" content={description} />

	{#if jsonLdScript}
		{@html `<script type="application/ld+json">${jsonLdScript}</script>`}
	{/if}
</svelte:head>
