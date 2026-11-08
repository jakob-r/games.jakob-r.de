<script lang="ts" module>
	export interface MapCard {
		id: string;
		category: 'city' | 'landmark' | 'event';
		name: string;
		country?: string;
		lat?: number;
		lon?: number;
		description?: string;
		wikipedia?: string;
		player_id?: string | null;
	}
</script>

<script lang="ts">
	import { geoEquirectangular, geoGraticule10, geoPath, type GeoPermissibleObjects } from 'd3-geo';

	let {
		placed,
		missed,
		playerColor,
		playerName,
		categoryLabel
	}: {
		placed: MapCard[];
		missed: MapCard[];
		playerColor: (playerId: string) => string;
		playerName: (playerId: string | null | undefined) => string;
		categoryLabel: (category: MapCard['category']) => { label: string; color: string };
	} = $props();

	const WIDTH = 600;
	const PAD_DEG = 12;

	type Point = { card: MapCard; correct: boolean; key: string };

	let land = $state<GeoPermissibleObjects | null>(null);
	let selectedKey = $state<string | null>(null);

	let points = $derived<Point[]>([
		...placed
			.filter((c) => c.lat !== undefined && c.lon !== undefined)
			.map((card) => ({ card, correct: true, key: `p${card.id}` })),
		...missed
			.filter((c) => c.lat !== undefined && c.lon !== undefined)
			.map((card) => ({ card, correct: false, key: `m${card.id}` }))
	]);

	// Frame the played locations (padded), but never zoom in further than ~40°×25°.
	let bounds = $derived.by(() => {
		const lats = points.map((p) => p.card.lat!);
		const lons = points.map((p) => p.card.lon!);
		if (lats.length === 0) return { w: -180, e: 180, s: -60, n: 80 };
		let w = Math.min(...lons) - PAD_DEG;
		let e = Math.max(...lons) + PAD_DEG;
		let s = Math.min(...lats) - PAD_DEG;
		let n = Math.max(...lats) + PAD_DEG;
		const widen = (lo: number, hi: number, min: number) => {
			const extra = Math.max(0, min - (hi - lo)) / 2;
			return [lo - extra, hi + extra];
		};
		[w, e] = widen(w, e, 40);
		[s, n] = widen(s, n, 25);
		return {
			w: Math.max(-180, w),
			e: Math.min(180, e),
			s: Math.max(-85, s),
			n: Math.min(85, n)
		};
	});

	let height = $derived(
		Math.round(
			Math.min(WIDTH * 0.9, Math.max(WIDTH * 0.35, (WIDTH * (bounds.n - bounds.s)) / (bounds.e - bounds.w)))
		)
	);

	let projection = $derived.by(() => {
		// Corner points, not a polygon: on the sphere a polygon's winding decides which side
		// is "inside", and in this projection the corners' bounding box is the rectangle.
		const frame = {
			type: 'MultiPoint',
			coordinates: [
				[bounds.w, bounds.s],
				[bounds.w, bounds.n],
				[bounds.e, bounds.n],
				[bounds.e, bounds.s]
			]
		};
		return (
			geoEquirectangular()
				.fitExtent(
					[
						[4, 4],
						[WIDTH - 4, height - 4]
					],
					frame as unknown as GeoPermissibleObjects
				)
				// Clip paths to the visible map. Unclipped, a zoomed-in land path spans tens of
				// thousands of pixels and the scribble filter (sized to the path's bounding box)
				// rasterises it at low resolution: blurry coastlines without outlines.
				.clipExtent([
					[0, 0],
					[WIDTH, height]
				])
		);
	});

	let path = $derived(geoPath(projection));
	let landPath = $derived(land ? (path(land) ?? '') : '');
	let gridPath = $derived(path(geoGraticule10()) ?? '');
	let equatorY = $derived(projection([0, 0])?.[1] ?? null);

	let projected = $derived(
		points
			.map((p) => {
				const xy = projection([p.card.lon!, p.card.lat!]);
				return xy ? { ...p, x: xy[0], y: xy[1] } : null;
			})
			.filter((p): p is Point & { x: number; y: number } => p !== null)
			// Selected point last so it draws on top.
			.sort((a, b) => Number(a.key === selectedKey) - Number(b.key === selectedKey))
	);

	let selected = $derived(points.find((p) => p.key === selectedKey) ?? null);

	function formatLat(lat: number | undefined): string {
		if (lat === undefined) return '';
		return `${Math.abs(lat).toFixed(1)}° ${lat >= 0 ? 'N' : 'S'}`;
	}

	function select(key: string) {
		selectedKey = key;
	}

	function onKey(e: KeyboardEvent, key: string) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			select(key);
		}
	}

	// Zoomed-in maps (a single continent) get the finer coastline; it is only fetched then.
	let detailed = $derived(bounds.e - bounds.w < 100);

	$effect(() => {
		let cancelled = false;
		const atlasImport = detailed
			? import('world-atlas/land-50m.json')
			: import('world-atlas/land-110m.json');
		Promise.all([import('topojson-client'), atlasImport]).then(
			([topojson, atlas]) => {
				if (cancelled) return;
				const topo = ('default' in atlas ? atlas.default : atlas) as unknown as Parameters<
					typeof topojson.feature
				>[0] & { objects: { land: Parameters<typeof topojson.feature>[1] } };
				land = topojson.feature(topo, topo.objects.land) as unknown as GeoPermissibleObjects;
			}
		);
		return () => {
			cancelled = true;
		};
	});
