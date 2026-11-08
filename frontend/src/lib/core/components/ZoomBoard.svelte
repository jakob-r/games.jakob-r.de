<script lang="ts">
	/**
	 * Shared scrollable + zoomable board canvas (Spellsprawl, Fragmentory).
	 *
	 * - One finger / wheel scrolls (scrollbars hidden), two fingers pinch-zoom around their
	 *   midpoint, Ctrl/⌘ + wheel (trackpad pinch) zooms around the pointer, +/− buttons zoom
	 *   around the centre. Zoom changes `cellSize`; the content sizes itself from it.
	 * - The canvas is as tall as the screen allows: from its top down to the bottom of the
	 *   window minus `reserveBelow` (e.g. an action panel below it, including the gap) and the
 *   bottom padding of the surrounding containers, but at least `minHeight`.
	 */
	import { onMount, tick, type Snippet } from 'svelte';

	let {
		cellSize = $bindable(),
		minCell,
		maxCell,
		el = $bindable(null),
		viewW = $bindable(0),
		viewH = $bindable(0),
		originX = 0,
		originY = 0,
		reserveBelow = 0,
		minHeight = 260,
		ariaLabel = 'Board',
		children,
		overlay
	}: {
		cellSize: number;
		minCell: number;
		maxCell: number;
		el?: HTMLDivElement | null;
		viewW?: number;
		viewH?: number;
		/** Grid cell shown at the content's top-left (it may move while zooming). */
		originX?: number;
		originY?: number;
		reserveBelow?: number;
		minHeight?: number;
		ariaLabel?: string;
		children: Snippet;
		overlay?: Snippet;
	} = $props();

	let outer = $state<HTMLDivElement | null>(null);
	let height = $state(400);

	const clamp = (v: number) => Math.max(minCell, Math.min(maxCell, v));

	/** Zoom to `next` keeping the content point under (px, py) (relative to the viewport) fixed. */
	function zoomAt(next: number, px: number, py: number, panX = px, panY = py) {
		const box = el;
		if (!box) return;
		const before = cellSize;
		const size = clamp(next);
		const cx = (box.scrollLeft + px) / before + originX;
		const cy = (box.scrollTop + py) / before + originY;
		cellSize = size;
		tick().then(() => {
			box.scrollLeft = (cx - originX) * size - panX;
			box.scrollTop = (cy - originY) * size - panY;
		});
	}

	function zoomButton(factor: number) {
		if (!el) return;
		zoomAt(cellSize * factor, el.clientWidth / 2, el.clientHeight / 2);
	}

	function measure() {
		if (!outer) return;
		const top = outer.getBoundingClientRect().top + window.scrollY;
		// The board's own border.
		const frame = outer.offsetHeight - (el?.offsetHeight ?? outer.offsetHeight);
		// Bottom padding/borders of the containers around the board also take screen space.
		let trailing = 0;
		for (let node = outer.parentElement; node && node !== document.body; node = node.parentElement) {
			const cs = getComputedStyle(node);
			trailing += parseFloat(cs.paddingBottom) + parseFloat(cs.borderBottomWidth);
		}
		const next = Math.max(
			minHeight,
			Math.floor(window.innerHeight - top - reserveBelow - trailing - frame)
		);
		if (Math.abs(next - height) > 1) height = next;
	}

	$effect(() => {
		void reserveBelow;
		measure();
	});

	onMount(() => {
		measure();
		const ro = new ResizeObserver(() => measure());
		ro.observe(document.body);
		window.addEventListener('resize', measure);
		return () => {
			ro.disconnect();
			window.removeEventListener('resize', measure);
		};
	});

	// Pinch and Ctrl+wheel need non-passive listeners to stop the browser from zooming the page.
	$effect(() => {
		const box = el;
		if (!box) return;
		let pinch: { dist: number; size: number; cx: number; cy: number } | null = null;

		const local = (t1: Touch, t2: Touch) => {
			const rect = box.getBoundingClientRect();
			return {
				x: (t1.clientX + t2.clientX) / 2 - rect.left,
				y: (t1.clientY + t2.clientY) / 2 - rect.top,
				dist: Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY)
			};
		};

		const onTouchStart = (e: TouchEvent) => {
			if (e.touches.length !== 2) return;
			const m = local(e.touches[0], e.touches[1]);
			pinch = {
				dist: Math.max(1, m.dist),
				size: cellSize,
				cx: (box.scrollLeft + m.x) / cellSize + originX,
				cy: (box.scrollTop + m.y) / cellSize + originY
			};
		};
		const onTouchMove = (e: TouchEvent) => {
			if (!pinch || e.touches.length !== 2) return;
			e.preventDefault();
			const m = local(e.touches[0], e.touches[1]);
			const size = clamp((pinch.size * m.dist) / pinch.dist);
			const anchor = pinch;
			cellSize = size;
			tick().then(() => {
				box.scrollLeft = (anchor.cx - originX) * size - m.x;
				box.scrollTop = (anchor.cy - originY) * size - m.y;
			});
		};
		const onTouchEnd = (e: TouchEvent) => {
			if (e.touches.length < 2) pinch = null;
		};
		const onWheel = (e: WheelEvent) => {
			if (!e.ctrlKey && !e.metaKey) return;
			e.preventDefault();
			const rect = box.getBoundingClientRect();
			zoomAt(cellSize * Math.exp(-e.deltaY * 0.01), e.clientX - rect.left, e.clientY - rect.top);
		};

		box.addEventListener('touchstart', onTouchStart, { passive: true });
		box.addEventListener('touchmove', onTouchMove, { passive: false });
		box.addEventListener('touchend', onTouchEnd, { passive: true });
		box.addEventListener('touchcancel', onTouchEnd, { passive: true });
		box.addEventListener('wheel', onWheel, { passive: false });
		return () => {
			box.removeEventListener('touchstart', onTouchStart);
			box.removeEventListener('touchmove', onTouchMove);
			box.removeEventListener('touchend', onTouchEnd);
			box.removeEventListener('touchcancel', onTouchEnd);
			box.removeEventListener('wheel', onWheel);
		};
	});
</script>

<div bind:this={outer} class="relative border-[2px] border-[#1a1917] bg-[#faf8f4]">
	<div
		bind:this={el}
		bind:clientWidth={viewW}
		bind:clientHeight={viewH}
		class="zoom-board overflow-auto"
		style="height: {height}px"
		aria-label={ariaLabel}
	>
		{@render children()}
	</div>

	{#if overlay}
		{@render overlay()}
	{/if}

	<div class="absolute right-1.5 bottom-1.5 flex gap-1">
		<button
			type="button"
			onclick={() => zoomButton(1 / 1.2)}
			disabled={cellSize <= minCell}
			class="h-8 w-8 cursor-pointer border border-[#1a1917] bg-[#faf8f4] text-lg leading-none disabled:opacity-40"
			aria-label="Zoom out">−</button
		>
		<button
			type="button"
			onclick={() => zoomButton(1.2)}
			disabled={cellSize >= maxCell}
			class="h-8 w-8 cursor-pointer border border-[#1a1917] bg-[#faf8f4] text-lg leading-none disabled:opacity-40"
			aria-label="Zoom in">+</button
		>
	</div>
</div>

<style>
	.zoom-board {
		touch-action: pan-x pan-y;
		overscroll-behavior: contain;
		scrollbar-width: none;
		-webkit-overflow-scrolling: touch;
	}
	.zoom-board::-webkit-scrollbar {
		display: none;
	}
</style>
