import { countSolutions } from './solver.ts';

let worker: Worker | null = null;
let nextId = 0;
const pending = new Map<number, (n: number) => void>();

function getWorker(): Worker | null {
	if (worker || typeof Worker === 'undefined') return worker;
	try {
		worker = new Worker(new URL('./solver.worker.ts', import.meta.url), { type: 'module' });
		worker.onmessage = (e: MessageEvent<{ id: number; solutions: number }>) => {
			pending.get(e.data.id)?.(e.data.solutions);
			pending.delete(e.data.id);
		};
	} catch {
		worker = null;
	}
	return worker;
}

/** Count solutions (capped at 1000) off the main thread when possible. */
export function countInBackground(grid: number[]): Promise<number> {
	const w = getWorker();
	if (!w) return Promise.resolve(countSolutions(grid));
	const id = nextId++;
	return new Promise((resolve) => {
		pending.set(id, resolve);
		w.postMessage({ id, grid });
	});
}
