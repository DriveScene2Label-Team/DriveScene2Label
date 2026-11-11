import { useQuery } from '@tanstack/react-query';
import { Box, RefreshCw, ShieldAlert, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { ClassMode } from '@/api/dto';
import { describeError, isApiError } from '@/api/http';
import type { SampleRef, Scene } from '@/api/models';
import { jobResultsQuery, jobStatusQuery } from '@/api/queries';
import { CLASS_COLORS, CLASS_MODES } from '@/lib/classes';
import { elapsedMs, formatElapsed } from '@/lib/jobs/createJob';
import { findReceipt, receiptsForScene, unverifiedReceiptsForScene } from '@/lib/jobs/receipts';
import { dismissJobSubmission, newJobSnapshot, submitJob, useSubmissions } from '@/lib/jobs/submissions';
import { errorGuide } from '@/lib/errorCodes';
import { useNow } from '@/hooks/useNow';
import { capabilityMessage, stateLabel, type Capability } from '@/api/system';
import { useSystemStatus } from '@/features/system/useSystemStatus';
import { useServer } from '@/stores/server';
import { useWorkspace, type PaneId } from '@/stores/workspace';
import { pollInterval, STATUS_KO, verifyJob } from './jobLogic';
import { useReceipts } from './useReceipts';
import { PostprocessPanel } from './PostprocessPanel';

interface Props {
  paneId: PaneId;
  scene: Scene;
  samples: SampleRef[];
  /** Compare mode shows which pane (A/B) the actions apply to. */
  paneLabel?: 'A' | 'B';
}

const fmtClock = (t: number) => {
  const d = new Date(t);
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':');
};

