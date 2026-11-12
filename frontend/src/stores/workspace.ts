import { create } from 'zustand';
import type { ClassMode } from '@/api/dto';
import type { Speed } from '@/lib/time/timeline';

/**
 * Per-pane UI state. A/B are fully independent even when they show the same scene: server data is shared through
 * the TanStack Query cache, but frame, playback, layers, selection and job choice live here per pane.
 * The store never copies server arrays (samples, boxes); it keeps identifiers only.
 */
export type PaneId = 'single' | 'A' | 'B';
export type CompareSide = 'A' | 'B';
export type ChangeOrigin = 'user' | 'playback' | 'sync' | 'viewer' | 'url' | 'init';
export type PaneView = 'both' | 'cams' | 'lidar';
export type LayerKey = 'gt' | 'pred' | 'names' | 'cmp';
export interface Layers {
  gt: boolean;
  pred: boolean;
  /** Class name tags on camera boxes. */
  names: boolean;
  /** Boxes of the comparison job (compareJobId), drawn on top of the shown predictions in another colour. */
  cmp: boolean;
}

export interface PaneState {
  datasetId: number | null;
  sceneId: number | null;
  /** The frame the user (or playback/sync) asked for. */
  requestedSampleToken: string | null;
  /** The frame whose images and boxes are on screen. Switches only when the requested frame is fully prepared. */
  displayedSampleToken: string | null;
  lastOrigin: ChangeOrigin;
  changeSeq: number;
  playing: boolean;
  speed: Speed;
  layers: Layers;
  /**
   * Selected object (objectKey: a GT instance or one prediction box). Kept when the frame changes, so a GT instance
   * stays selected across its frames; the inspector says when it is not in the displayed frame.
   */
  selectedBoxKey: string | null;
  /** Objects hidden from the cameras/list of this pane (objectKey). Display only — nothing is sent to the server. */
  hidden: string[];
  focusCamera: string | null;
  classMode: ClassMode;
  /** Job whose status is watched in the inspector. */
  jobId: number | null;
  /** Completed job whose predictions are drawn. Kept while a newer run is pending or failed. */
  resultJobId: number | null;
  /**
   * Second completed job drawn next to resultJobId for a before/after look (e.g. a VESPA ver2 run against the
   * original). Display only: its boxes cannot be selected or edited.
   */
  compareJobId: number | null;
  recordingId: number | null;
  /** Compare panes only: cameras + 3D, camera grid or 3D. */
  paneView: PaneView;
  /**
   * UI context generation. Bumped whenever the pane shows another scene (A→B→A ends on a new number), so a late
   * answer to a request made in an older context is recorded but never attached to the current view.
   */
  generation: number;
}

export const initialPane = (): PaneState => ({
  datasetId: null,
  sceneId: null,
  requestedSampleToken: null,
  displayedSampleToken: null,
  lastOrigin: 'init',
  changeSeq: 0,
  playing: false,
  speed: 1,
  layers: { gt: true, pred: true, names: true, cmp: true },
  selectedBoxKey: null,
  hidden: [],
  focusCamera: null,
  classMode: 8,
  jobId: null,
  resultJobId: null,
  compareJobId: null,
  recordingId: null,
  paneView: 'both',
  generation: 0,
});

let generationSeq = 0;
const nextGeneration = () => ++generationSeq;

interface OpenScene {
  datasetId: number;
  sceneId: number;
  sampleToken?: string | null;
  jobId?: number | null;
  compareJobId?: number | null;
}

interface WorkspaceStore {
  panes: Record<PaneId, PaneState>;
  activePane: CompareSide;
  sync: boolean;
  openScene: (pane: PaneId, s: OpenScene) => void;
  closePane: (pane: PaneId) => void;
  resetServerContext: () => void;
  requestSample: (pane: PaneId, token: string, origin: ChangeOrigin) => void;
  markDisplayed: (pane: PaneId, token: string) => void;
  setPlaying: (pane: PaneId, playing: boolean) => void;
  setSpeed: (pane: PaneId, speed: Speed) => void;
  toggleLayer: (pane: PaneId, layer: LayerKey) => void;
  toggleHidden: (pane: PaneId, key: string) => void;
  showAllHidden: (pane: PaneId) => void;
  selectBox: (pane: PaneId, key: string | null) => void;
  setFocusCamera: (pane: PaneId, channel: string | null) => void;
  setClassMode: (pane: PaneId, mode: ClassMode) => void;
  watchJob: (pane: PaneId, jobId: number | null) => void;
  showResult: (pane: PaneId, jobId: number | null) => void;
  setCompareJob: (pane: PaneId, jobId: number | null) => void;
  setRecording: (pane: PaneId, recordingId: number | null) => void;
  setPaneView: (pane: PaneId, view: PaneView) => void;
  setActivePane: (pane: CompareSide) => void;
  setSync: (on: boolean) => void;
  pauseAll: () => void;
}

const patch = (s: WorkspaceStore, pane: PaneId, p: Partial<PaneState>): Pick<WorkspaceStore, 'panes'> => ({
  panes: { ...s.panes, [pane]: { ...s.panes[pane], ...p } },
});

