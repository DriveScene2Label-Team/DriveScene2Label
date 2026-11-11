import { useSyncExternalStore } from 'react';

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia?.(query);
      mq?.addEventListener('change', cb);
      return () => mq?.removeEventListener('change', cb);
    },
    () => window.matchMedia?.(query).matches ?? false,
    () => false,
  );
}

/** Narrow layout: the workspace stacks vertically and scrolls (design breakpoint 900px). */
export const useFlowLayout = () => useMediaQuery('(max-width: 900px)');