export function JobPanel({ paneId, scene, samples, paneLabel }: Props) {
  const pane = useWorkspace((s) => s.panes[paneId]);
  const watchJob = useWorkspace((s) => s.watchJob);
  const showResult = useWorkspace((s) => s.showResult);
  const setClassMode = useWorkspace((s) => s.setClassMode);
  const scope = useServer((s) => s.scope);
  const receipts = useReceipts();
  const sceneReceipts = useMemo(() => receiptsForScene(receipts, scope, scene.datasetId, scene.token), [receipts, scope, scene.datasetId, scene.token]);
  const system = useSystemStatus(scene.datasetId);
  const vespa = system.capability('vespa');
  const sampleTokens = useMemo(() => new Set(samples.map((s) => s.token)), [samples]);
  const jobId = pane.jobId;

  // The pane may still hold the previous scene for one render after navigation; act only on a matching pane.
  const paneMatches = pane.datasetId === scene.datasetId && pane.sceneId === scene.id;
  // Restore: no job selected → the newest receipt of this scene on this server (shared by every pane showing the scene).
  useEffect(() => {
    if (paneMatches && jobId == null && sceneReceipts[0]) watchJob(paneId, sceneReceipts[0].jobId);
  }, [paneMatches, pane.generation, jobId, sceneReceipts, paneId, watchJob]);

  const statusQ = useQuery({
    ...jobStatusQuery(jobId ?? -1),
    enabled: jobId != null,
    refetchInterval: (q) => pollInterval(q.state.data, q.state.status === 'error'),
    refetchIntervalInBackground: false,
  });
  const status = statusQ.data;
  const completed = status?.status === 'COMPLETED';
  const resultsQ = useQuery({ ...jobResultsQuery(jobId ?? -1), enabled: jobId != null && completed });
  const receipt = jobId != null ? findReceipt(receipts, scope, jobId) : undefined;
  const ownership = jobId != null ? verifyJob(scene, sampleTokens, status, receipt, resultsQ.data) : null;

  useEffect(() => {
    if (paneMatches && jobId != null && completed && ownership?.kind === 'verified') showResult(paneId, jobId);
  }, [paneMatches, jobId, completed, ownership?.kind, paneId, showResult]);

  const active = status?.status === 'PENDING' || status?.status === 'RUNNING';
  const now = useNow(active ? 1000 : null);

  // In-flight requests made from this pane for this scene in this UI context (they outlive this component).
  const submission = useSubmissions((st) => Object.values(st.jobs).find((j) =>
    j.snapshot.paneId === paneId && j.snapshot.sceneId === scene.id && j.snapshot.instanceId === scope && j.snapshot.generation === pane.generation));
  const posting = submission?.status === 'pending';
  const failedPost = submission?.status === 'error' ? submission : undefined;
  const lostResponse = !!failedPost && isApiError(failedPost.error) && failedPost.error.transient;
  const currentScope = () => useServer.getState().scope;
  const startNewRun = () => {
    if (failedPost) dismissJobSubmission(failedPost.snapshot.idempotencyKey);
    const snapshot = newJobSnapshot({
      instanceId: scope, datasetId: scene.datasetId, datasetChecksum: system.status?.dataset?.metadataChecksum ?? null,
      sceneId: scene.id, sceneToken: scene.token, sceneName: scene.name, paneId, generation: pane.generation,
    }, pane.classMode);
    void submitJob(snapshot, currentScope);
  };
  const resendSame = () => { if (failedPost) void submitJob(failedPost.snapshot, currentScope); };

  const busy = posting || (active && ownership?.kind !== 'mismatch');
  const blocked = !vespa.canExecute;
  const label = posting ? '요청 보내는 중' : busy ? '작업 진행 중' : paneLabel ? `씬 ${paneLabel} 전체 라벨 생성` : '씬 전체 라벨 생성';
  const guide = errorGuide(status?.errorCode);
  const remote = vespa.executor === 'ssh';

  return (
    <>
      <section className="insp-sec" aria-labelledby={`job-h-${paneId}`}>
        <div className="sec-head"><h2 id={`job-h-${paneId}`}>자동 라벨링</h2><span className="sec-aside">VESPA</span></div>
        <div className="target">
          {paneLabel ? <span className={`pane-dot pane-dot--${paneLabel}`}>{paneLabel}</span> : <Box className="icon" aria-hidden="true" />}
          <div>
            <div className="target-name">{scene.name}</div>
            <div className="target-sub">씬 전체 {scene.nbrSamples}개 프레임에 실행해요</div>
          </div>
        </div>
        <div className="field">
          <div className="field-label"><span id={`cm-${paneId}`}>클래스 모드</span><span className="dim">다음 실행에 적용</span></div>
          <div className="seg seg--full" role="radiogroup" aria-labelledby={`cm-${paneId}`}>
            {([1, 3, 8] as ClassMode[]).map((m) => (
              <button key={m} type="button" role="radio" aria-checked={pane.classMode === m} onClick={() => setClassMode(paneId, m)}>{m}개 클래스</button>
            ))}
          </div>
          <div className="class-chips">
            {CLASS_MODES[pane.classMode].map((c) => <span key={c} className="cls-chip"><i className="cls-dot" style={{ ['--c' as string]: CLASS_COLORS[c] }} />{c}</span>)}
          </div>
        </div>
        <ReadinessBox paneId={paneId} vespa={vespa} last={system.lastKnown('vespa')} lastChecked={system.lastChecked}
          refreshing={system.refreshing} onRefresh={() => void system.refresh()} onRecheck={() => void system.refetch()} />
        <button type="button" className="btn btn--primary btn--block" onClick={startNewRun} disabled={busy || blocked} data-testid={`run-job-${paneId}`}>
          {busy ? <span className="spin" aria-hidden="true" /> : <Sparkles className="icon" aria-hidden="true" />}{label}
        </button>
        {busy && !posting && <p className="help">진행 중인 작업이 끝나면 다시 실행할 수 있어요.</p>}
        {failedPost && (
          <div className={lostResponse ? 'alert alert--warn' : 'alert'} role="alert">
            {lostResponse ? (
              <>
                <b>요청 결과를 확인하지 못했어요</b>
                서버가 요청을 받았을 수 있어요. 같은 요청을 다시 보내면 이미 만들어진 작업이 있을 때 그 작업을 그대로 돌려받아요.
                <span className="mono">{describeError(failedPost.error)}</span>
                <button type="button" className="btn btn--sm btn--weak" onClick={resendSame} disabled={posting}><RefreshCw className="icon" aria-hidden="true" />같은 요청 다시 보내기</button>
              </>
            ) : (
              <>
                <b>작업을 만들지 못했어요</b>
                <span className="mono">{describeError(failedPost.error)}</span>
              </>
            )}
          </div>
        )}
      </section>

      <section className="insp-sec" aria-labelledby={`st-h-${paneId}`}>
        <div className="sec-head">
          <h2 id={`st-h-${paneId}`}>작업 상태</h2>
          {active && <span className="sec-aside">3초마다 확인</span>}
        </div>
        {jobId == null ? (
          <p className="empty-note">아직 연결된 작업이 없어요. 라벨을 생성하면 상태와 경과 시간을 여기서 볼 수 있어요.</p>
        ) : (
          <div className="job" aria-live="polite" data-testid={`job-card-${paneId}`}>
            <div className="job-row">
              {statusQ.isPending ? (
                <span className="status status--UNKNOWN"><i />확인 중</span>
              ) : status ? (
                <span className={`status status--${status.status}`} data-status={status.status}><i />{STATUS_KO[status.status]}</span>
              ) : (
                <span className="status status--OFFLINE"><i />확인할 수 없음</span>
              )}
              <span className="job-code">작업 #{jobId}</span>
            </div>

            {statusQ.isError && (isApiError(statusQ.error) && statusQ.error.status === 404 ? (
              <div className="alert" role="alert">
                <b>작업을 찾을 수 없어요</b>
                링크의 작업 번호가 이 서버에 없어요.
                <span className="mono">job {jobId}</span>
                <button type="button" className="btn btn--sm btn--weak" onClick={() => watchJob(paneId, null)}>연결 해제</button>
              </div>
            ) : (
              <div className="alert alert--warn" role="status">
                <b>연결을 확인할 수 없어요</b>
                상태를 조회하지 못했어요. 작업 자체가 실패했다는 뜻은 아니에요.
                <span className="mono">{describeError(statusQ.error)}{statusQ.dataUpdatedAt ? ` · 마지막 확인 ${fmtClock(statusQ.dataUpdatedAt)}` : ''}</span>
                <button type="button" className="btn btn--sm btn--weak" onClick={() => void statusQ.refetch()}><RefreshCw className="icon" aria-hidden="true" />다시 조회</button>
              </div>
            ))}

            {ownership?.kind === 'mismatch' && (
              <div className="alert" role="alert"><b>이 씬의 작업이 아니에요</b>{ownership.reason}. 결과를 이 씬에 표시하지 않아요.</div>
            )}
            {ownership?.kind === 'unverified' && status && (
              <p className="result-note dim">작업 대상 확인 필요 · 서버 상태 응답과 이 브라우저의 실행 기록으로는 이 씬의 작업인지 아직 확인할 수 없어요.{completed ? '' : ' 완료 후 결과 프레임으로 확인해요.'}</p>
            )}

            {active && (
              <>
                <div className={status.status === 'PENDING' ? 'indet indet--pending' : 'indet'} />
                <p className="help">
                  {status.status === 'PENDING' ? '작업 대기열에 있어요.' : remote ? '원격 클러스터에서 처리 중이에요. 대기열 대기와 실제 계산 단계는 구분해 알 수 없어요.' : 'VESPA가 씬 전체를 처리하고 있어요.'} 진행률은 제공되지 않아 단계나 퍼센트는 표시하지 않아요.
                </p>
              </>
            )}

            {status?.status === 'FAILED' && (
              <div className="alert" role="alert" data-error-code={status.errorCode ?? ''}>
                <b>{guide?.title ?? '작업이 실패했어요'}</b>
                {guide ? guide.action : '원인을 확인한 뒤 새 작업으로 다시 실행해 주세요.'} GT와 이전 결과는 그대로 남아 있어요.
                <span className="mono">{status.errorCode ? `${status.errorCode} · ` : ''}{status.errorMessage || '오류 메시지 없음'}</span>
                <button type="button" className="btn btn--sm btn--weak" onClick={startNewRun} disabled={posting || blocked}>
                  <RefreshCw className="icon" aria-hidden="true" />{guide?.environment ? '환경 확인 후 새 작업으로 다시 실행' : '새 작업으로 다시 실행'}
                </button>
                {blocked && <span className="help">실행 환경이 준비되지 않아 다시 실행할 수 없어요.</span>}
              </div>
            )}

            {completed && (
              resultsQ.isPending ? <p className="result-note">결과를 불러오고 있어요</p>
                : resultsQ.isError ? (
                  <div className="alert alert--warn" role="alert">
                    <b>결과를 불러오지 못했어요</b>
                    작업은 완료되었어요. 결과만 다시 읽어요(새 작업을 만들지 않아요).
                    <span className="mono">{describeError(resultsQ.error)}</span>
                    <button type="button" className="btn btn--sm btn--weak" onClick={() => void resultsQ.refetch()}><RefreshCw className="icon" aria-hidden="true" />결과 다시 불러오기</button>
                  </div>
                ) : resultsQ.data && (
                  <p className="result-note">
                    예측 박스 {resultsQ.data.boxCount.toLocaleString('ko-KR')}개 · 처리 프레임 {resultsQ.data.sampleTokens.size}개
                    {resultsQ.data.boxCount === 0 && ' · 검출된 박스가 없어요'}
                  </p>
                )
            )}

            {pane.resultJobId != null && pane.resultJobId !== jobId && (
              <p className="result-note dim">지금은 이전 작업 #{pane.resultJobId}의 결과를 보여 주고 있어요.</p>
            )}

            {status && (
              <dl className="kv">
                <dt>경과 시간</dt><dd>{status.startedAt || status.completedAt ? formatElapsed(elapsedMs(status, now)) : '시작 전'}</dd>
                <dt>클래스 모드</dt><dd>{status.classMode ?? receipt?.classMode ?? '확인 불가'}</dd>
                <dt>생성 시각</dt><dd>{fmtClock(status.createdAt)}</dd>
                {status.completedAt && <><dt>완료 시각</dt><dd>{fmtClock(status.completedAt)}</dd></>}
              </dl>
            )}
          </div>
        )}
        {completed && ownership?.kind === 'verified' && resultsQ.data && <PostprocessPanel key={resultsQ.data.jobId} paneId={paneId} scene={scene} samples={samples} results={resultsQ.data} disabled={blocked || !paneMatches} />}
        <JobHistory paneId={paneId} jobIds={sceneReceipts.map((r) => r.jobId)} current={jobId} />
        <LegacyNote paneId={paneId} count={unverifiedReceiptsForScene(receipts, scene.datasetId, scene.token).length} />
        <JobLookup onOpen={(id) => watchJob(paneId, id)} />
      </section>
    </>
  );
}