export const useWorkspace = create<WorkspaceStore>()((set) => ({
  panes: { single: initialPane(), A: initialPane(), B: initialPane() },
  activePane: 'A',
  sync: false,

  openScene: (pane, o) =>
    set((s) => {
      const cur = s.panes[pane];
      const same = cur.datasetId === o.datasetId && cur.sceneId === o.sceneId;
      // Pane key = paneId + datasetId + sceneId: a different scene starts from a clean UI state.
      const base: PaneState = same ? cur : { ...initialPane(), classMode: cur.classMode, layers: cur.layers, speed: cur.speed, paneView: cur.paneView, generation: nextGeneration() };
      const next: PaneState = { ...base, datasetId: o.datasetId, sceneId: o.sceneId };
      if (o.sampleToken !== undefined && o.sampleToken !== next.requestedSampleToken) {
        next.requestedSampleToken = o.sampleToken;
        next.lastOrigin = 'url';
        next.changeSeq = cur.changeSeq + 1;
      }
      if (o.jobId !== undefined && o.jobId !== next.jobId) {
        next.jobId = o.jobId;
        if (o.jobId === null) next.resultJobId = null;
      }
      if (o.compareJobId !== undefined && o.compareJobId !== next.compareJobId) next.compareJobId = o.compareJobId;
      if (same && next === cur) return s;
      return patch(s, pane, next);
    }),

  closePane: (pane) => set((s) => patch(s, pane, { ...initialPane(), generation: nextGeneration() })),
  resetServerContext: () =>
    set((s) => {
      // A different backend instance: job/recording ids of the old one mean nothing here.
      const clear = (p: PaneState): PaneState => ({ ...p, jobId: null, resultJobId: null, compareJobId: null, recordingId: null, selectedBoxKey: null, generation: nextGeneration() });
      return { panes: { single: clear(s.panes.single), A: clear(s.panes.A), B: clear(s.panes.B) } };
    }),

  requestSample: (pane, token, origin) =>
    set((s) => {
      const cur = s.panes[pane];
      if (cur.requestedSampleToken === token) return s;
      // Selection is an object key (GT instance / prediction box), not a per-frame row: it is kept across frames.
      return patch(s, pane, { requestedSampleToken: token, lastOrigin: origin, changeSeq: cur.changeSeq + 1 });
    }),

  markDisplayed: (pane, token) =>
    set((s) => (s.panes[pane].displayedSampleToken === token ? s : patch(s, pane, { displayedSampleToken: token }))),

  setPlaying: (pane, playing) => set((s) => (s.panes[pane].playing === playing ? s : patch(s, pane, { playing }))),
  setSpeed: (pane, speed) => set((s) => patch(s, pane, { speed })),
  toggleLayer: (pane, layer) =>
    set((s) => {
      const cur = s.panes[pane];
      const layers = { ...cur.layers, [layer]: !cur.layers[layer] };
      // Hiding a source also drops a selection of that source (it would no longer be visible anywhere).
      const sel = cur.selectedBoxKey;
      const dropSel = !layers[layer] && (layer === 'gt' || layer === 'pred') && sel != null && sel.startsWith(layer === 'gt' ? 'gt:' : 'pred:');
      return patch(s, pane, { layers, ...(dropSel ? { selectedBoxKey: null } : {}) });
    }),
  toggleHidden: (pane, key) =>
    set((s) => {
      const h = s.panes[pane].hidden;
      return patch(s, pane, { hidden: h.includes(key) ? h.filter((k) => k !== key) : [...h, key].slice(-500) });
    }),
  showAllHidden: (pane) => set((s) => (s.panes[pane].hidden.length ? patch(s, pane, { hidden: [] }) : s)),
  selectBox: (pane, key) => set((s) => patch(s, pane, { selectedBoxKey: key })),
  setFocusCamera: (pane, channel) => set((s) => patch(s, pane, { focusCamera: channel })),
  setClassMode: (pane, classMode) => set((s) => patch(s, pane, { classMode })),
  watchJob: (pane, jobId) => set((s) => patch(s, pane, { jobId })),
  showResult: (pane, resultJobId) => set((s) => (s.panes[pane].resultJobId === resultJobId ? s : patch(s, pane, { resultJobId }))),
  setCompareJob: (pane, compareJobId) => set((s) => (s.panes[pane].compareJobId === compareJobId ? s : patch(s, pane, { compareJobId }))),
  setRecording: (pane, recordingId) => set((s) => (s.panes[pane].recordingId === recordingId ? s : patch(s, pane, { recordingId }))),
  setPaneView: (pane, paneView) => set((s) => patch(s, pane, { paneView })),
  setActivePane: (activePane) => set({ activePane }),
  setSync: (sync) => set({ sync }),
  pauseAll: () =>
    set((s) => ({
      panes: {
        single: { ...s.panes.single, playing: false },
        A: { ...s.panes.A, playing: false },
        B: { ...s.panes.B, playing: false },
      },
    })),
}));

export function usePane(pane: PaneId): PaneState {
  return useWorkspace((s) => s.panes[pane]);
}

/** Test helper. */
export function resetWorkspace(): void {
  useWorkspace.setState({ panes: { single: initialPane(), A: initialPane(), B: initialPane() }, activePane: 'A', sync: false });
}
