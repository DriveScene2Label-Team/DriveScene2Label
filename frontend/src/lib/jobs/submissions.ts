import type { QueryClient } from '@tanstack/react-query';
import { create } from 'zustand';
import type { ClassMode, RecordingCreatedDto } from '@/api/dto';
import { requestJson } from '@/api/http';
import { qk } from '@/api/queries';
import { createJob, newIdempotencyKey, type RunIntent } from './createJob';
import { saveReceipt } from './receipts';
import { toast } from '@/stores/toast';
import { useWorkspace, type PaneId } from '@/stores/workspace';

/**
 * Request snapshots and their in-flight state, kept outside React components so that a request survives scene
 * changes, active-pane switches and unmounts. Answers are recorded against the snapshot (receipt, query cache of the
 * original scene) and attached to a pane only if that pane still shows the same server/dataset/scene/generation.
 */
export interface UiContext {
  instanceId: string;
  datasetId: number;
  datasetChecksum: string | null;
  sceneId: number;
  sceneToken: string;
  sceneName: string;
  paneId: PaneId;
  generation: number;
}

export interface JobSnapshot extends UiContext {
  classMode: ClassMode;
  idempotencyKey: string;
  requestedAt: number;
}

export interface RecordingSnapshot extends UiContext {
  jobId: number | null;
  /** Comparison job drawn next to jobId (needs jobId). */
  compareJobId?: number | null;
  requestedAt: number;
}

export type Pending<S> = { snapshot: S; status: 'pending' | 'error'; error?: unknown };

interface SubmissionStore {
  jobs: Record<string, Pending<JobSnapshot>>; // by idempotencyKey
  recordings: Record<string, Pending<RecordingSnapshot>>; // by recordingKey()
}

export const useSubmissions = create<SubmissionStore>()(() => ({ jobs: {}, recordings: {} }));

let client: QueryClient | null = null;
/** Called once by the app shell so answers can update the shared query cache. */
export function bindQueryClient(qc: QueryClient): void {
  client = qc;
}

/** Does the pane still show the context the request was made in? */
export function sameContext(ctx: UiContext, scope: string): boolean {
  const pane = useWorkspace.getState().panes[ctx.paneId];
  return ctx.instanceId === scope && pane.datasetId === ctx.datasetId && pane.sceneId === ctx.sceneId && pane.generation === ctx.generation;
}

export function newJobSnapshot(ctx: UiContext, classMode: ClassMode): JobSnapshot {
  return { ...ctx, classMode, idempotencyKey: newIdempotencyKey(), requestedAt: Date.now() };
}

export const intentOf = (s: JobSnapshot): RunIntent => ({ key: s.idempotencyKey, body: { sceneToken: s.sceneToken, datasetId: s.datasetId, classMode: s.classMode } });

const setJob = (key: string, v: Pending<JobSnapshot> | null) =>
  useSubmissions.setState((st) => {
    const jobs = { ...st.jobs };
    if (v) jobs[key] = v;
    else delete jobs[key];
    return { jobs };
  });

/**
 * POST a job for the snapshot. Retries reuse the snapshot's key (createJob). `currentScope` is read at answer time.
 * Returns the job id, or null when the request failed (state kept for "같은 요청 다시 보내기").
 */
export async function submitJob(snapshot: JobSnapshot, currentScope: () => string, opts?: Parameters<typeof createJob>[1]): Promise<number | null> {
  setJob(snapshot.idempotencyKey, { snapshot, status: 'pending' });
  try {
    const created = await createJob(intentOf(snapshot), opts);
    saveReceipt({
      instanceId: snapshot.instanceId, jobId: created.jobId, datasetId: snapshot.datasetId, datasetChecksum: snapshot.datasetChecksum,
      sceneId: snapshot.sceneId, sceneToken: snapshot.sceneToken, sceneName: snapshot.sceneName, paneId: snapshot.paneId,
      classMode: snapshot.classMode, idempotencyKey: snapshot.idempotencyKey, requestedAt: snapshot.requestedAt,
    });
    setJob(snapshot.idempotencyKey, null);
    void client?.invalidateQueries({ queryKey: qk.jobStatus(created.jobId) });
    if (sameContext(snapshot, currentScope())) {
      useWorkspace.getState().watchJob(snapshot.paneId, created.jobId);
      toast(`작업 #${created.jobId}을 만들었어요`, 'ok');
    } else {
      toast(`${snapshot.sceneName}의 작업 #${created.jobId}이 접수됐어요 (지금 화면과 다른 씬이라 연결하지 않았어요)`, 'info');
    }
    return created.jobId;
  } catch (error) {
    setJob(snapshot.idempotencyKey, { snapshot, status: 'error', error });
    return null;
  }
}

export function dismissJobSubmission(key: string): void {
  setJob(key, null);
}

export const recordingKey = (s: Pick<RecordingSnapshot, 'instanceId' | 'sceneId' | 'jobId' | 'compareJobId'>) =>
  `${s.instanceId}:${s.sceneId}:${s.jobId ?? 'gt'}${s.compareJobId != null ? `:cmp${s.compareJobId}` : ''}`;

/** POST a recording for the snapshot; only the original scene's queries and (if unchanged) pane are updated. */
export async function submitRecording(snapshot: RecordingSnapshot, currentScope: () => string): Promise<number | null> {
  const key = recordingKey(snapshot);
  useSubmissions.setState((st) => ({ recordings: { ...st.recordings, [key]: { snapshot, status: 'pending' } } }));
  try {
    const res = await requestJson<RecordingCreatedDto>(`/api/scenes/${snapshot.sceneId}/recordings`, {
      method: 'POST',
      body: snapshot.jobId == null ? {} : snapshot.compareJobId != null ? { jobId: snapshot.jobId, compareJobId: snapshot.compareJobId } : { jobId: snapshot.jobId },
    });
    useSubmissions.setState((st) => {
      const recordings = { ...st.recordings };
      delete recordings[key];
      return { recordings };
    });
    void client?.invalidateQueries({ queryKey: qk.recordings(snapshot.sceneId) });
    void client?.invalidateQueries({ queryKey: qk.recording(res.data.recordingId) });
    const pane = useWorkspace.getState().panes[snapshot.paneId];
    if (sameContext(snapshot, currentScope()) && pane.resultJobId === snapshot.jobId && (pane.compareJobId ?? null) === (snapshot.compareJobId ?? null)) {
      useWorkspace.getState().setRecording(snapshot.paneId, res.data.recordingId);
    }
    return res.data.recordingId;
  } catch (error) {
    useSubmissions.setState((st) => ({ recordings: { ...st.recordings, [key]: { snapshot, status: 'error', error } } }));
    return null;
  }
}
