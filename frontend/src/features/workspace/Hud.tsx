import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { jobResultsQuery, sceneJobsQuery } from '@/api/queries';
import { Icon } from '@/components/Icon';
import { compareJobs } from '@/features/objects/compareBoxes';
import { compareTagOf } from '@/features/objects/useFrameBoxes';
import { announce } from '@/stores/toast';
import { useWorkspace, type LayerKey, type PaneId } from '@/stores/workspace';

const META: Record<LayerKey, { label: string; key: string; ko: string }> = {
  gt: { label: 'GT', key: 'G', ko: 'GT 박스' },
  pred: { label: '예측', key: 'P', ko: '예측 박스' },
  names: { label: '클래스 이름', key: '', ko: '클래스 이름' },
  cmp: { label: '비교', key: '', ko: '비교 박스' },
};

export function toggleLayerAnnounced(paneId: PaneId, layer: LayerKey): void {
  const st = useWorkspace.getState();
  st.toggleLayer(paneId, layer);
  announce(`${META[layer].ko} ${useWorkspace.getState().panes[paneId].layers[layer] ? '보이기' : '숨기기'}`);
}

export function LayerToggle({ paneId, layer }: { paneId: PaneId; layer: LayerKey }) {
  const on = useWorkspace((s) => s.panes[paneId].layers[layer]);
  const m = META[layer];
  return (
    <button type="button" className="hud-tog" aria-pressed={on} data-layer={layer} onClick={() => toggleLayerAnnounced(paneId, layer)}
      title={`${m.label} ${on ? '숨기기' : '보이기'}${m.key ? ` (${m.key})` : ''}${layer === 'cmp' ? ' · 카메라에 적용' : layer !== 'names' ? ' · 카메라·3D·객체 목록에 적용' : ' · 카메라·3D에 적용'}`}>
      {layer === 'names' ? <Icon name="text" /> : <><Icon name="eye" className="i-on" /><Icon name="eye-off" className="i-off" /></>}
      {layer !== 'names' && <span className={`sw sw-${layer}`} aria-hidden="true" />}
      <span>{m.label}</span>
      {m.key && <kbd aria-hidden="true">{m.key}</kbd>}
    </button>
  );
}

interface Props {
  paneId: PaneId;
  /** Compare mode: the toggles apply to the work-target pane, shown by its tag. */
  compareTag?: 'A' | 'B';
  sync?: { on: boolean; set: (on: boolean) => void };
  onResetSplit?: () => void;
  onExitCompare?: () => void;
}

/** Display bar on top of the sensor card. */
export function Hud({ paneId, compareTag, sync, onResetSplit, onExitCompare }: Props) {
  const hidden = useWorkspace((s) => s.panes[paneId].hidden.length);
  const showAll = useWorkspace((s) => s.showAllHidden);
  return (
    <div className="hud" role="toolbar" aria-label={compareTag ? `씬 ${compareTag} 표시` : '표시'}>
      {compareTag && <span className="hud-pane" title={`표시 설정은 작업 대상인 씬 ${compareTag}에 적용돼요`} aria-hidden="true">{compareTag}</span>}
      <div className="hud-group">
        <LayerToggle paneId={paneId} layer="gt" />
        <LayerToggle paneId={paneId} layer="pred" />
        <LayerToggle paneId={paneId} layer="names" />
      </div>
      <CompareJobPicker paneId={paneId} />
      {hidden > 0 && (
        <span className="hud-note">숨긴 객체 {hidden}개<button type="button" className="hud-link" onClick={() => { showAll(paneId); announce('숨긴 객체를 모두 다시 보이게 했어요'); }}>모두 보이기</button></span>
      )}
      <span className="hud-gap" />
      {sync && (
        <label className="hud-switch" title="각 씬의 시간 범위에서 같은 비율 위치로 맞춰요. 같은 촬영 시각이라는 뜻은 아니에요.">
          <input type="checkbox" role="switch" className="switch switch--media" checked={sync.on} onChange={(e) => sync.set(e.currentTarget.checked)} />재생 위치 맞추기
        </label>
      )}
      {onResetSplit && <button type="button" className="hud-btn icon" data-action="reset-split" onClick={onResetSplit} aria-label="화면 비율 초기화" title="화면 비율 초기화"><Icon name="reset" /></button>}
      {onExitCompare && <button type="button" className="hud-btn" onClick={onExitCompare}>비교 닫기</button>}
    </div>
  );
}

