import { expect, it, vi } from 'vitest';
import { recoverChunkLoad } from './RouteErrorPage';

it('reloads a missing route chunk once and preserves the guard across page loads', () => {
  const values = new Map<string, string>();
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); } };
  const reload = vi.fn();
  const error = new TypeError('Failed to fetch dynamically imported module: /assets/old.js');
  expect(recoverChunkLoad(error, storage, reload, 100_000)).toBe(true);
  expect(recoverChunkLoad(error, storage, reload, 101_000)).toBe(false);
  expect(reload).toHaveBeenCalledTimes(1);
  expect(recoverChunkLoad(error, storage, reload, 200_000)).toBe(true);
});

it('does not reload application errors or loop when session storage is unavailable', () => {
  const storage = { getItem: () => { throw new Error('Storage blocked'); }, setItem: vi.fn() };
  const reload = vi.fn();
  expect(recoverChunkLoad(new Error('Invalid annotation'), storage, reload)).toBe(false);
  expect(recoverChunkLoad(new TypeError('Importing a module script failed.'), storage, reload)).toBe(false);
  expect(reload).not.toHaveBeenCalled();
});
