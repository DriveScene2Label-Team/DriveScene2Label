import { useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router';
import type { SampleRef, Scene } from '@/api/models';
import { compareUrl, parseCompare, searchUrl, workspaceUrl } from '@/app/urls';
import { usePaneFrames, type PaneFrames } from '@/features/frames/usePaneFrames';
import { Inspector, JobTracker } from '@/features/inspector/Inspector';
import { Split } from '@/features/layout/Split';
import { usePredictions, type PredState } from '@/features/objects/useFrameBoxes';
import { useScene } from '@/features/scenes/useScene';
import { FrameTimeline } from '@/features/timeline/FrameTimeline';
import { RecordingPanel } from '@/features/viewer/RecordingPanel';
import { CameraBody } from '@/features/workspace/CameraBody';
import { Hud } from '@/features/workspace/Hud';
import { usePlaybackLifecycle, useWorkspaceShortcuts } from '@/features/workspace/hooks';
import { DeleteDialog, KeysSheet, useUndoLast, ZoomDialog } from '@/features/workspace/Overlays';
import { PageState, WorkspaceToolbar, type WorkspaceMode } from '@/features/workspace/WorkspaceToolbar';
import { josa } from '@/lib/edits/labelEdits';
import { mapRelative } from '@/lib/time/timeline';
import { COMPARE_MAX, useLayout } from '@/stores/layout';
import { toast } from '@/stores/toast';
import { useWorkspace, type CompareSide, type PaneView } from '@/stores/workspace';

export default function SceneComparePage() {
  const [sp] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const params = parseCompare(sp);
  const openScene = useWorkspace((s) => s.openScene);
  const setActivePane = useWorkspace((s) => s.setActivePane);
  const setSync = useWorkspace((s) => s.setSync);
  const active = useWorkspace((s) => s.activePane);
  const sync = useWorkspace((s) => s.sync);
  const paneA = useWorkspace((s) => s.panes.A);
  const paneB = useWorkspace((s) => s.panes.B);
  const ratio = useLayout((s) => s.compareRatio);
  const setRatio = useLayout((s) => s.setCompareRatio);
  const resetRatio = useLayout((s) => s.resetCompare);
  const inspectorHidden = useLayout((s) => s.inspectorHidden);

  const written = useRef<string | null>(null);
  useEffect(() => {
    if (location.search === written.current) return;
    for (const side of ['A', 'B'] as const) {
      const p = params[side];
      if (p.datasetId != null && p.sceneId != null) openScene(side, { datasetId: p.datasetId, sceneId: p.sceneId, sampleToken: p.sample, jobId: p.job });
    }
    setActivePane(params.active);
    setSync(params.sync);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  const sceneA = useScene(paneA.datasetId, paneA.sceneId);
  const sceneB = useScene(paneB.datasetId, paneB.sceneId);
  const framesA = usePaneFrames('A');
  const framesB = usePaneFrames('B');
  const predA = usePredictions(paneA.resultJobId, framesA.displayed.sample);
  const predB = usePredictions(paneB.resultJobId, framesB.displayed.sample);
  const undo = useUndoLast();
  usePlaybackLifecycle();
  const activeFrames = active === 'A' ? framesA : framesB;
  const activePred = active === 'A' ? predA : predB;
  const activeScene = active === 'A' ? sceneA.scene : sceneB.scene;
  useWorkspaceShortcuts({
    paneId: active, frames: activeFrames, sceneId: activeScene?.id ?? null, undo,
    boxes: [...(activeFrames.displayed.gt ?? []), ...(activePred.kind === 'ready' ? activePred.boxes : [])],
  });
  useRelativeSync(framesA.samples, framesB.samples);

  // Store → URL.
  useEffect(() => {
    if (paneA.playing || paneB.playing || framesA.buffering || framesB.buffering) return;
    const t = window.setTimeout(() => {
      if (window.location.pathname !== '/compare') return; // navigated away meanwhile: never undo that
      const url = compareUrl({
        A: { datasetId: paneA.datasetId, sceneId: paneA.sceneId, sample: paneA.displayedSampleToken, job: paneA.jobId },
        B: { datasetId: paneB.datasetId, sceneId: paneB.sceneId, sample: paneB.displayedSampleToken, job: paneB.jobId },
        sync, active,
      });
      const search = url.slice(url.indexOf('?'));
      if (search !== location.search) {
        written.current = search;
        navigate(url, { replace: true });
      }
    }, 250);
    return () => window.clearTimeout(t);
  }, [paneA, paneB, sync, active, framesA.buffering, framesB.buffering, location.search, navigate]);

  useEffect(() => {
    if (sceneA.scene && sceneB.scene) document.title = `${sceneA.scene.name}, ${sceneB.scene.name} 비교 - DriveScene2Label`;
  }, [sceneA.scene, sceneB.scene]);

  if (params.A.datasetId == null || params.A.sceneId == null || params.B.datasetId == null || params.B.sceneId == null) {
    return <PageState title="비교할 두 씬 정보가 링크에 없어요" detail="datasetA/sceneA와 datasetB/sceneB가 모두 필요해요." actions={<Link className="btn" to={searchUrl(null)}>씬 목록에서 고르기</Link>} />;
  }

  const activePane = active === 'A' ? paneA : paneB;
  const nameA = sceneA.scene?.name ?? '…';
  const nameB = sceneB.scene?.name ?? '…';
  const exitCompare = () => {
    if (activePane.datasetId == null || activePane.sceneId == null) return navigate(searchUrl(null));
    navigate(workspaceUrl({ datasetId: activePane.datasetId, sceneId: activePane.sceneId, sample: activePane.displayedSampleToken, job: activePane.jobId, view: 'split' }));
  };
  const setMode = (m: WorkspaceMode) => {
    if (m === 'compare' || activePane.datasetId == null || activePane.sceneId == null) return;
    navigate(workspaceUrl({ datasetId: activePane.datasetId, sceneId: activePane.sceneId, sample: activePane.displayedSampleToken, job: activePane.jobId, view: m === 'cams' ? 'six' : 'split' }));
  };
  const toggleSync = (on: boolean) => {
    setSync(on);
    if (on) {
      useWorkspace.getState().setPlaying('B', false);
      const st = useWorkspace.getState();
      const i = framesA.samples.findIndex((s) => s.token === st.panes.A.requestedSampleToken);
      const target = framesB.samples[mapRelative(framesA.samples, i, framesB.samples)];
      if (i >= 0 && target) st.requestSample('B', target.token, 'sync');
    }
    toast(on ? '두 씬의 재생 위치를 비율로 맞춰요' : '재생 위치 맞추기를 껐어요');
  };
  const backLabel = activeScene ? `${josa(activeScene.name, '으로/로')} 돌아가기` : '비교 닫기';

  return (
    <div className={inspectorHidden ? 'app app--ws insp-hidden' : 'app app--ws'} data-mode="compare">
      <WorkspaceToolbar title="두 씬 비교" sub={`${josa(nameA, '과/와')} ${nameB}`} mode="compare" onMode={setMode} backLabel={backLabel} onBack={exitCompare} datasetId={activePane.datasetId} />
      <div className="body" id="main">
        <section className="stage" aria-label="센서 화면">
          <Hud paneId={active} compareTag={active} sync={{ on: sync, set: toggleSync }} onResetSplit={resetRatio} onExitCompare={exitCompare} />
          <div className="viewport">
            <Split className="split--compare" orient="side" ratio={ratio} max={COMPARE_MAX} onChange={setRatio} onReset={resetRatio} label="씬 A와 씬 B 영역 비율"
              a={<ComparePane side="A" scene={sceneA.scene} scenes={sceneA.scenes} frames={framesA} pred={predA} active={active === 'A'} />}
              b={<ComparePane side="B" scene={sceneB.scene} scenes={sceneB.scenes} frames={framesB} pred={predB} active={active === 'B'} />} />
          </div>
        </section>
        <Inspector paneId={active} scene={activeScene} frames={activeFrames} pred={activePred} hidden={inspectorHidden}
          compare={{ active, names: { A: nameA, B: nameB }, onActive: setActivePane }} />
      </div>
      {sceneA.scene && <JobTracker paneId="A" scene={sceneA.scene} frames={framesA} />}
      {sceneB.scene && <JobTracker paneId="B" scene={sceneB.scene} frames={framesB} />}
      <ZoomDialog paneId="A" sceneName={nameA} frames={framesA} pred={predA} />
      <ZoomDialog paneId="B" sceneName={nameB} frames={framesB} pred={predB} />
      <DeleteDialog />
      <KeysSheet />
    </div>
  );
}

/**
 * FR-16: when sync is on, a user/playback/viewer change in one pane moves the other pane to the same relative
 * position of its own time span. Sync-originated changes are not propagated back.
 */
function useRelativeSync(samplesA: SampleRef[], samplesB: SampleRef[]) {
  const sync = useWorkspace((s) => s.sync);
  const seqA = useWorkspace((s) => s.panes.A.changeSeq);
  const seqB = useWorkspace((s) => s.panes.B.changeSeq);
  useEffect(() => {
    if (!sync) return;
    const st = useWorkspace.getState();
    const a = st.panes.A;
    if (a.lastOrigin === 'sync' || a.lastOrigin === 'init') return;
    const i = samplesA.findIndex((s) => s.token === a.requestedSampleToken);
    const target = samplesB[mapRelative(samplesA, i, samplesB)];
    if (i >= 0 && target) st.requestSample('B', target.token, 'sync');
  }, [sync, seqA, samplesA, samplesB]);
  useEffect(() => {
    if (!sync) return;
    const st = useWorkspace.getState();
    const b = st.panes.B;
    if (b.lastOrigin === 'sync' || b.lastOrigin === 'init') return;
    const i = samplesB.findIndex((s) => s.token === b.requestedSampleToken);
    const target = samplesA[mapRelative(samplesB, i, samplesA)];
    if (i >= 0 && target) st.requestSample('A', target.token, 'sync');
  }, [sync, seqB, samplesA, samplesB]);
}

const VIEWS: Array<[PaneView, string]> = [['both', '카메라 + 3D'], ['cams', '카메라'], ['lidar', '3D']];

function ComparePane({ side, scene, scenes, frames, pred, active }: { side: CompareSide; scene: Scene | undefined; scenes: Scene[] | undefined; frames: PaneFrames; pred: PredState; active: boolean }) {
  const pane = useWorkspace((s) => s.panes[side]);
  const setActivePane = useWorkspace((s) => s.setActivePane);
  const setPaneView = useWorkspace((s) => s.setPaneView);
  const openScene = useWorkspace((s) => s.openScene);
  const setPlaying = useWorkspace((s) => s.setPlaying);
  const view = pane.paneView;
  const recording = scene ? <RecordingPanel paneId={side} scene={scene} enabled={active} /> : null;
  return (
    <section className={active ? 'pane is-active' : 'pane'} data-pane={side} aria-label={`씬 ${side}${scene ? `, ${scene.name}` : ''}`}
      onPointerDownCapture={() => { if (!active) setActivePane(side); }}>
      <div className="pane-head">
        <span className="pane-tag" aria-hidden="true">{side}</span>
        <label className="sr-only" htmlFor={`pane-sel-${side}`}>씬 {side}</label>
        <select id={`pane-sel-${side}`} className="popup popup--media popup--sm" value={pane.sceneId ?? ''}
          onChange={(e) => { setPlaying(side, false); setActivePane(side); openScene(side, { datasetId: pane.datasetId!, sceneId: Number(e.currentTarget.value), sampleToken: null, jobId: null }); }}>
          {!scenes && scene && <option value={scene.id}>{scene.name}</option>}
          {scenes?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <div className="seg seg--media seg--sm" role="group" aria-label={`씬 ${side} 화면`}>
          {VIEWS.map(([k, l]) => <button key={k} type="button" aria-pressed={view === k} onClick={() => setPaneView(side, k)}>{l}</button>)}
        </div>
        <span className="pane-gap" />
        <span className="pane-target">작업 대상</span>
        <button type="button" className="hud-btn pane-pick" onClick={() => setActivePane(side)}>작업 대상으로</button>
      </div>
      <div className="pane-body">
        {view === 'lidar' ? recording : view === 'cams' ? <CameraBody paneId={side} frames={frames} pred={pred} /> : (
          <div className="pane-stack">
            <div className="pane-cams"><CameraBody paneId={side} frames={frames} pred={pred} fit="width" /></div>
            <div className="pane-3d">{recording}</div>
          </div>
        )}
      </div>
      <div className="pane-tl">
        <FrameTimeline paneId={side} samples={frames.samples} requestedIndex={frames.requestedIndex} displayedIndex={frames.displayedIndex} buffering={frames.buffering} prefix={`씬 ${side} `} />
      </div>
    </section>
  );
}
