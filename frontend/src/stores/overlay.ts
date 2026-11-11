import { create } from 'zustand';
import type { BoxView } from '@/api/models';
import type { PaneId } from './workspace';

/** Modal layers of the workspace: camera quick look, delete confirmation, shortcut sheet. One at a time. */
export type Overlay =
  | { kind: 'zoom'; paneId: PaneId; channel: string }
  | { kind: 'confirm'; paneId: PaneId; box: BoxView; instanceFrames: number; frameIndex: number }
  | { kind: 'keys' };

interface OverlayStore {
  overlay: Overlay | null;
  open: (o: Overlay) => void;
  close: () => void;
}

export const useOverlay = create<OverlayStore>()((set) => ({
  overlay: null,
  open: (overlay) => set({ overlay }),
  close: () => set({ overlay: null }),
}));
