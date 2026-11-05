import type { KeyboardEvent } from 'react';
import type { Scene } from '@/api/models';
import type { PaneFrames } from '@/features/frames/usePaneFrames';
import { useJobState } from '@/features/labeling/useJobState';
import type { PredState } from '@/features/objects/useFrameBoxes';
import { useLayout, type SideTab } from '@/stores/layout';
import { useWorkspace, type CompareSide, type PaneId } from '@/stores/workspace';
import { EditsPanel, useLabelEdits } from './EditsPanel';
import { JobsPanel } from './JobsPanel';
import { ObjectsPanel, useObjectRows } from './ObjectsPanel';

const TABS: Array<[SideTab, string]> = [['objects', '객체'], ['jobs', '자동 라벨링'], ['edits', '기록']];

interface Props {
  paneId: PaneId;
  scene: Scene | undefined;
  frames: PaneFrames;
  pred: PredState;
  hidden: boolean;
  compare?: { active: CompareSide; names: Record<CompareSide, string>; onActive: (p: CompareSide) => void };
}

/** Right-hand card: work target (compare), tabs 객체 / 자동 라벨링 / 기록. Stays mounted while hidden so job polling continues. */
export function Inspector({ paneId, scene, frames, pred, hidden, compare }: Props) {
  return (
    <aside className="inspector" id="side" aria-label="인스펙터" hidden={hidden}>
      {compare && (
        <div className="insp-target">
          <span className="lbl" id="tg-l">작업 대상</span>
          <div className="seg seg--full" role="radiogroup" aria-labelledby="tg-l">
            {(['A', 'B'] as const).map((p) => (
              <button key={p} type="button" role="radio" aria-checked={compare.active === p} onClick={() => compare.onActive(p)}><b>{p}</b>{compare.names[p]}</button>
            ))}
          </div>
        </div>
      )}
      {scene ? <InspectorBody key={`${paneId}-${scene.id}`} paneId={paneId} scene={scene} frames={frames} pred={pred} paneLabel={compare?.active} />
        : <p className="panel-msg">불러오는 중…</p>}
    </aside>
  );
}

function InspectorBody({ paneId, scene, frames, pred, paneLabel }: { paneId: PaneId; scene: Scene; frames: PaneFrames; pred: PredState; paneLabel?: CompareSide }) {
  const tab = useLayout((s) => s.sideTab);
  const setTab = useLayout((s) => s.setSideTab);
  const layers = useWorkspace((s) => s.panes[paneId].layers);
  const resultJobId = useWorkspace((s) => s.panes[paneId].resultJobId);
  const job = useJobState(paneId, scene, frames.samples);
  const rows = useObjectRows(frames, pred);
  const edits = useLabelEdits(scene, resultJobId);
  const nObj = rows.filter((r) => (r.box.source === 'GT' ? layers.gt : layers.pred)).length;
  const nEdits = edits.data?.filter((e) => !e.revertedAt).length ?? 0;
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const k = TABS.findIndex(([id]) => id === tab);
    const next = TABS[(k + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length]![0];
    setTab(next);
    window.setTimeout(() => document.getElementById(`tab-${next}`)?.focus(), 0);
  };
  return (
    <>
      <div className="seg seg--full insp-tabs" role="tablist" aria-label="인스펙터" onKeyDown={onKey}>
        {TABS.map(([k, l]) => (
          <button key={k} type="button" role="tab" id={`tab-${k}`} aria-selected={tab === k} aria-controls="side-panel" tabIndex={tab === k ? 0 : -1} onClick={() => setTab(k)}>
            {l}
            {k === 'objects' && <> <span className="cnt">{nObj}</span></>}
            {k === 'jobs' && job.active && <i className="run-dot" aria-label="진행 중" />}
            {k === 'edits' && nEdits > 0 && <> <span className="cnt">{nEdits}</span></>}
          </button>
        ))}
      </div>
      <div className="insp-panel" id="side-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === 'objects' && <ObjectsPanel paneId={paneId} scene={scene} frames={frames} pred={pred} rows={rows} />}
        {tab === 'jobs' && <JobsPanel paneId={paneId} scene={scene} frameCount={frames.samples.length} job={job} paneLabel={paneLabel} />}
        {tab === 'edits' && <EditsPanel paneId={paneId} scene={scene} samples={frames.samples} />}
      </div>
    </>
  );
}

/** Keeps job polling / result display alive for a compare pane that is not the inspector's target. Renders nothing. */
export function JobTracker({ paneId, scene, frames }: { paneId: PaneId; scene: Scene; frames: PaneFrames }) {
  useJobState(paneId, scene, frames.samples);
  return null;
}
