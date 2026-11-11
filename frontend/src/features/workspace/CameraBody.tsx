import { describeError } from '@/api/http';
import { Icon } from '@/components/Icon';
import { CameraGrid } from '@/features/cameras/CameraGrid';
import type { PaneFrames } from '@/features/frames/usePaneFrames';
import { objectKey } from '@/features/objects/objectKeys';
import type { PredState } from '@/features/objects/useFrameBoxes';
import { useOverlay } from '@/stores/overlay';
import { useWorkspace, type PaneId } from '@/stores/workspace';
import { selectObject, usePaneBoxes } from './actions';

/** Six cameras of the displayed frame, or a full-area state while the scene's frames are not available. */
export function CameraBody({ paneId, frames, pred, fit }: { paneId: PaneId; frames: PaneFrames; pred: PredState; fit?: 'width' }) {
  const pane = useWorkspace((s) => s.panes[paneId]);
  const setFocus = useWorkspace((s) => s.setFocusCamera);
  const openOverlay = useOverlay((s) => s.open);
  const boxes = usePaneBoxes(paneId, frames, pred);
  const state = frameState(frames);
  if (state) return state;
  const all = [...(frames.displayed.gt ?? []), ...(pred.kind === 'ready' ? pred.boxes : [])];
  return (
    <CameraGrid
      cameras={frames.displayed.cameras}
      boxes={boxes}
      selectedKey={pane.selectedBoxKey}
      focusCamera={pane.focusCamera ?? 'CAM_FRONT'}
      names={pane.layers.names}
      frameNumber={frames.displayedIndex + 1}
      onSelect={(k) => selectObject(paneId, k, all.find((b) => objectKey(b) === k) ?? null)}
      onFocus={(ch) => { setFocus(paneId, ch); if (paneId !== 'single') useWorkspace.getState().setActivePane(paneId); }}
      onExpand={(ch) => { setFocus(paneId, ch); openOverlay({ kind: 'zoom', paneId, channel: ch }); }}
      fit={fit}
      label={`카메라 6대, 프레임 ${frames.displayedIndex + 1}`}
    />
  );
}

function frameState(frames: PaneFrames) {
  if (frames.samplesError) return <div className="stage-state" role="alert"><Icon name="warn" /><b>프레임 목록을 불러오지 못했어요</b><span className="mono">{describeError(frames.samplesError)}</span></div>;
  if (frames.samplesLoading || (!frames.displayed.sample && frames.samples.length > 0)) return <div className="stage-state" role="status"><span className="spinner" aria-hidden="true" /><b>첫 프레임을 불러오고 있어요</b></div>;
  if (frames.samples.length === 0) return <div className="stage-state"><b>이 씬에는 프레임이 없어요</b></div>;
  if (frames.displayed.detailError) return <div className="stage-state" role="alert"><Icon name="warn" /><b>센서 파일 목록을 불러오지 못했어요</b><span className="mono">{describeError(frames.displayed.detailError)}</span></div>;
  return null;
}
