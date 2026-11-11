import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';
import { isApiError } from '@/api/http';
import type { SampleRef, Scene } from '@/api/models';
import { jobResultsQuery, jobStatusQuery, qk, sceneJobsQuery } from '@/api/queries';
import { useSystemStatus } from '@/features/system/useSystemStatus';
import { findReceipt, receiptsForScene, unverifiedReceiptsForScene } from '@/lib/jobs/receipts';
import { dismissJobSubmission, newJobSnapshot, submitJob, useSubmissions } from '@/lib/jobs/submissions';
import { useServer } from '@/stores/server';
import { useWorkspace, type PaneId } from '@/stores/workspace';
import { pollInterval, verifyJob } from './jobLogic';
import { useReceipts } from './useReceipts';

/**
 * Label job state of one pane, mounted for as long as the inspector exists (whatever tab is open), so status polling
 * and "show the verified completed result" keep working.
 * - Restores the newest completed server result of this scene, falling back to receipts on older servers.
 * - Polls status every 3 s while PENDING/RUNNING (5 s while the status GET itself fails) and stops at a terminal state.
 *   A failing status GET is not a FAILED job.
 * - Results of a COMPLETED job are a plain GET (retrying it never starts VESPA again).
 * - A new run uses a new Idempotency-Key; resending after a lost response reuses the same snapshot/key.
 */
export function useJobState(paneId: PaneId, scene: Scene, samples: SampleRef[]) {
  const client = useQueryClient();
  const pane = useWorkspace((s) => s.panes[paneId]);
  const watchJob = useWorkspace((s) => s.watchJob);
  const showResult = useWorkspace((s) => s.showResult);
  const scope = useServer((s) => s.scope);
  const receipts = useReceipts();
  const sceneReceipts = useMemo(() => receiptsForScene(receipts, scope, scene.datasetId, scene.token), [receipts, scope, scene.datasetId, scene.token]);
  const legacyCount = useMemo(() => unverifiedReceiptsForScene(receipts, scene.datasetId, scene.token).length, [receipts, scene.datasetId, scene.token]);
  const system = useSystemStatus(scene.datasetId);
  const vespa = system.capability('vespa');
  const sampleTokens = useMemo(() => new Set(samples.map((s) => s.token)), [samples]);
  const jobId = pane.jobId;
  const paneMatches = pane.datasetId === scene.datasetId && pane.sceneId === scene.id;
  const historyQ = useQuery({ ...sceneJobsQuery(scene.id), enabled: paneMatches });
  const history = historyQ.data;
  const sceneHistory = useMemo(() => {
    const rows = new Map(sceneReceipts.map((r) => [r.jobId, { jobId: r.jobId, classMode: r.classMode as number | null, createdAt: r.requestedAt }]));
    for (const r of history ?? []) rows.set(r.jobId, { jobId: r.jobId, classMode: r.classMode, createdAt: r.createdAt });
    return [...rows.values()].sort((a, b) => b.createdAt - a.createdAt || b.jobId - a.jobId);
  }, [history, sceneReceipts]);

  useEffect(() => {
    if (!paneMatches || jobId != null) return;
    const restored = history?.find((r) => r.status === 'COMPLETED') ?? history?.[0];
    const id = restored?.jobId ?? (historyQ.isError ? sceneReceipts[0]?.jobId : undefined);
    if (id != null) watchJob(paneId, id);
  }, [paneMatches, pane.generation, jobId, history, historyQ.isError, sceneReceipts, paneId, watchJob]);

  useEffect(() => {
    for (const value of history ?? []) client.setQueryData(qk.jobStatus(value.jobId), value);
  }, [history, client]);

  const statusQ = useQuery({
    ...jobStatusQuery(jobId ?? -1),
    enabled: jobId != null,
    refetchInterval: (q) => pollInterval(q.state.data, q.state.status === 'error'),
    refetchIntervalInBackground: false,
  });
  const status = statusQ.data;
  useEffect(() => {
    if (status) void client.invalidateQueries({ queryKey: qk.sceneJobs(scene.id) });
  }, [status?.jobId, status?.status, scene.id, client]);
  const completed = status?.status === 'COMPLETED';
  const resultsQ = useQuery({ ...jobResultsQuery(jobId ?? -1), enabled: jobId != null && completed });
  const receipt = jobId != null ? findReceipt(receipts, scope, jobId) : undefined;
  const ownership = jobId != null ? verifyJob(scene, sampleTokens, status, receipt, resultsQ.data) : null;

  useEffect(() => {
    if (paneMatches && jobId != null && completed && ownership?.kind === 'verified') showResult(paneId, jobId);
  }, [paneMatches, jobId, completed, ownership?.kind, paneId, showResult]);

  const active = status?.status === 'PENDING' || status?.status === 'RUNNING';
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

  return {
    pane, jobId, statusQ, status, completed, resultsQ, receipt, ownership, active, posting, failedPost, lostResponse, busy,
    sceneReceipts, sceneHistory, historyQ, legacyCount, system, vespa, blocked: !vespa.canExecute, startNewRun, resendSame,
    watch: (id: number | null) => watchJob(paneId, id),
  };
}

export type JobState = ReturnType<typeof useJobState>;