</script>

<div class="border-[2px] border-[#1a1917] bg-[#faf8f4]">
	<svg
		viewBox="0 0 {WIDTH} {height}"
		class="block h-auto w-full touch-manipulation"
		role="group"
		aria-label="Map of all played locations"
	>
		<path d={gridPath} fill="none" stroke="#1a1917" stroke-opacity="0.06" stroke-width="0.8" />
		{#if equatorY !== null && equatorY > 0 && equatorY < height}
			<line
				x1="0"
				x2={WIDTH}
				y1={equatorY}
				y2={equatorY}
				stroke="#1a1917"
				stroke-opacity="0.25"
				stroke-dasharray="4 4"
			/>
		{/if}
		<path
			d={landPath}
			fill="#1a1917"
			fill-opacity="0.07"
			stroke="#1a1917"
			stroke-opacity="0.55"
			stroke-width="1"
			stroke-linejoin="round"
			filter="url(#scribble-filter)"
		/>
		{#each projected as p (p.key)}
			{@const isSel = p.key === selectedKey}
			<!-- svelte-ignore a11y_mouse_events_have_key_events -->
			<g
				role="button"
				tabindex="0"
				aria-label="{p.card.name}{p.correct ? '' : ' (misplaced)'}"
				aria-pressed={isSel}
				class="map-point cursor-pointer outline-none"
				transform="translate({p.x} {p.y})"
				onmouseenter={() => select(p.key)}
				onclick={() => select(p.key)}
				onfocus={() => select(p.key)}
				onkeydown={(e) => onKey(e, p.key)}
			>
				<!-- Generous invisible hit area for touch -->
				<circle r="11" fill="transparent" />
				{#if p.correct}
					<circle
						r={isSel ? 7 : 5}
						fill={p.card.player_id ? playerColor(p.card.player_id) : '#faf8f4'}
						stroke="#1a1917"
						stroke-width="1.5"
					/>
				{:else}
					<g stroke="#b5523b" stroke-width={isSel ? 3.4 : 2.6} stroke-linecap="round">
						<path d="M-{isSel ? 6 : 4.5} -{isSel ? 6 : 4.5}L{isSel ? 6 : 4.5} {isSel ? 6 : 4.5}M{isSel ? 6 : 4.5} -{isSel ? 6 : 4.5}L-{isSel ? 6 : 4.5} {isSel ? 6 : 4.5}" />
					</g>
				{/if}
				{#if isSel}
					<circle r="12" fill="none" stroke="#1a1917" stroke-width="1" stroke-dasharray="2 2" />
				{/if}
			</g>
		{/each}
	</svg>
</div>

<div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#6e6a63]">
	<span class="flex items-center gap-1.5">
		<svg width="12" height="12" viewBox="-6 -6 12 12" aria-hidden="true"
			><circle r="4.5" fill="#faf8f4" stroke="#1a1917" stroke-width="1.5" /></svg
		>
		placed (player colour)
	</span>
	<span class="flex items-center gap-1.5">
		<svg width="12" height="12" viewBox="-6 -6 12 12" aria-hidden="true"
			><path d="M-4 -4L4 4M4 -4L-4 4" stroke="#b5523b" stroke-width="2.4" stroke-linecap="round" /></svg
		>
		misplaced
	</span>
	<span>Tap or hover a point.</span>
</div>

<div class="mt-2 min-h-[5.5rem]" aria-live="polite">
	{#if selected}
		{@const card = selected.card}
		{@const cat = categoryLabel(card.category)}
		<div
			class="rounded border-[1.5px] bg-white/80 px-3 py-2
			{selected.correct ? 'border-[#1a1917]' : 'border-[#b5523b]'}"
		>
			<div class="flex items-baseline gap-2">
				<span class="font-semibold">{card.name}</span>
				<span class="text-[10px] font-semibold uppercase" style="color: {cat.color}">{cat.label}</span>
				<span class="font-mono-num ml-auto shrink-0 text-sm">{formatLat(card.lat)}</span>
			</div>
			<div class="text-xs text-[#6e6a63]">
				{card.country ? `${card.country} · ` : ''}{card.description}
			</div>
			<div class="mt-1 flex items-center gap-2 text-xs">
				{#if selected.correct}
					{#if card.player_id}
						<span class="text-[#4f8a4b]">✓ placed by {playerName(card.player_id)}</span>
					{:else}
						<span class="text-[#6e6a63]">start card</span>
					{/if}
				{:else}
					<span class="text-[#b5523b]">✗ misplaced by {playerName(card.player_id)}</span>
				{/if}
				{#if card.wikipedia}
					<a href={card.wikipedia} target="_blank" rel="noopener" class="ml-auto underline">
						Wikipedia
					</a>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.map-point:focus-visible circle:nth-child(2) {
		stroke-width: 2.5;
	}
</style>
