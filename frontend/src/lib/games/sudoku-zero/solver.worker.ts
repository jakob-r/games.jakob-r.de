import { countSolutions } from './solver.ts';

self.onmessage = (e: MessageEvent<{ id: number; grid: number[] }>) => {
	const { id, grid } = e.data;
	self.postMessage({ id, solutions: countSolutions(grid) });
};