function LegacyNote({ paneId, count }: { paneId: PaneId; count: number }) {
  if (!count) return null;
  return (
    <p className="help" data-testid={`legacy-receipts-${paneId}`}>
      이전 버전에서 저장된 이 씬의 실행 기록 {count}건은 어느 서버(DB)의 작업인지 확인할 수 없어 이 서버의 작업으로 연결하지 않았어요. 기록은 브라우저에 그대로 보존돼요.
    </p>
  );
}

function JobHistory({ paneId, jobIds, current }: { paneId: PaneId; jobIds: number[]; current: number | null }) {
  const watchJob = useWorkspace((s) => s.watchJob);
  const rest = jobIds.filter((id) => id !== current).slice(0, 5);
  if (!rest.length) return null;
  return (
    <ul className="job-history" aria-label="이 브라우저에서 실행한 이 씬의 다른 작업">
      {rest.map((id) => <HistoryRow key={id} jobId={id} onPick={() => watchJob(paneId, id)} />)}
    </ul>
  );
}

function HistoryRow({ jobId, onPick }: { jobId: number; onPick: () => void }) {
  // Cached status only; history rows do not poll.
  const q = useQuery({ ...jobStatusQuery(jobId), staleTime: 60_000 });
  const st = q.data?.status;
  const color = st === 'COMPLETED' ? 'var(--st-ok)' : st === 'FAILED' ? 'var(--st-err)' : st === 'RUNNING' ? 'var(--st-run)' : 'var(--st-pend)';
  return (
    <li>
      <button type="button" onClick={onPick}>
        <span className="dot" style={{ background: color }} />
        <span className="mono">#{jobId}</span>
        <span>{st ? STATUS_KO[st] : q.isError ? '확인할 수 없음' : '확인 중'}</span>
        <span className="dim" style={{ marginLeft: 'auto' }}>보기</span>
      </button>
    </li>
  );
}

