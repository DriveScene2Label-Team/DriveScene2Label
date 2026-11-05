import { useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router';
import { describeError } from '@/api/http';
import { compareUrl, parseWorkspace, searchUrl, workspaceUrl, type WorkspaceView } from '@/app/urls';
import { usePaneFrames } from '@/features/frames/usePaneFrames';
import { Inspector } from '@/features/inspector/Inspector';
import { Split } from '@/features/layout/Split';
import { usePredictions } from '@/features/objects/useFrameBoxes';
import { useScene } from '@/features/scenes/useScene';
import { FrameTimeline } from '@/features/timeline/FrameTimeline';
import { RecordingPanel } from '@/features/viewer/RecordingPanel';
import { CameraBody } from '@/features/workspace/CameraBody';
import { Hud } from '@/features/workspace/Hud';
import { usePlaybackLifecycle, useWorkspaceShortcuts } from '@/features/workspace/hooks';
import { DeleteDialog, KeysSheet, useUndoLast, ZoomDialog } from '@/features/workspace/Overlays';
import { PageState, WorkspaceToolbar, type WorkspaceMode } from '@/features/workspace/WorkspaceToolbar';
import { SPLIT_MAX, useLayout } from '@/stores/layout';
import { useWorkspace } from '@/stores/workspace';

export default function SceneWorkspacePage() {
  const { sceneId: sceneParam } = useParams();
  const [sp] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const params = parseWorkspace(sceneParam, sp);
  const openScene = useWorkspace((s) => s.openScene);
  const pane = useWorkspace((s) => s.panes.single);
  const inspectorHidden = useLayout((s) => s.inspectorHidden);
  const orient = useLayout((s) => s.orient);
  const splitRatio = useLayout((s) => s.splitRatio);
  const setSplitRatio = useLayout((s) => s.setSplitRatio);
  const resetSplit = useLayout((s) => s.resetSplit);
  const { scene, scenes, isPending, error, notFound, refetch } = useScene(params.datasetId, params.sceneId);

  // URL → store, except for URLs this page wrote itself (prevents replace/parse loops).
  const written = useRef<string | null>(null);
  useEffect(() => {
    if (location.search === written.current) return;
    if (params.datasetId == null || params.sceneId == null) return;
    openScene('single', { datasetId: params.datasetId, sceneId: params.sceneId, sampleToken: params.sample, jobId: params.job });
  }, [location.search, params.datasetId, params.sceneId, params.sample, params.job, openScene]);

  const frames = usePaneFrames('single');
  const pred = usePredictions(pane.resultJobId, frames.displayed.sample);
  const undo = useUndoLast();
  usePlaybackLifecycle();
  useWorkspaceShortcuts({
    paneId: 'single', frames, sceneId: scene?.id ?? null, undo,
    boxes: [...(frames.displayed.gt ?? []), ...(pred.kind === 'ready' ? pred.boxes : [])],
  });

  // Store → URL (replace, no history spam). Not while playing or while a frame is still loading.
  useEffect(() => {
    if (pane.playing || frames.buffering || pane.datasetId == null || pane.sceneId == null || !pane.displayedSampleToken) return;
    const path = window.location.pathname;
    const t = window.setTimeout(() => {
      if (window.location.pathname !== path || path !== `/scenes/${pane.sceneId}`) return;
      const url = workspaceUrl({ datasetId: pane.datasetId!, sceneId: pane.sceneId!, sample: pane.displayedSampleToken, job: pane.jobId, view: params.view });
      const search = url.slice(url.indexOf('?'));
      if (search !== location.search) {
        written.current = search;
        navigate(url, { replace: true });
      }
    }, 250);
    return () => window.clearTimeout(t);
  }, [pane.playing, frames.buffering, pane.datasetId, pane.sceneId, pane.displayedSampleToken, pane.jobId, params.view, location.search, navigate]);

  useEffect(() => { if (scene) document.title = `${scene.name} - DriveScene2Label`; }, [scene]);

  const setMode = (m: WorkspaceMode) => {
    if (pane.datasetId == null || pane.sceneId == null) return;
    if (m === 'compare') {
      const list = scenes ?? [];
      const k = list.findIndex((s) => s.id === pane.sceneId);
      const other = list.length > 1 ? list[(k + 1) % list.length]! : list[0];
      const side = { datasetId: pane.datasetId, sceneId: pane.sceneId, sample: pane.displayedSampleToken, job: pane.jobId };
      navigate(compareUrl({ A: side, B: other ? { datasetId: other.datasetId, sceneId: other.id, sample: null, job: null } : { ...side, job: null }, sync: false, active: 'A' }));
      return;
    }
    const view: WorkspaceView = m === 'cams' ? 'six' : 'split';
    if (view === params.view) return;
    navigate(workspaceUrl({ datasetId: pane.datasetId, sceneId: pane.sceneId, sample: pane.displayedSampleToken, job: pane.jobId, view }));
  };

  if (params.datasetId == null || params.sceneId == null) {
    return <PageState title="링크에 데이터셋 또는 씬 정보가 없어요" detail="공유 링크에는 dataset과 씬 번호가 함께 있어야 해요." actions={<Link className="btn" to={searchUrl(null)}>씬 목록에서 고르기</Link>} />;
  }
  if (error || notFound) {
    return (
      <PageState title={notFound ? '이 데이터셋에서 씬을 찾을 수 없어요' : '씬 정보를 불러오지 못했어요'}
        detail={notFound ? `dataset ${params.datasetId}에 scene ${params.sceneId}이(가) 없어요.` : describeError(error)}
        actions={<>{!notFound && <button type="button" className="btn" onClick={() => void refetch()}>다시 불러오기</button>}<Link className="btn plain" to={searchUrl(params.datasetId)}>씬 목록으로</Link></>} />
    );
  }
  if (isPending || !scene) return <PageState loading />;

  const mode: WorkspaceMode = params.view === 'six' ? 'cams' : 'camlidar';
  const cams = <CameraBody paneId="single" frames={frames} pred={pred} />;
  return (
    <div className={inspectorHidden ? 'app app--ws insp-hidden' : 'app app--ws'} data-mode={mode}>
      <WorkspaceToolbar title={scene.name} sub={scene.description} mode={mode} onMode={setMode} backLabel="씬 목록으로"
        onBack={() => navigate(searchUrl(scene.datasetId))} datasetId={scene.datasetId} />
      <div className="body" id="main">
        <section className="stage" aria-label="센서 화면">
          <Hud paneId="single" onResetSplit={mode === 'camlidar' ? resetSplit : undefined} />
          <div className="viewport">
            {mode === 'cams' ? cams : (
              <Split orient={orient} ratio={splitRatio} max={SPLIT_MAX} onChange={setSplitRatio} onReset={resetSplit}
                label={orient === 'stack' ? '카메라와 3D 영역 높이 비율' : '카메라와 3D 영역 너비 비율'}
                a={cams} b={<RecordingPanel paneId="single" scene={scene} enabled />} />
            )}
          </div>
          <div className="tl-bar">
            <FrameTimeline paneId="single" samples={frames.samples} requestedIndex={frames.requestedIndex} displayedIndex={frames.displayedIndex} buffering={frames.buffering} />
          </div>
        </section>
        <Inspector paneId="single" scene={scene} frames={frames} pred={pred} hidden={inspectorHidden} />
      </div>
      <ZoomDialog paneId="single" sceneName={scene.name} frames={frames} pred={pred} />
      <DeleteDialog />
      <KeysSheet />
    </div>
  );
}
