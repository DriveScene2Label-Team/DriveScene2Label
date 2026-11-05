import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Icon } from '@/components/Icon';
import { useEffect, useMemo } from 'react';
import { describeError, isApiError } from '@/api/http';
import type { Recording, Scene } from '@/api/models';
import { qk, recordingQuery, recordingsQuery } from '@/api/queries';
import { capabilityMessage } from '@/api/system';
import { useSystemStatus } from '@/features/system/useSystemStatus';
import { errorGuide } from '@/lib/errorCodes';
import { recordingKey, submitRecording, useSubmissions } from '@/lib/jobs/submissions';
import { useServer } from '@/stores/server';
import { useWorkspace, type PaneId } from '@/stores/workspace';
import { RerunViewer } from './RerunViewer';

const RECORDING_STATUS_KO: Record<string, string> = { PENDING: '대기 중', RUNNING: '생성 중', READY: '준비됨', FAILED: '생성 실패' };

/** Pick the recording to show: the pane's explicit choice, else the newest one for the shown job (or GT-only). */
export function pickRecording(list: Recording[], jobId: number | null, explicit: number | null): Recording | undefined {
  if (explicit != null) {
    const found = list.find((r) => r.recordingId === explicit);
    if (found) return found;
  }
  const same = list.filter((r) => r.jobId === jobId).sort((a, b) => b.createdAt - a.createdAt || b.recordingId - a.recordingId);
  return same.find((r) => r.status !== 'FAILED') ?? same[0];
}

interface Props {
  paneId: PaneId;
  scene: Scene;
  /** Draw only for the active pane in compare mode (single Rerun instance). */
  enabled: boolean;
}

/**
 * LiDAR/3D area. Recording readiness (PENDING/RUNNING/READY/FAILED) is separate from the label job status, and a
 * failed recording is retried by asking for a recording again — never by re-running VESPA.
 */
export function RecordingPanel(props: Props) {
  return (
    <div className="v3d" data-v3d={props.paneId}>
      <div className="v3d-body"><RecordingBody {...props} /></div>
    </div>
  );
}