function JobLookup({ onOpen }: { onOpen: (id: number) => void }) {
  const [value, setValue] = useState('');
  const id = Number(value);
  const valid = Number.isSafeInteger(id) && id > 0;
  return (
    <form className="job-lookup" onSubmit={(e) => { e.preventDefault(); if (valid) { onOpen(id); setValue(''); } }}>
      <label className="sr-only" htmlFor="job-lookup">작업 번호</label>
      <input id="job-lookup" inputMode="numeric" placeholder="작업 번호로 열기" value={value} onChange={(e) => setValue(e.currentTarget.value.trim())} />
      <button type="submit" className="btn btn--sm" disabled={!valid}>열기</button>
    </form>
  );
}

const fmtTime = (t: number) => [new Date(t).getHours(), new Date(t).getMinutes(), new Date(t).getSeconds()].map((n) => String(n).padStart(2, '0')).join(':');

interface ReadinessProps {
  paneId: PaneId;
  vespa: Capability;
  /** Last successful answer; shown for context only, never used to allow a run. */
  last?: Capability;
  lastChecked: number;
  refreshing: boolean;
  onRefresh: () => void;
  onRecheck: () => void;
}

function ReadinessBox({ paneId, vespa, last, lastChecked, refreshing, onRefresh, onRecheck }: ReadinessProps) {
  if (vespa.canExecute) {
    return (
      <p className="help" data-testid={`vespa-ready-${paneId}`}>
        실행 환경 확인됨 · {vespa.executor === 'ssh' ? '원격 클러스터(SSH)' : '로컬'} 실행. 실제 추론 성공을 보장하는 확인은 아니에요.
      </p>
    );
  }
  // Status call failed / answer expired / still checking: re-read with a light GET. The heavy environment re-check
  // (refresh=true) is only offered for real capability reasons.
  const statusProblem = (vespa.reasonCode ?? '').startsWith('STATUS_') && vespa.reasonCode !== 'STATUS_API_UNSUPPORTED';
  const fixedByRefresh = !statusProblem && !['SYNTHETIC_DATASET', 'VESPA_WORKER_DISABLED', 'DATASET_MISMATCH'].includes(vespa.reasonCode ?? '');
  return (
    <div className="readiness readiness--blocked" role="status" data-testid={`vespa-readiness-${paneId}`} data-state={vespa.state} data-reason={vespa.reasonCode ?? ''}>
      <div className="row"><ShieldAlert className="icon" aria-hidden="true" /><b>라벨 생성 {stateLabel(vespa.state)}</b>{vespa.executor && <span className="dim">· {vespa.executor === 'ssh' ? '원격(SSH)' : '로컬'}</span>}</div>
      <div>{capabilityMessage(vespa)} 기존 완료 결과 조회와 센서 탐색은 그대로 쓸 수 있어요.</div>
      {statusProblem && last && lastChecked > 0 && (
        <div className="dim" data-testid={`vespa-last-known-${paneId}`}>마지막 확인 {fmtTime(lastChecked)}: {stateLabel(last.state)} (현재 판정에는 쓰지 않아요)</div>
      )}
      {statusProblem && vespa.reasonCode !== 'STATUS_CHECKING' && (
        <button type="button" className="btn btn--sm btn--weak" onClick={onRecheck}><RefreshCw className="icon" aria-hidden="true" />상태 다시 확인</button>
      )}
      {fixedByRefresh && (
        <button type="button" className="btn btn--sm btn--weak" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? <span className="spin" aria-hidden="true" /> : <RefreshCw className="icon" aria-hidden="true" />}실행 환경 확인
        </button>
      )}
    </div>
  );
}
