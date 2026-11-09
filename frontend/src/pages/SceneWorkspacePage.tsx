import { ArrowLeft, ExternalLink, Grid3x3, Link2, PanelRightClose, PanelRightOpen, SplitSquareHorizontal, Columns2 } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router';
import { describeError } from '@/api/http';
import { compareUrl, parseWorkspace, searchUrl, workspaceUrl, type WorkspaceView } from '@/app/urls';
import { StateBox } from '@/components/StateBox';
import { usePaneFrames } from '@/features/frames/usePaneFrames';
import { JobPanel } from '@/features/labeling/JobPanel';
import { ObjectInspector } from '@/features/objects/ObjectInspector';
import { usePredictions } from '@/features/objects/useFrameBoxes';
import { useScene } from '@/features/scenes/useScene';
import { FrameTimeline } from '@/features/timeline/FrameTimeline';
import { usePlaybackLifecycle, useWorkspaceShortcuts } from '@/features/workspace/hooks';
import { SinglePaneView } from '@/features/workspace/PaneView';
import { DataOriginBadge } from '@/features/system/DataOriginBadge';
import { useLayout } from '@/stores/layout';
import { toast } from '@/stores/toast';
import { useWorkspace } from '@/stores/workspace';
import { cn } from '@/lib/utils';

