import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState, type KeyboardEvent } from 'react';
import type { EditScope } from '@/api/dto';
import { describeError } from '@/api/http';
import type { BoxView, Scene } from '@/api/models';
import { sceneInstancesQuery } from '@/api/queries';
import { Icon } from '@/components/Icon';
import { cameraKo } from '@/features/cameras/cameraMeta';
import type { PaneFrames } from '@/features/frames/usePaneFrames';
import { gtComparisonClass } from '@/features/objects/boxLabels';
import { objectKey } from '@/features/objects/objectKeys';
import type { PredState } from '@/features/objects/useFrameBoxes';
import { selectObject } from '@/features/workspace/actions';
import { LABEL_OPTIONS } from '@/lib/classes';
import { afterEdit, josa, renameBox, revertEdit } from '@/lib/edits/labelEdits';
import { projectBox } from '@/lib/geometry/projection';
import { useLayout } from '@/stores/layout';
import { useOverlay } from '@/stores/overlay';
import { announce, snack, toast } from '@/stores/toast';
import { useWorkspace, type PaneId } from '@/stores/workspace';

export interface ObjectRow {
  box: BoxView;
  key: string;
  cams: string[];
  dist: number | null;
}

const f2 = (v: number) => (Math.abs(v) < 0.005 ? 0 : v).toFixed(2);
const f3 = (v: number) => (Math.abs(v) < 0.0005 ? 0 : v).toFixed(3);
const short = (t: string | null) => (t ? `${t.slice(0, 8)}…` : '-');

/** Objects of the displayed frame: GT + predictions of the shown job, nearest first, with the cameras they appear in. */
export function useObjectRows(frames: PaneFrames, pred: PredState): ObjectRow[] {
  const bundle = frames.displayed;
  const ego = bundle.frame?.lidar?.vehicle ?? bundle.frame?.cameras.get('CAM_FRONT')?.vehicle ?? null;
  return useMemo(() => {
    const all: BoxView[] = [...(bundle.gt ?? []), ...(pred.kind === 'ready' ? pred.boxes : [])];
    return all.map((box) => ({
      box,
      key: objectKey(box),
      cams: bundle.cameras.filter((c) => c.camera && projectBox(c.camera, box)).map((c) => c.channel),
      dist: ego ? Math.hypot(box.center[0] - ego[0], box.center[1] - ego[1]) : null,
    })).sort((a, b) => (a.dist ?? 0) - (b.dist ?? 0));
  }, [bundle.gt, bundle.cameras, pred, ego]);
}

/** Shared edit lock so a second edit is not sent while one is in flight. */
let editBusy = false;
export async function runEdit<T>(fn: () => Promise<T>): Promise<T | undefined> {
  if (editBusy) return undefined;
  editBusy = true;
  try { return await fn(); } finally { editBusy = false; }
}

/** Revert from a toast / history / ⌘Z. */
export async function revertWithToast(qc: ReturnType<typeof useQueryClient>, editId: number): Promise<void> {
  await runEdit(async () => {
    try {
      const e = await revertEdit(editId);
      await afterEdit(qc, e);
      toast('수정을 되돌렸어요', 'ok');
    } catch (err) {
      toast(`되돌리지 못했어요: ${describeError(err)}`, 'error');
    }
  });
}

interface Props {
  paneId: PaneId;
  scene: Scene;
  frames: PaneFrames;
  pred: PredState;
  rows: ObjectRow[];
}

