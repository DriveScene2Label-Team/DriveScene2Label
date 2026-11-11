import { useMemo } from 'react';
import type { BoxView } from '@/api/models';
import type { PaneFrames } from '@/features/frames/usePaneFrames';
import { objectKey } from '@/features/objects/objectKeys';
import { visibleBoxes, type PredState } from '@/features/objects/useFrameBoxes';
import { useLayout } from '@/stores/layout';
import { announce } from '@/stores/toast';
import { useWorkspace, type PaneId } from '@/stores/workspace';

/** Select (or with the same key, clear) an object; selecting opens the 객체 tab and makes the pane the work target. */
export function selectObject(paneId: PaneId, key: string | null, box?: BoxView | null): void {
  const st = useWorkspace.getState();
  const cur = st.panes[paneId].selectedBoxKey;
  const next = key != null && cur === key ? null : key;
  st.selectBox(paneId, next);
  if (paneId !== 'single') st.setActivePane(paneId);
  if (next) {
    if (useLayout.getState().sideTab !== 'objects') useLayout.getState().setSideTab('objects');
    if (box) announce(`${box.source === 'GT' ? 'GT' : '예측'} ${box.cls} 선택`);
  }
}

/** Boxes drawn in the cameras of a pane: layers applied, hidden objects removed. */
export function usePaneBoxes(paneId: PaneId, frames: PaneFrames, pred: PredState): BoxView[] {
  const layers = useWorkspace((s) => s.panes[paneId].layers);
  const hidden = useWorkspace((s) => s.panes[paneId].hidden);
  return useMemo(() => {
    const set = new Set(hidden);
    return visibleBoxes(frames.displayed.gt, pred, layers).filter((b) => !set.has(objectKey(b)));
  }, [frames.displayed.gt, pred, layers, hidden]);
}