/**
 * Picks a second completed job of the scene whose boxes are drawn over the shown predictions as green dashes (e.g. the
 * VESPA ver2 run next to the original). The swatch part toggles them; the note sums up the whole-job difference.
 * Hidden while the scene has no other completed job.
 */
function CompareJobPicker({ paneId }: { paneId: PaneId }) {
  const sceneId = useWorkspace((s) => s.panes[paneId].sceneId);
  const resultJobId = useWorkspace((s) => s.panes[paneId].resultJobId);
  const compareJobId = useWorkspace((s) => s.panes[paneId].compareJobId);
  const on = useWorkspace((s) => s.panes[paneId].layers.cmp);
  const setCompareJob = useWorkspace((s) => s.setCompareJob);
  const jobs = useQuery({ ...sceneJobsQuery(sceneId ?? -1), enabled: sceneId != null });
  const active = compareJobId != null && compareJobId !== resultJobId ? compareJobId : null;
  const base = useQuery({ ...jobResultsQuery(resultJobId ?? -1), enabled: active != null && resultJobId != null });
  const other = useQuery({ ...jobResultsQuery(active ?? -1), enabled: active != null });
  const counts = useMemo(() => (base.data && other.data ? compareJobs(base.data, other.data) : null), [base.data, other.data]);
  const done = (jobs.data ?? []).filter((j) => j.status === 'COMPLETED' && j.jobId !== resultJobId);
  if (!done.length && compareJobId == null) return null;
  const name = (id: number, variant: string | null) => (variant == null ? `#${id}` : `#${id} · ${variant === '' ? 'VESPA' : compareTagOf(id, variant)}`);
  return (
    <div className="hud-cmp" role="group" aria-label="비교 작업">
      <button type="button" className="hud-cmp-tog" aria-pressed={active != null && on} disabled={active == null}
        title={active == null ? '비교할 작업을 고르세요' : `비교 박스 ${on ? '숨기기' : '보이기'} · 카메라에 적용`}
        onClick={() => toggleLayerAnnounced(paneId, 'cmp')}>
        <span className="sw sw-cmp" aria-hidden="true" />비교
      </button>
      <select aria-label="비교할 작업" value={compareJobId ?? ''} onChange={(e) => {
        const v = e.currentTarget.value ? Number(e.currentTarget.value) : null;
        setCompareJob(paneId, v);
        if (v != null && !useWorkspace.getState().panes[paneId].layers.cmp) useWorkspace.getState().toggleLayer(paneId, 'cmp');
        announce(v == null ? '비교를 껐어요' : `작업 #${v}의 박스를 초록 점선으로 겹쳐 보여요`);
      }}>
        <option value="">없음</option>
        {compareJobId != null && !done.some((j) => j.jobId === compareJobId) && <option value={compareJobId}>#{compareJobId}</option>}
        {done.map((j) => <option key={j.jobId} value={j.jobId}>{name(j.jobId, j.variant)}</option>)}
      </select>
      {active != null && counts && (
        <span className="hud-cmp-sum" title={`작업 #${resultJobId} 대비 #${active}, 전체 프레임. 같음 = 같은 클래스·위치·크기·방향(5 cm 이내). 같은 박스는 태그를 생략해요.`}>
          같음 {counts.same} · 달라짐 {counts.changed} · 추가 {counts.added} · 없어짐 {counts.removed}
        </span>
      )}
      {compareJobId != null && compareJobId === resultJobId && <span className="hud-cmp-sum">표시 중인 작업과 같아요</span>}
    </div>
  );
}
