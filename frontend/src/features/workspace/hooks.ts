import { useEffect } from 'react';
import type { BoxView } from '@/api/models';
import { objectKey } from '@/features/objects/objectKeys';
import type { PaneFrames } from '@/features/frames/usePaneFrames';
import { imageCache } from '@/lib/imageCache';
import { useLayout } from '@/stores/layout';
import { useOverlay } from '@/stores/overlay';
import { announce } from '@/stores/toast';
import { useWorkspace, type PaneId } from '@/stores/workspace';
import { toggleLayerAnnounced } from './Hud';

/** Pause playback when the tab is hidden; on leaving the workspace also stop and release idle images. */
export function usePlaybackLifecycle(): void {
  const pauseAll = useWorkspace((s) => s.pauseAll);
  useEffect(() => {
    const onVis = () => { if (document.hidden) pauseAll(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      document.removeEventListener('visibilitychange', onVis);
      pauseAll();
      imageCache.trim(0);
    };
  }, [pauseAll]);
}

const isTextEntry = (t: HTMLElement | null) =>
  !!t?.matches?.('textarea, select, [contenteditable="true"], input:not([type="checkbox"]):not([type="radio"]):not([type="range"])');

interface ShortcutContext {
  paneId: PaneId;
  frames: PaneFrames;
  /** Boxes of the displayed frame (for Delete/H on the selection). */
  boxes: BoxView[];
  sceneId: number | null;
  undo: (sceneId: number | null, jobId: number | null) => void;
}

/**
 * Workspace shortcuts (design sheet): Space play/pause · ←/→ frame · G/P layers · H hide selection · Delete delete
 * selection · ⌘/Ctrl+Z revert last edit · Esc clear selection · \\ inspector · ? shortcut sheet.
 * Not while typing; letter keys only on checkboxes/sliders; nothing behind a modal except the camera quick look.
 */
export function useWorkspaceShortcuts(ctx: ShortcutContext): void {
  const { paneId, frames, boxes, sceneId, undo } = ctx;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const t = e.target as HTMLElement | null;
      const ov = useOverlay.getState().overlay;
      if (ov && ov.kind !== 'zoom') return;
      if (ov?.kind === 'zoom' && ov.paneId !== paneId) return;
      const st = useWorkspace.getState();
      const pane = st.panes[paneId];
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.code === 'KeyZ' && !isTextEntry(t)) {
        e.preventDefault();
        undo(sceneId, pane.resultJobId);
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTextEntry(t)) return;
      if (t?.closest?.('[role="separator"], .v3d-host, .menu')) return;
      if (e.key === 'Escape') {
        if (ov) return; // Radix closes the dialog
        if (pane.selectedBoxKey) { st.selectBox(paneId, null); e.preventDefault(); }
        return;
      }
      const choice = !!t?.matches?.('input[type="checkbox"], input[type="radio"]');
      const slider = !!t?.matches?.('input[type="range"]');
      const inGroup = !!t?.closest?.('[role="radiogroup"], [role="group"], [role="tablist"], [role="toolbar"]');
      const i = frames.requestedIndex;
      const sel = pane.selectedBoxKey;
      if (e.key === ' ' && !choice && !t?.closest?.('button, a, [role="tab"], tr, summary')) {
        if (frames.samples.length > 1) st.setPlaying(paneId, !pane.playing);
      } else if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && !inGroup && !choice && !slider) {
        const s = frames.samples[i + (e.key === 'ArrowRight' ? 1 : -1)];
        if (!s) return;
        st.setPlaying(paneId, false);
        st.requestSample(paneId, s.token, 'user');
      } else if (e.code === 'KeyG') toggleLayerAnnounced(paneId, 'gt');
      else if (e.code === 'KeyP') toggleLayerAnnounced(paneId, 'pred');
      else if (e.code === 'KeyH') {
        if (!sel) return;
        st.toggleHidden(paneId, sel);
        announce(useWorkspace.getState().panes[paneId].hidden.includes(sel) ? '객체를 화면에서 숨겼어요' : '객체를 다시 보이게 했어요');
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && !ov) {
        const box = sel ? boxes.find((b) => objectKey(b) === sel) : undefined;
        if (!box) return;
        useOverlay.getState().open({ kind: 'confirm', paneId, box, instanceFrames: 0, frameIndex: frames.displayedIndex });
      } else if (e.code === 'Backslash' && !ov) {
        const l = useLayout.getState();
        l.setInspectorHidden(!l.inspectorHidden);
      } else if (e.key === '?' && !ov) {
        useOverlay.getState().open({ kind: 'keys' });
      } else return;
      e.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [paneId, frames.requestedIndex, frames.samples, frames.displayedIndex, boxes, sceneId, undo]);
}
