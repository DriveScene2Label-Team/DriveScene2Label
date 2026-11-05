import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { ClassMode } from '@/api/dto';
import { describeError, isApiError } from '@/api/http';
import type { Scene } from '@/api/models';
import { jobStatusQuery } from '@/api/queries';
import { capabilityMessage, stateLabel } from '@/api/system';
import { Icon } from '@/components/Icon';
import type { JobState } from '@/features/labeling/useJobState';
import { STATUS_KO } from '@/features/labeling/jobLogic';
import { useNow } from '@/hooks/useNow';
import { CLASS_MODES } from '@/lib/classes';
import { errorGuide } from '@/lib/errorCodes';
import { elapsedMs, formatElapsed } from '@/lib/jobs/createJob';
import { toast } from '@/stores/toast';
import { useWorkspace, type PaneId } from '@/stores/workspace';

const pad = (n: number) => String(n).padStart(2, '0');
const fmtHM = (t: number) => { const d = new Date(t); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const fmtClock = (t: number) => { const d = new Date(t); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
const ST_CLASS: Record<string, string> = { PENDING: 'st-pending', RUNNING: 'st-running', COMPLETED: 'st-completed', FAILED: 'st-failed' };

interface Props {
  paneId: PaneId;
  scene: Scene;
  frameCount: number;
  job: JobState;
  paneLabel?: 'A' | 'B';
}

export function JobsPanel({ paneId, scene, frameCount, job, paneLabel }: Props) {
  const setClassMode = useWorkspace((s) => s.setClassMode);
  const { pane, vespa, system } = job;
  const statusProblem = (vespa.reasonCode ?? '').startsWith('STATUS_') && vespa.reasonCode !== 'STATUS_API_UNSUPPORTED';
  const checking = system.isPending || vespa.reasonCode === 'STATUS_CHECKING' || system.refreshing;
  const fixedByRefresh = !statusProblem && !['SYNTHETIC_DATASET', 'VESPA_WORKER_DISABLED', 'DATASET_MISMATCH'].includes(vespa.reasonCode ?? '');
  const last = system.lastKnown('vespa');

  let env: React.ReactNode;
  if (checking) env = <span className="muted">확인 중…</span>;
  else if (vespa.canExecute) {
    env = (
      <>
        <span className="status st-completed"><i />사용 가능</span>
        {system.lastChecked > 0 && <span className="muted small">{fmtHM(system.lastChecked)} 확인</span>}
        <button type="button" className="link small" onClick={() => void system.refresh()}>다시 확인</button>
      </>
    );
  } else {
    env = (
      <>
        <span className="status st-warn"><i />{statusProblem ? '확인 실패' : '확인 필요'}</span>
        {statusProblem && vespa.reasonCode !== 'STATUS_CHECKING' && <button type="button" className="link small" onClick={() => void system.refetch()}>지금 확인</button>}
        {!statusProblem && fixedByRefresh && <button type="button" className="link small" onClick={() => void system.refresh()}>지금 확인</button>}
      </>
    );
  }

  const label = job.posting ? '요청 보내는 중…' : job.busy ? '생성 중…' : paneLabel ? `씬 ${paneLabel} 라벨 생성하기` : '라벨 생성하기';
  return (
    <>
      <section className="group" aria-labelledby={`job-h-${paneId}`}>
        <h3 className="group-title" id={`job-h-${paneId}`}>라벨 생성</h3>
        <div className="form">
          <div className="form-row"><span className="row-label">대상</span><span className="row-value">{scene.name}{paneLabel && <span className="muted">씬 {paneLabel}</span>}</span></div>
          <div className="form-row"><span className="row-label">범위</span><span className="row-value">씬 전체 {frameCount || scene.nbrSamples}프레임</span></div>
          <div className="form-row">
            <label className="row-label" htmlFor={`cm-${paneId}`}>클래스</label>
            <select id={`cm-${paneId}`} className="popup" value={pane.classMode} onChange={(e) => setClassMode(paneId, Number(e.currentTarget.value) as ClassMode)}>
              {([1, 3, 8] as ClassMode[]).map((m) => <option key={m} value={m}>{m}개 클래스</option>)}
            </select>
          </div>
          <p className="row-help">{CLASS_MODES[pane.classMode].join(', ')}</p>
          <div className="form-row"><span className="row-label">실행 환경</span><span className="row-value">{env}</span></div>
          {!checking && vespa.canExecute && (
            <p className="row-help" data-testid={`vespa-ready-${paneId}`}>{vespa.executor === 'ssh' ? '원격 클러스터(SSH)' : '로컬'} 실행 · 실제 추론 성공을 보장하는 확인은 아니에요.</p>
          )}
        </div>
        {!checking && !vespa.canExecute && (
          <div className="notice" role="status" data-testid={`vespa-readiness-${paneId}`} data-state={vespa.state} data-reason={vespa.reasonCode ?? ''}>
            <Icon name="warn" />
            <span>
              <b>라벨 생성 {stateLabel(vespa.state)}</b>{vespa.executor ? ` · ${vespa.executor === 'ssh' ? '원격(SSH)' : '로컬'}` : ''} · {capabilityMessage(vespa)} 완료된 결과 보기와 센서 탐색은 그대로 쓸 수 있어요.
              {statusProblem && last && system.lastChecked > 0 && (
                <span className="notice-sub" data-testid={`vespa-last-known-${paneId}`}>마지막 확인 {fmtClock(system.lastChecked)}: {stateLabel(last.state)} (현재 판정에는 쓰지 않아요)</span>
              )}
            </span>
          </div>
        )}
        <button type="button" className="btn primary wide" onClick={job.startNewRun} disabled={job.busy || job.blocked} data-testid={`run-job-${paneId}`}>{label}</button>
        {job.failedPost && (
          <div className="notice notice--err" role="alert">
            <Icon name="warn" />
            <span>
              {job.lostResponse ? (
                <>
                  <b>요청 결과를 확인하지 못했어요</b> 서버가 요청을 받았을 수 있어요. 같은 요청을 다시 보내면 이미 만들어진 작업이 있을 때 그 작업을 그대로 돌려받아요.
                  <span className="notice-sub mono">{describeError(job.failedPost.error)}</span>
                  <button type="button" className="btn sm weak" onClick={job.resendSame} disabled={job.posting}>같은 요청 다시 보내기</button>
                </>
              ) : (
                <><b>작업을 만들지 못했어요</b><span className="notice-sub mono">{describeError(job.failedPost.error)}</span></>
              )}
            </span>
          </div>
        )}
        <details className="disclosure">
          <summary>보낼 요청</summary>
          <pre>{`POST /api/auto-label/jobs\nIdempotency-Key: 실행마다 새 키\n${JSON.stringify({ sceneToken: scene.token, datasetId: scene.datasetId, classMode: pane.classMode }, null, 1)}`}</pre>
        </details>
      </section>

      <section className="group" aria-live="polite" aria-labelledby={`st-h-${paneId}`}>
        <h3 className="group-title" id={`st-h-${paneId}`}>진행 상태</h3>
        <CurrentJob paneId={paneId} job={job} />
      </section>

      <section className="group" aria-labelledby={`hist-h-${paneId}`}>
        <h3 className="group-title" id={`hist-h-${paneId}`}>작업 기록</h3>
        {job.sceneReceipts.length ? (
          <ul className="jobs" aria-label="이 브라우저에서 실행한 이 씬의 작업. 완료된 작업을 고르면 그 결과를 화면에 표시해요">
            {job.sceneReceipts.slice(0, 10).map((r) => <JobRow key={r.jobId} jobId={r.jobId} classMode={r.classMode} createdAt={r.requestedAt} shown={pane.resultJobId === r.jobId} onPick={() => job.watch(r.jobId)} />)}
          </ul>
        ) : <p className="muted">이 브라우저에서 실행한 기록이 없어요.</p>}
        {job.legacyCount > 0 && (
          <p className="muted small hist-legacy" data-testid={`legacy-receipts-${paneId}`}>
            이전 버전에서 저장된 이 씬의 실행 기록 {job.legacyCount}건은 어느 서버(DB)의 작업인지 확인할 수 없어 이 서버의 작업으로 연결하지 않았어요. 기록은 브라우저에 그대로 보존돼요.
          </p>
        )}
        <JobLookup onOpen={(id) => job.watch(id)} />
      </section>
    </>
  );
}

function CurrentJob({ paneId, job }: { paneId: PaneId; job: JobState }) {
  const { jobId, status, statusQ, resultsQ, ownership, completed, active, pane, receipt } = job;
  const now = useNow(active ? 1000 : null);
  if (jobId == null) return <p className="muted">아직 실행한 작업이 없어요.</p>;
  const guide = errorGuide(status?.errorCode);
  const remote = job.vespa.executor === 'ssh';
  const elapsed = status && (status.startedAt || status.completedAt) ? formatElapsed(elapsedMs(status, now)) : status ? '시작 전' : '';
  return (
    <div className="job-card" data-testid={`job-card-${paneId}`}>
      <div className="job-head">
        <b>작업 #{jobId}</b>
        {statusQ.isPending ? <span className="status st-pending"><i />확인 중</span>
          : status ? <span className={`status ${ST_CLASS[status.status]}`} data-status={status.status}><i />{STATUS_KO[status.status]}</span>
            : <span className="status st-warn"><i />확인할 수 없음</span>}
        {elapsed && <span className="el">{elapsed}</span>}
      </div>

      {statusQ.isError && (isApiError(statusQ.error) && statusQ.error.status === 404 ? (
        <div className="job-alert" role="alert">
          <b>작업을 찾을 수 없어요</b> 링크의 작업 번호가 이 서버에 없어요. <span className="mono">job {jobId}</span>
          <button type="button" className="btn sm weak" onClick={() => job.watch(null)}>연결 해제</button>
        </div>
      ) : (
        <div className="job-alert job-alert--warn" role="status">
          <b>연결을 확인할 수 없어요</b> 상태를 조회하지 못했어요. 작업 자체가 실패했다는 뜻은 아니에요.
          <span className="mono">{describeError(statusQ.error)}{statusQ.dataUpdatedAt ? ` · 마지막 확인 ${fmtClock(statusQ.dataUpdatedAt)}` : ''}</span>
          <button type="button" className="btn sm weak" onClick={() => void statusQ.refetch()}>다시 조회</button>
        </div>
      ))}

      {ownership?.kind === 'mismatch' && <div className="job-alert" role="alert"><b>이 씬의 작업이 아니에요</b> {ownership.reason}. 결과를 이 씬에 표시하지 않아요.</div>}
      {ownership?.kind === 'unverified' && status && (
        <p className="muted small">작업 대상 확인 필요 · 서버 상태 응답과 이 브라우저의 실행 기록으로는 이 씬의 작업인지 아직 확인할 수 없어요.{completed ? '' : ' 완료 후 결과 프레임으로 확인해요.'}</p>
      )}

      {active && status && (
        <>
          <div className="progress" role="progressbar" aria-label="작업 진행 중, 진행률 정보 없음" />
          <p className="muted small">
            {status.status === 'PENDING' ? '대기열에 있어요.' : remote ? '원격 클러스터에서 처리 중이에요.' : '씬 전체 프레임을 처리하고 있어요.'} 3초마다 상태를 확인해요. 진행률은 제공되지 않아 단계나 퍼센트는 표시하지 않아요.
          </p>
        </>
      )}

      {status?.status === 'FAILED' && (
        <div data-error-code={status.errorCode ?? ''}>
          <p><b>{guide?.title ?? '작업이 실패했어요'}</b> {guide ? guide.action : '원인을 확인한 뒤 새 작업으로 다시 실행해 주세요.'} GT와 이전 결과는 그대로 남아 있어요.</p>
          <p className="err">{status.errorCode ? `${status.errorCode} · ` : ''}{status.errorMessage || '오류 메시지 없음'}</p>
          <button type="button" className="btn sm weak" onClick={job.startNewRun} disabled={job.posting || job.blocked}>{guide?.environment ? '환경 확인 후 다시 시도' : '다시 시도'}</button>
          {job.blocked && <p className="muted small">실행 환경이 준비되지 않아 다시 실행할 수 없어요.</p>}
        </div>
      )}

      {completed && (
        resultsQ.isPending ? <p className="muted">결과 불러오는 중…</p>
          : resultsQ.isError ? (
            <div className="job-alert job-alert--warn" role="alert">
              <b>결과를 불러오지 못했어요</b> 작업은 완료되었어요. 결과만 다시 읽어요(새 작업을 만들지 않아요).
              <span className="mono">{describeError(resultsQ.error)}</span>
              <button type="button" className="btn sm weak" onClick={() => void resultsQ.refetch()}>결과 다시 불러오기</button>
            </div>
          ) : resultsQ.data && (
            <>
              <p>예측 박스 {resultsQ.data.boxCount.toLocaleString('ko-KR')}개, {resultsQ.data.sampleTokens.size}프레임{resultsQ.data.editedCount ? `, 이름 바꾼 박스 ${resultsQ.data.editedCount}개` : ''}{resultsQ.data.boxCount === 0 ? ' · 검출된 박스가 없어요' : ''}</p>
              {resultsQ.data.artifactPath && <p className="muted small mono" title="결과 파일의 서버 내부 경로예요. 다운로드 주소가 아니에요.">{resultsQ.data.artifactPath}</p>}
            </>
          )
      )}
      {pane.resultJobId != null && pane.resultJobId !== jobId && <p className="muted small">화면에는 작업 #{pane.resultJobId} 결과가 표시돼요.</p>}
      {status && (
        <p className="muted small job-times">
          {status.classMode ?? receipt?.classMode ?? '?'}개 클래스 · 생성 {fmtClock(status.createdAt)}{status.completedAt ? ` · 완료 ${fmtClock(status.completedAt)}` : ''}
        </p>
      )}
    </div>
  );
}

function JobRow({ jobId, classMode, createdAt, shown, onPick }: { jobId: number; classMode: number; createdAt: number; shown: boolean; onPick: () => void }) {
  // Cached status only; history rows do not poll.
  const q = useQuery({ ...jobStatusQuery(jobId), staleTime: 60_000 });
  const st = q.data?.status;
  return (
    <li>
      <button type="button" className="job-row" aria-pressed={shown} onClick={onPick}
        title={st === 'COMPLETED' ? '이 작업을 진행 상태에 연결하고 결과를 화면에 표시' : '이 작업을 진행 상태에 연결'}>
        <span>#{jobId}</span>
        <span className={`status ${st ? ST_CLASS[st] : 'st-pending'}`}><i />{st ? STATUS_KO[st] : q.isError ? '확인 불가' : '확인 중'}</span>
        <span className="k">{classMode}개</span>
        <span className="t">{createdAt ? fmtHM(createdAt) : ''}</span>
        <Icon name="check" className="chk-ic" />
      </button>
    </li>
  );
}

function JobLookup({ onOpen }: { onOpen: (id: number) => void }) {
  const [value, setValue] = useState('');
  const id = Number(value);
  const valid = Number.isSafeInteger(id) && id > 0;
  return (
    <form className="open-job" onSubmit={(e) => { e.preventDefault(); if (!valid) { toast('작업 번호를 숫자로 입력해 주세요', 'error'); return; } onOpen(id); setValue(''); }}>
      <label htmlFor="job-no">번호로 열기</label>
      <input id="job-no" className="field" inputMode="numeric" placeholder="예: 1001" autoComplete="off" value={value} onChange={(e) => setValue(e.currentTarget.value.replace(/[^0-9]/g, ''))} />
      <button type="submit" className="btn sm">열기</button>
    </form>
  );
}
