import { create } from 'zustand';
import { readStored, writeStored } from '@/lib/storage';

/**
 * Display preferences that survive reloads (localStorage, small values only). Applied after the URL context; they
 * never contain server data. splitRatio null = "fit the six cameras" (computed from the available space).
 */
export type Theme = 'light' | 'dark' | 'auto';
export type Orient = 'stack' | 'side';
export type SideTab = 'objects' | 'jobs' | 'edits';

export interface LayoutPrefs {
  theme: Theme;
  /** Cameras + 3D: 3D below the cameras (stack) or to their right (side). */
  orient: Orient;
  splitRatio: number | null;
  compareRatio: number;
  inspectorHidden: boolean;
  sideTab: SideTab;
}

const KEY = 'ds2l.layout';
const VERSION = 2;
export const DEFAULT_LAYOUT: LayoutPrefs = { theme: 'light', orient: 'stack', splitRatio: null, compareRatio: 0.5, inspectorHidden: false, sideTab: 'objects' };
export const RATIO_MIN = 0.25;
export const SPLIT_MAX = 0.8;
export const COMPARE_MAX = 0.75;

export const clampSplit = (r: number) => Math.min(SPLIT_MAX, Math.max(RATIO_MIN, r));
export const clampCompare = (r: number) => Math.min(COMPARE_MAX, Math.max(RATIO_MIN, r));

function isPrefs(v: unknown): v is LayoutPrefs {
  if (!v || typeof v !== 'object') return false;
  const o = v as Record<string, unknown>;
  return ['light', 'dark', 'auto'].includes(o.theme as string) && ['stack', 'side'].includes(o.orient as string)
    && (o.splitRatio === null || typeof o.splitRatio === 'number') && typeof o.compareRatio === 'number'
    && typeof o.inspectorHidden === 'boolean' && ['objects', 'jobs', 'edits'].includes(o.sideTab as string);
}

/** Object list filter of the inspector. Session only (not persisted). */
export interface ObjectFilter {
  source: 'all' | 'gt' | 'pred';
  cls: string;
}

interface LayoutStore extends LayoutPrefs {
  filter: ObjectFilter;
  setTheme: (t: Theme) => void;
  setOrient: (o: Orient) => void;
  setSplitRatio: (r: number) => void;
  setCompareRatio: (r: number) => void;
  setInspectorHidden: (v: boolean) => void;
  setSideTab: (t: SideTab) => void;
  setFilter: (f: Partial<ObjectFilter>) => void;
  resetSplit: () => void;
  resetCompare: () => void;
}

const loaded = readStored(KEY, VERSION, isPrefs, DEFAULT_LAYOUT);

export const useLayout = create<LayoutStore>()((set, get) => {
  const save = () => {
    const { theme, orient, splitRatio, compareRatio, inspectorHidden, sideTab } = get();
    writeStored(KEY, VERSION, { theme, orient, splitRatio, compareRatio, inspectorHidden, sideTab });
  };
  const put = (p: Partial<LayoutPrefs>) => { set(p); save(); };
  return {
    ...loaded,
    splitRatio: loaded.splitRatio == null ? null : clampSplit(loaded.splitRatio),
    compareRatio: clampCompare(loaded.compareRatio),
    filter: { source: 'all', cls: 'all' },
    setTheme: (theme) => put({ theme }),
    setOrient: (orient) => put({ orient }),
    setSplitRatio: (r) => put({ splitRatio: clampSplit(r) }),
    setCompareRatio: (r) => put({ compareRatio: clampCompare(r) }),
    setInspectorHidden: (inspectorHidden) => put({ inspectorHidden }),
    setSideTab: (sideTab) => put({ sideTab }),
    setFilter: (f) => set({ filter: { ...get().filter, ...f } }),
    resetSplit: () => put({ splitRatio: null }),
    resetCompare: () => put({ compareRatio: DEFAULT_LAYOUT.compareRatio }),
  };
});