export function ObjectsPanel({ paneId, scene, frames, pred, rows }: Props) {
  const pane = useWorkspace((s) => s.panes[paneId]);
  const toggleHidden = useWorkspace((s) => s.toggleHidden);
  const showAll = useWorkspace((s) => s.showAllHidden);
  const filter = useLayout((s) => s.filter);
  const setFilter = useLayout((s) => s.setFilter);
  const bundle = frames.displayed;

  if (!bundle.sample) {
    return <p className="panel-msg">{frames.samplesError ? '샘플을 불러오지 못했어요.' : '불러오는 중…'}</p>;
  }
  const avail = rows.filter((r) => (r.box.source === 'GT' ? pane.layers.gt : pane.layers.pred));
  const ofType = (t: string) => avail.filter((r) => t === 'all' || (t === 'gt') === (r.box.source === 'GT'));
  const listed = ofType(filter.source).filter((r) => filter.cls === 'all' || r.box.cls === filter.cls);
  const nG = avail.filter((r) => r.box.source === 'GT').length;
  const classes = [...new Set(ofType(filter.source).map((r) => r.box.cls))].sort();

  let body: React.ReactNode;
  if (!pane.layers.gt && !pane.layers.pred) body = <p className="panel-msg">GT와 예측이 모두 숨겨져 있어요. 센서 화면 위 표시 버튼으로 다시 보이게 할 수 있어요.</p>;
  else if (!listed.length) {
    body = (
      <p className="panel-msg">
        {filter.source === 'pred' && !pane.layers.pred ? '예측 박스를 숨긴 상태예요.'
          : filter.source === 'gt' && !pane.layers.gt ? 'GT 박스를 숨긴 상태예요.'
            : filter.source === 'pred' && pred.kind === 'none' ? '표시 중인 예측 결과가 없어요. 자동 라벨링 탭에서 라벨을 생성하거나 완료된 작업을 고르세요.'
              : filter.source === 'pred' && pred.kind === 'not-in-job' ? `작업 #${pred.jobId}에는 이 프레임의 결과가 없어요.`
                : '이 프레임에 해당하는 객체가 없어요.'}
      </p>
    );
  } else {
    body = (
      <table className="otable" aria-label={`프레임 ${frames.displayedIndex + 1}의 객체`}>
        <colgroup><col style={{ width: 56 }} /><col /><col style={{ width: 66 }} /><col style={{ width: 42 }} /></colgroup>
        <thead><tr><th>구분</th><th>클래스와 카메라</th><th>거리</th><th>화면 표시</th></tr></thead>
        <tbody>
          {listed.map((r) => {
            const hid = pane.hidden.includes(r.key);
            const on = r.key === pane.selectedBoxKey;
            const gt = r.box.source === 'GT';
            const pick = () => selectObject(paneId, r.key, r.box);
            return (
              <tr key={r.box.key} className={[on ? 'is-sel' : '', hid ? 'is-hidden' : ''].join(' ').trim() || undefined} tabIndex={0} onClick={pick}
                onKeyDown={(e: KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } }}
                aria-label={`${gt ? 'GT' : '예측'} ${r.box.cls}, ${r.dist != null ? `${r.dist.toFixed(1)}미터` : '거리 정보 없음'}${r.box.edited ? ', 수정됨' : ''}${on ? ', 선택됨' : ''}${hid ? ', 숨김' : ''}`}
                data-object-key={r.key}>
                <td className="c-lead"><span className="o-ic" aria-hidden="true"><span className={`sw sw-${gt ? 'gt' : 'pred'}`} /></span></td>
                <td className="c-main">
                  <span className="c-cls" title={r.box.cls}>{r.box.cls}{r.box.edited && <i className="dot" title={`수정됨, 원래 ${r.box.baseCls}`} />}</span>
                  <span className="c-sub">{gt ? 'GT' : '예측'} · {r.cams[0] ? cameraKo(r.cams[0]) : '카메라 밖'}</span>
                </td>
                <td className="num">{r.dist != null ? `${r.dist.toFixed(1)} m` : '-'}</td>
                <td className="c-eye">
                  <button type="button" className="eye" aria-pressed={!hid} aria-label={hid ? '화면에 다시 보이기' : '화면에서 숨기기'} title={`${hid ? '다시 보이기' : '숨기기'} (H)`}
                    onClick={(e) => { e.stopPropagation(); toggleHidden(paneId, r.key); announce(hid ? '객체를 다시 보이게 했어요' : '객체를 화면에서 숨겼어요'); }}>
                    <Icon name={hid ? 'eye-off' : 'eye'} />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  return (
    <>
      <ObjectEditor key={pane.selectedBoxKey ?? "none"} paneId={paneId} scene={scene} frames={frames} rows={rows} />
      <div className="list-tools">
        <div className="seg seg--sm" role="group" aria-label="구분">
          {([['all', '전체', avail.length], ['gt', 'GT', nG], ['pred', '예측', avail.length - nG]] as const).map(([k, l, c]) => (
            <button key={k} type="button" aria-pressed={filter.source === k} onClick={() => setFilter({ source: k, cls: 'all' })}>{l} <span className="cnt">{c}</span></button>
          ))}
        </div>
        <select className="popup popup--sm" aria-label="클래스로 거르기" value={filter.cls} onChange={(e) => setFilter({ cls: e.currentTarget.value })}>
          <option value="all">모든 클래스</option>
          {classes.map((c) => <option key={c} value={c}>{c}</option>)}
          {filter.cls !== 'all' && !classes.includes(filter.cls) && <option value={filter.cls}>{filter.cls}</option>}
        </select>
      </div>
      {(pred.kind === 'error' || bundle.gtError != null) && (
        <div className="obj-warn" role="alert">
          {bundle.gtError != null && <span>GT를 불러오지 못했어요 ({describeError(bundle.gtError)}).</span>}
          {pred.kind === 'error' && <span>예측 결과를 불러오지 못했어요 ({describeError(pred.error)}). <button type="button" className="link" onClick={pred.refetch}>다시 불러오기</button></span>}
        </div>
      )}
      <div className="obj-scroll">{body}</div>
      {pane.hidden.length > 0 && (
        <p className="obj-foot">숨긴 객체 {pane.hidden.length}개<button type="button" className="link" onClick={() => showAll(paneId)}>모두 보이기</button></p>
      )}
    </>
  );
}

function ObjectEditor({ paneId, scene, frames, rows }: { paneId: PaneId; scene: Scene; frames: PaneFrames; rows: ObjectRow[] }) {
  const pane = useWorkspace((s) => s.panes[paneId]);
  const toggleHidden = useWorkspace((s) => s.toggleHidden);
  const openOverlay = useOverlay((s) => s.open);
  const qc = useQueryClient();
  const [allFrames, setAllFrames] = useState(true);
  const [busy, setBusy] = useState(false);
  const sel = pane.selectedBoxKey;
  const row = rows.find((r) => r.key === sel);
  const instances = useQuery({ ...sceneInstancesQuery(scene.id), enabled: row?.box.source === 'GT' && !!row.box.instanceToken });
  const close = <button type="button" className="icon-btn" onClick={() => selectObject(paneId, null)} aria-label="선택 해제" title="선택 해제 (Esc)"><Icon name="close" /></button>;

  if (!sel) {
    return (
      <section className="editor editor--empty" aria-label="선택한 객체">
        <span className="empty-ic" aria-hidden="true"><Icon name="cube" /></span>
        <p>화면이나 목록에서 객체를 고르면 클래스를 바꾸거나 지울 수 있어요.</p>
      </section>
    );
  }
  if (!row) {
    const gtSel = sel.startsWith('gt:');
    return (
      <section className="editor" aria-label="선택한 객체" data-testid="object-detail">
        <div className="ed-top"><span className="ed-kicker">{gtSel ? '선택한 GT 객체' : '선택한 예측 박스'}</span>{close}</div>
        <p className="ed-meta">{gtSel ? '이 프레임에는 없어요. 재생 막대 위 노란 표시가 이 객체가 나오는 프레임이에요.' : '예측 박스는 프레임마다 따로 저장돼서 다른 프레임으로 이어지지 않아요.'}</p>
      </section>
    );
  }
  const { box } = row;
  const gt = box.source === 'GT';
  const hid = pane.hidden.includes(row.key);
  const n = gt && box.instanceToken ? instances.data?.get(box.instanceToken)?.size ?? null : 1;
  const cams = row.cams.length ? (row.cams.length > 2 ? `${cameraKo(row.cams[0]!)} 외 ${row.cams.length - 1}곳` : row.cams.map(cameraKo).join(', ')) : '카메라에 안 보여요';
  const sample = frames.displayed.sample;
  const options: string[] = (LABEL_OPTIONS as readonly string[]).includes(box.cls) ? [...LABEL_OPTIONS] : [box.cls, ...LABEL_OPTIONS];
  const cmp = gt ? gtComparisonClass(box, pane.classMode) : null;

  const rename = async (label: string) => {
    if (label === box.cls) return;
    const scope: EditScope = gt && allFrames && box.instanceToken ? 'INSTANCE' : 'SAMPLE';
    setBusy(true);
    announce('저장 중…');
    await runEdit(async () => {
      try {
        const e = await renameBox(box, label, scope);
        await afterEdit(qc, e);
        snack(`${josa(box.cls, '을/를')} ${josa(label, '으로/로')} 바꿨어요${e.count > 1 ? ` (${e.count}개 프레임)` : ''}`, '되돌리기', () => void revertWithToast(qc, e.id));
      } catch (err) {
        toast(`저장하지 못했어요: ${describeError(err)}`, 'error');
      }
    });
    setBusy(false);
  };

  return (
    <section className="editor" aria-label="선택한 객체" data-testid="object-detail">
      <div className="ed-top">
        <span className="ed-kicker"><span className={`sw sw-${gt ? 'gt' : 'pred'}`} aria-hidden="true" />{gt ? 'GT' : `예측 · 작업 #${box.jobId}`}</span>
        {close}
      </div>
      <h3 className="ed-label">{box.cls}</h3>
      <p className="ed-meta">{row.dist != null ? `${row.dist.toFixed(1)} m · ` : ''}{cams}</p>
      {box.edited && <p className="ed-orig"><i className="dot" aria-hidden="true" />원래 클래스 {box.baseCls}에서 바꿨어요</p>}
      <div className="ed-form">
        <div className="ed-row">
          <label className="ed-row-l" htmlFor={`ed-cls-${paneId}`}>클래스</label>
          <select id={`ed-cls-${paneId}`} className="popup" value={box.cls} disabled={busy} onChange={(e) => void rename(e.currentTarget.value)}>
            {options.map((c) => <option key={c} value={c} disabled={!(LABEL_OPTIONS as readonly string[]).includes(c)}>{c}</option>)}
          </select>
        </div>
        {gt && box.instanceToken && (
          <div className="ed-row">
            <label className="ed-row-l" htmlFor={`ed-scope-${paneId}`}>모든 프레임에 적용<span className="ed-row-s">이 객체가 나오는 프레임 ({n ?? '…'}개)</span></label>
            <input type="checkbox" role="switch" className="switch" id={`ed-scope-${paneId}`} checked={allFrames} onChange={(e) => setAllFrames(e.currentTarget.checked)} />
          </div>
        )}
      </div>
      <div className="ed-actions">
        <button type="button" className="btn" onClick={() => toggleHidden(paneId, row.key)}>{hid ? '다시 보이기' : '숨기기'}</button>
        <button type="button" className="btn destructive" disabled={busy} data-testid="ask-delete"
          onClick={() => openOverlay({ kind: 'confirm', paneId, box, instanceFrames: n ?? 1, frameIndex: frames.displayedIndex })}>삭제</button>
      </div>
      <details className="disclosure ed-more">
        <summary>좌표와 ID</summary>
        <dl>
          <dt>{gt ? 'annotation id' : 'prediction id'}</dt><dd>{box.id}</dd>
          {gt ? (
            <>
              <dt>instanceToken</dt><dd title={box.instanceToken ?? ''}>{short(box.instanceToken)}</dd>
              <dt>원본 category</dt><dd>{box.label ?? '클래스 정보 없음'}</dd>
              <dt>{pane.classMode}종 비교 분류</dt><dd>{cmp ?? '비교 분류 없음'}</dd>
              <dt>LiDAR 점 수</dt><dd>{box.numLidarPts ?? '-'}</dd>
            </>
          ) : (
            <>
              <dt>detectionName</dt><dd>{box.label}</dd>
              <dt>속도 X, Y (m/s)</dt><dd>{box.velocityXY?.map(f2).join(', ') ?? '-'}</dd>
              <dt>sampleToken</dt><dd title={sample?.token}>{short(sample?.token ?? null)}</dd>
            </>
          )}
          <dt>중심 (WORLD, m)</dt><dd>{box.center.map(f2).join(', ')}</dd>
          <dt>크기 W/L/H (m)</dt><dd>{box.sizeWLH.map(f2).join(', ')}</dd>
          <dt>회전 W, X, Y, Z</dt><dd>{[box.rotation.w, box.rotation.x, box.rotation.y, box.rotation.z].map(f3).join(', ')}</dd>
          <dt>timestamp (µs)</dt><dd>{sample?.timestampUs ?? '-'}</dd>
        </dl>
      </details>
    </section>
  );
}