function RecordingBody({ paneId, scene, enabled }: Props) {
  const pane = useWorkspace((s) => s.panes[paneId]);
  const setRecording = useWorkspace((s) => s.setRecording);
  const qc = useQueryClient();
  const listQ = useQuery({ ...recordingsQuery(scene.id), enabled });
  const targetJob = pane.resultJobId;
  const picked = useMemo(() => (listQ.data ? pickRecording(listQ.data, targetJob, pane.recordingId) : undefined), [listQ.data, targetJob, pane.recordingId]);
  const detailQ = useQuery({
    ...recordingQuery(picked?.recordingId ?? -1),
    enabled: enabled && !!picked,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'PENDING' || s === 'RUNNING' || (!s && q.state.status !== 'error') ? 3000 : q.state.status === 'error' ? 5000 : false;
    },
  });
  const rec = detailQ.data;

  // If the shown job changes, drop an explicit choice that belonged to another job.
  useEffect(() => {
    if (pane.recordingId != null && rec && rec.recordingId === pane.recordingId && rec.jobId !== targetJob) setRecording(paneId, null);
  }, [rec, pane.recordingId, targetJob, paneId, setRecording]);

  const scope = useServer((s) => s.scope);
  const system = useSystemStatus(scene.datasetId);
  const capability = system.capability('recording');
  const subKey = recordingKey({ instanceId: scope, sceneId: scene.id, jobId: targetJob });
  const submission = useSubmissions((st) => st.recordings[subKey]);
  const creating = submission?.status === 'pending';
  const create = () => void submitRecording({
    instanceId: scope, datasetId: scene.datasetId, datasetChecksum: system.status?.dataset?.metadataChecksum ?? null, sceneId: scene.id,
    sceneToken: scene.token, sceneName: scene.name, paneId, generation: pane.generation, jobId: targetJob, requestedAt: Date.now(),
  }, () => useServer.getState().scope);
  const onFileMissing = () => {
    void qc.invalidateQueries({ queryKey: qk.recordings(scene.id) });
    if (picked) void qc.invalidateQueries({ queryKey: qk.recording(picked.recordingId) });
  };

  if (!enabled) {
    return (
      <div className="v3d-state">
        <Icon name="cube" />
        <b>3D 보기는 작업 대상 패널 하나에서만 열려요</b>
        <span>이 패널을 작업 대상으로 고르면 3D 뷰어가 이쪽으로 옮겨 와요.</span>
      </div>
    );
  }
  if (listQ.isPending) return <div className="v3d-state" role="status"><span className="spinner" aria-hidden="true" />3D recording 정보를 확인하고 있어요</div>;
  if (listQ.isError) {
    const unsupported = isApiError(listQ.error) && (listQ.error.status === 404 || listQ.error.status === 405);
    return (
      <div className="v3d-state" role="alert">
        <b>{unsupported ? '이 서버는 3D recording을 제공하지 않아요' : '3D recording 정보를 불러오지 못했어요'}</b>
        <span className="mono">{describeError(listQ.error)}</span>
        <button type="button" className="btn sm weak" onClick={() => void listQ.refetch()}>다시 확인</button>
      </div>
    );
  }

  const jobText = targetJob != null ? `작업 #${targetJob} 예측 포함` : 'GT·센서만';
  const createButton = (labelText: string) => (
    <>
      <button type="button" className="btn primary sm" onClick={create} disabled={creating || !capability.canExecute} data-testid="create-recording">
        {creating ? <span className="spinner" aria-hidden="true" /> : <Icon name="cube" />}{labelText}
      </button>
      {!capability.canExecute && (
        <span className="v3d-ready-note" data-testid="recording-readiness" data-reason={capability.reasonCode ?? ''}>
          3D 생성 준비 안 됨 · {capabilityMessage(capability)}{' '}
          <button type="button" className="btn sm weak" onClick={() => void system.recheck(capability)} disabled={system.refreshing}>다시 확인</button>
        </span>
      )}
      {submission?.status === 'error' && <span className="mono">{describeError(submission.error)}</span>}
    </>
  );

  if (!picked) {
    return (
      <div className="v3d-state">
        <Icon name="cube" />
        <b>아직 3D recording이 없어요</b>
        <span>실제 LiDAR 점군과 GT{targetJob != null ? `, 작업 #${targetJob}의 예측` : ''}을 담은 recording을 서버에서 만들어요.</span>
        {createButton(`3D recording 만들기 (${jobText})`)}
      </div>
    );
  }
  const status = rec?.status ?? picked.status;
  if (status === 'READY' && rec?.contentUrl) {
    return (
      <>
        <RerunViewer key={rec.recordingId} paneId={paneId} recording={rec} displayedSampleToken={pane.displayedSampleToken} onFileMissing={onFileMissing} />
        {/* Not drawn over the viewer (it covered Rerun's own timeline controls); kept for screen readers and tests. */}
        <div className="sr-only" role="status" data-testid="recording-badge">
          3D recording 열림 · {rec.jobId != null ? `GT + 작업 #${rec.jobId} 예측` : 'GT·센서'} · 원본 박스 기준, GT·예측·클래스 이름 표시는 위 버튼을 따라요
        </div>
      </>
    );
  }
  if (status === 'FAILED') {
    return (
      <div className="v3d-state" role="alert">
        <b>{errorGuide(rec?.errorCode ?? picked.errorCode)?.title ?? '3D recording을 만들지 못했어요'}</b>
        <span className="mono">{(rec?.errorCode ?? picked.errorCode) ? `${rec?.errorCode ?? picked.errorCode} · ` : ''}{rec?.errorMessage ?? picked.errorMessage ?? '오류 메시지 없음'}</span>
        <span>recording만 다시 만들어요. 라벨 작업은 다시 실행하지 않아요.</span>
        {createButton('recording 다시 만들기')}
      </div>
    );
  }
  if (status === 'READY') {
    // READY in the list, detail (with the content URL) still loading or failed to load.
    return (
      <div className="v3d-state" role="status">
        {detailQ.isError ? <b>3D recording 정보를 불러오지 못했어요</b> : <><span className="spinner" aria-hidden="true" /><b>3D recording 정보를 불러오고 있어요</b></>}
        {detailQ.isError && <><span className="mono">{describeError(detailQ.error)}</span><button type="button" className="btn sm weak" onClick={() => void detailQ.refetch()}>다시 확인</button></>}
      </div>
    );
  }
  return (
    <div className="v3d-state" role="status">
      <span className="spinner" aria-hidden="true" />
      <b>3D recording {RECORDING_STATUS_KO[status] ?? status}</b>
      <span>recording #{picked.recordingId} · {jobText}. 준비되면 자동으로 열려요.</span>
      {detailQ.isError && <span className="mono">상태를 확인하지 못했어요 · {describeError(detailQ.error)}</span>}
    </div>
  );
}