export default function SceneWorkspacePage() {
  const { sceneId: sceneParam } = useParams();
  const [sp] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const params = parseWorkspace(sceneParam, sp);
  const openScene = useWorkspace((s) => s.openScene);
  const pane = useWorkspace((s) => s.panes.single);
  const collapsed = useLayout((s) => s.inspectorCollapsed);
  const setCollapsed = useLayout((s) => s.setInspectorCollapsed);
  const { scene, isPending, error, notFound, refetch } = useScene(params.datasetId, params.sceneId);

  // URL → store, except for URLs this page wrote itself (prevents replace/parse loops).
  const written = useRef<string | null>(null);
  useEffect(() => {
    if (location.search === written.current) return;
    if (params.datasetId == null || params.sceneId == null) return;
    openScene('single', { datasetId: params.datasetId, sceneId: params.sceneId, sampleToken: params.sample, jobId: params.job });
  }, [location.search, params.datasetId, params.sceneId, params.sample, params.job, openScene]);

  const frames = usePaneFrames('single');
  const pred = usePredictions(pane.resultJobId, frames.displayed.sample);
  usePlaybackLifecycle();
  useWorkspaceShortcuts('single', frames);

  // Store → URL (replace, no history spam). Not while playing or while a frame is still loading.
  useEffect(() => {
    if (pane.playing || frames.buffering || pane.datasetId == null || pane.sceneId == null || !pane.displayedSampleToken) return;
    const path = window.location.pathname;
    const t = window.setTimeout(() => {
      // The user may have navigated away meanwhile (route transitions keep this page mounted briefly): never undo that.
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

  const setView = (view: WorkspaceView) => {
    if (pane.datasetId == null || pane.sceneId == null) return;
    navigate(workspaceUrl({ datasetId: pane.datasetId, sceneId: pane.sceneId, sample: pane.displayedSampleToken, job: pane.jobId, view }));
  };
  const goCompare = () => {
    if (pane.datasetId == null || pane.sceneId == null) return;
    const side = { datasetId: pane.datasetId, sceneId: pane.sceneId, sample: pane.displayedSampleToken, job: pane.jobId };
    navigate(compareUrl({ A: side, B: { ...side, job: null }, sync: false, active: 'A' }));
  };
  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast('현재 씬·프레임·작업이 담긴 링크를 복사했어요', 'ok');
    } catch {
      toast('링크를 복사하지 못했어요. 주소창의 URL을 사용해 주세요', 'error');
    }
  };

  if (params.datasetId == null || params.sceneId == null) {
    return (
      <div className="page-state">
        <StateBox kind="error" title="링크에 데이터셋 또는 씬 정보가 없어요" actions={<Link className="btn btn--weak" to={searchUrl(null)}>씬 목록에서 고르기</Link>}>
          공유 링크에는 dataset과 씬 번호가 함께 있어야 해요.
        </StateBox>
      </div>
    );
  }
  if (error || notFound) {
    return (
      <div className="page-state">
        <StateBox kind="error" title={notFound ? '이 데이터셋에서 씬을 찾을 수 없어요' : '씬 정보를 불러오지 못했어요'}
          actions={<>{!notFound && <button type="button" className="btn btn--weak" onClick={() => void refetch()}>다시 불러오기</button>}<Link className="btn btn--ghost" to={searchUrl(params.datasetId)}>씬 목록으로</Link></>}>
          {notFound ? `dataset ${params.datasetId}에 scene ${params.sceneId}이(가) 없어요.` : describeError(error)}
        </StateBox>
      </div>
    );
  }
  if (isPending || !scene) return <div className="page-state" role="status"><span className="spin" aria-hidden="true" /></div>;

  const frameNumber = frames.displayedIndex + 1;
  return (
    <div className="app app--ws" data-view={params.view}>
      <header className="topbar">
        <Link className="btn btn--ghost btn--sm" to={searchUrl(scene.datasetId)}><ArrowLeft className="icon" aria-hidden="true" /><span className="lbl">씬 목록</span></Link>
        <div className="crumb">
          <h1 className="crumb-title">{scene.name}</h1>
          <span className="crumb-sub">{scene.description}</span>
        </div>
        <DataOriginBadge datasetId={scene.datasetId} />
        <div className="seg seg--modes" role="group" aria-label="보기 모드">
          <button type="button" aria-pressed={params.view === 'split'} onClick={() => setView('split')}><SplitSquareHorizontal className="icon" aria-hidden="true" /><span className="lbl">카메라 + LiDAR</span></button>
          <button type="button" aria-pressed={params.view === 'six'} onClick={() => setView('six')}><Grid3x3 className="icon" aria-hidden="true" /><span className="lbl">6개 카메라</span></button>
          <button type="button" aria-pressed={false} onClick={goCompare}><Columns2 className="icon" aria-hidden="true" /><span className="lbl">두 씬 비교</span></button>
        </div>
        <div className="topbar-end">
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => void copyLink()} title="현재 씬, 프레임, 작업이 담긴 링크"><Link2 className="icon" aria-hidden="true" /><span className="lbl">링크 복사</span></button>
          <a className="btn btn--ghost btn--sm" href={window.location.href} target="_blank" rel="noopener" title="새 탭에서 열기"><ExternalLink className="icon" aria-hidden="true" /><span className="lbl">새 탭</span></a>
          <button type="button" className="btn btn--ghost btn--sm btn--icon collapse-toggle" onClick={() => setCollapsed(!collapsed)} aria-pressed={collapsed} aria-label={collapsed ? '오른쪽 패널 펼치기' : '오른쪽 패널 접기'} title={collapsed ? '오른쪽 패널 펼치기' : '오른쪽 패널 접기'}>
            {collapsed ? <PanelRightOpen className="icon" aria-hidden="true" /> : <PanelRightClose className="icon" aria-hidden="true" />}
          </button>
        </div>
      </header>
      <main className={cn('ws', collapsed && 'is-collapsed')}>
        <SinglePaneView scene={scene} data={{ frames, pred }} view={params.view} />
        <aside className="inspector" aria-label="자동 라벨링과 객체 정보">
          <JobPanel paneId="single" scene={scene} samples={frames.samples} />
          {pane.resultJobId != null && <Link className="btn btn--primary" to={`/labels?job=${pane.resultJobId}`}>이 결과 수정 · 저장 · 다운로드</Link>}
          <ObjectInspector paneId="single" bundle={frames.displayed} frameNumber={frameNumber} pred={pred} />
        </aside>
      </main>
      <footer className="tl-bar">
        <FrameTimeline paneId="single" samples={frames.samples} requestedIndex={frames.requestedIndex} displayedIndex={frames.displayedIndex} buffering={frames.buffering} />
      </footer>
    </div>
  );
}
