import { useQuery, useQueryClient } from '@tanstack/react-query';
import { describeError, isApiError } from '@/api/http';
import type { LabelEdit, SampleRef, Scene } from '@/api/models';
import { labelEditsQuery } from '@/api/queries';
import { selectObject } from '@/features/workspace/actions';
import { useWorkspace, type PaneId } from '@/stores/workspace';
import { revertWithToast } from './ObjectsPanel';

const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent || '');
export const MOD = IS_MAC ? '⌘' : 'Ctrl';
const pad = (n: number) => String(n).padStart(2, '0');
const fmtHM = (t: number) => { const d = new Date(t); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };

/** History of label edits: GT edits of this scene and prediction edits of the shown job, newest first. */
export function useLabelEdits(scene: Scene, jobId: number | null) {
  return useQuery({ ...labelEditsQuery(scene.id, jobId) });
}

export function EditsPanel({ paneId, scene, samples }: { paneId: PaneId; scene: Scene; samples: SampleRef[] }) {
  const pane = useWorkspace((s) => s.panes[paneId]);
  const requestSample = useWorkspace((s) => s.requestSample);
  const setPlaying = useWorkspace((s) => s.setPlaying);
  const qc = useQueryClient();
  const q = useLabelEdits(scene, pane.resultJobId);
  const intro = (
    <p className="panel-intro">이 씬의 GT 수정{pane.resultJobId != null ? `과 작업 #${pane.resultJobId} 예측 수정` : ''}이에요. {MOD}{IS_MAC ? '' : '+'}Z로 마지막 수정을 되돌릴 수 있어요. 3D recording은 원본 박스를 보여 줘요.</p>
  );
  if (q.isPending) return <>{intro}<p className="panel-msg">불러오는 중…</p></>;
  if (q.isError) {
    const unsupported = isApiError(q.error) && (q.error.status === 404 || q.error.status === 405);
    return <>{intro}<p className="panel-msg">{unsupported ? '이 서버는 라벨 수정 기록을 제공하지 않아요.' : `기록을 불러오지 못했어요: ${describeError(q.error)}`}</p></>;
  }
  if (!q.data.length) return <>{intro}<p className="panel-msg">아직 수정한 내용이 없어요. 객체를 골라 클래스를 바꾸거나 삭제하면 여기에 남아요.</p></>;
  const frameOf = (token: string | undefined) => { const k = samples.findIndex((s) => s.token === token); return k >= 0 ? k + 1 : null; };
  const goto = (e: LabelEdit) => {
    const token = e.sampleTokens[0];
    const s = samples.find((x) => x.token === token);
    if (s) { setPlaying(paneId, false); requestSample(paneId, s.token, 'user'); }
    const key = e.targetType === 'ANNOTATION' ? (e.instanceToken ? `gt:${e.datasetId}:${e.instanceToken}` : null) : `pred:${e.jobId}:${e.targetIds[0]}`;
    if (key && e.action !== 'DELETE') selectObject(paneId, key === pane.selectedBoxKey ? null : key);
  };
  return (
    <>
      {intro}
      <ul className="hist" aria-label="수정 기록">
        {q.data.map((x) => {
          const fr = frameOf(x.sampleTokens[0]);
          const where = x.count > 1 ? `${x.count}개 프레임` : fr ? `프레임 ${fr}` : '';
          const what = x.action === 'RENAME' ? `${x.fromLabel} → ${x.toLabel}` : `${x.fromLabel} 삭제`;
          return (
            <li key={x.id} className={x.revertedAt ? 'hist-row is-reverted' : 'hist-row'}>
              <button type="button" className="hist-main" onClick={() => goto(x)} title="이 수정이 있는 프레임으로 이동">
                <span className="hist-what">{what}</span>
                <span className="hist-sub">{x.targetType === 'ANNOTATION' ? 'GT' : '예측'}{where ? ` · ${where}` : ''} · {fmtHM(x.createdAt)}</span>
              </button>
              {x.revertedAt ? <span className="done">되돌림</span>
                : x.revertible ? <button type="button" className="btn sm weak" onClick={() => void revertWithToast(qc, x.id)}>되돌리기</button>
                  : <span className="done" title="같은 객체에 나중 수정이 있어요. 최근 수정부터 되돌려 주세요">—</span>}
            </li>
          );
        })}
      </ul>
    </>
  );
}
