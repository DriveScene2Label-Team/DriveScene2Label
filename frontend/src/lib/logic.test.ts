import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { toJobResults, toJobStatus } from '@/api/mappers';
import { verifyJob, pollInterval } from '@/features/labeling/jobLogic';
import { boxKeyForSelection, indexForSample } from '@/features/viewer/recordingMap';
import { jobResultsDto, jobStatusDto } from '@/test/fixtures';
import { comparisonClass } from './classes';
import { createJob, elapsedMs, newRunIntent } from './jobs/createJob';
import { _resetReceiptCache, findReceipt, loadReceipts, receiptsForScene, saveReceipt, unverifiedReceiptsForScene } from './jobs/receipts';
import { mapRelative, nearestIndex, playbackDelayMs, relativeProgress } from './time/timeline';
import type { Recording } from '@/api/models';

const t = (us: number[]) => us.map((v, i) => ({ token: `t${i}`, timestampUs: v }));

describe('timestamp playback and relative sync', () => {
  it('uses the real keyframe gap, scaled by speed, with a fallback for equal timestamps', () => {
    const s = t([0, 500_000, 1_100_000, 1_100_000]);
    expect(playbackDelayMs(s, 0, 1)).toBe(500);
    expect(playbackDelayMs(s, 1, 2)).toBe(300);
    expect(playbackDelayMs(s, 2, 1)).toBe(500);
    expect(playbackDelayMs(s, 3, 1)).toBe(500);
  });
  it('maps by fraction of each scene’s own time span, not frame index', () => {
    const a = t([0, 1e6, 2e6, 10e6]); // A: progress of index 2 = 0.2
    const b = t([100e6, 101e6, 102e6, 110e6]);
    expect(relativeProgress(a, 2)).toBeCloseTo(0.2);
    expect(mapRelative(a, 2, b)).toBe(2); // target 102e6
    expect(mapRelative(a, 3, b)).toBe(3);
  });
  it('handles single-frame and zero-span scenes without dividing by zero', () => {
    expect(mapRelative(t([5]), 0, t([0, 1e6]))).toBe(0);
    expect(mapRelative(t([0, 1e6]), 1, t([7, 7, 7]))).toBe(0);
    expect(mapRelative(t([0, 1e6]), 1, [])).toBe(-1);
    expect(nearestIndex(t([0, 10, 20]), 14)).toBe(1);
    expect(nearestIndex(t([0, 10, 20]), 15)).toBe(1);
  });
});

describe('job creation idempotency', () => {
  afterEach(() => vi.restoreAllMocks());
  const body = { sceneToken: 'scene-tok', datasetId: 1, classMode: 8 as const };

  it('retries a lost response with the same Idempotency-Key and gets the same job', async () => {
    const keys: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_u, init) => {
      keys.push((init!.headers as Record<string, string>)['Idempotency-Key']!);
      if (keys.length === 1) throw new TypeError('connection reset');
      return new Response(JSON.stringify({ jobId: 12, status: 'PENDING' }), { status: 202 });
    });
    const intent = newRunIntent(body);
    const created = await createJob(intent, { sleep: async () => {} });
    expect(created.jobId).toBe(12);
    expect(keys).toEqual([intent.key, intent.key]);
  });
  it('retries 503 but not 409 key conflicts', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('', { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'HTTP_409', message: 'Idempotency key refers to another request' }), { status: 409 }));
    await expect(createJob(newRunIntent(body), { sleep: async () => {} })).rejects.toMatchObject({ status: 409 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it('uses a new key for each new user run', () => {
    expect(newRunIntent(body).key).not.toBe(newRunIntent(body).key);
  });
  it('stops elapsed time at completedAt', () => {
    expect(elapsedMs({ createdAt: 0, startedAt: 1000, completedAt: 61_000 }, 999_999)).toBe(60_000);
    expect(elapsedMs({ createdAt: 0, startedAt: null, completedAt: null }, 5000)).toBe(5000);
  });
  it('polls every 3 s, backs off on GET errors, and stops at terminal states', () => {
    expect(pollInterval(toJobStatus(jobStatusDto()), false)).toBe(3000);
    expect(pollInterval(toJobStatus(jobStatusDto()), true)).toBe(5000);
    expect(pollInterval(undefined, true)).toBe(5000);
    expect(pollInterval(toJobStatus(jobStatusDto({ status: 'FAILED', errorMessage: 'x', completedAt: '2026-10-03T12:00:05Z' })), false)).toBe(false);
  });
});

describe('job receipts (instance scoped)', () => {
  beforeEach(() => { localStorage.clear(); _resetReceiptCache(); });
  const base = { datasetId: 1, sceneId: 7, sceneToken: 'a', sceneName: 'scene-0061', classMode: 8 as const, idempotencyKey: 'k', requestedAt: 1, datasetChecksum: null, paneId: 'single' };
  it('keeps receipts of different servers apart (job 2 of DB-x is not job 2 of DB-y)', () => {
    saveReceipt({ ...base, instanceId: 'db-x', jobId: 2 });
    saveReceipt({ ...base, instanceId: 'db-y', jobId: 2, sceneToken: 'b', requestedAt: 2 });
    _resetReceiptCache();
    expect(receiptsForScene(loadReceipts(), 'db-x', 1, 'a').map((r) => r.jobId)).toEqual([2]);
    expect(receiptsForScene(loadReceipts(), 'db-y', 1, 'a')).toEqual([]);
    expect(findReceipt(loadReceipts(), 'db-y', 2)?.sceneToken).toBe('b');
  });
  it('ignores corrupt storage', () => {
    localStorage.setItem('ds2l.jobReceipts.v2', '{"v":2,"data":[{"jobId":"x"}]}');
    _resetReceiptCache();
    expect(loadReceipts()).toEqual([]);
  });
  it('never attaches v1 receipts to a server, even when that server has the same datasetId/sceneToken/jobId (FU-02)', () => {
    const v1 = { jobId: 41, datasetId: 1, sceneId: 7, sceneToken: 'a', sceneName: 's', classMode: 8, idempotencyKey: 'old-db-request-key', requestedAt: 5 };
    localStorage.setItem('ds2l.jobReceipts', JSON.stringify({ v: 1, data: [v1] }));
    _resetReceiptCache();
    expect(receiptsForScene(loadReceipts(), 'db-new', 1, 'a')).toEqual([]);
    expect(findReceipt(loadReceipts(), 'db-new', 41)).toBeUndefined();
    expect(unverifiedReceiptsForScene(loadReceipts(), 1, 'a').map((r) => r.idempotencyKey)).toEqual(['old-db-request-key']);
    expect(JSON.parse(localStorage.getItem('ds2l.jobReceipts')!).data).toEqual([v1]); // preserved untouched
  });
  it('treats v2 entries made by the former migration as unverified, keeps normal v2 entries', () => {
    saveReceipt({ ...base, instanceId: 'db-x', jobId: 41, paneId: 'legacy', idempotencyKey: 'old' });
    saveReceipt({ ...base, instanceId: 'db-x', jobId: 42, idempotencyKey: 'new', requestedAt: 9 });
    _resetReceiptCache();
    expect(receiptsForScene(loadReceipts(), 'db-x', 1, 'a').map((r) => r.jobId)).toEqual([42]);
    expect(findReceipt(loadReceipts(), 'db-x', 41)).toBeUndefined();
    expect(unverifiedReceiptsForScene(loadReceipts(), 1, 'a').map((r) => r.jobId)).toEqual([41]);
    expect(loadReceipts()).toHaveLength(2); // nothing deleted
  });
});

describe('job ownership (shared links)', () => {
  const scene = { datasetId: 1, token: 'scene-tok' };
  const tokens = new Set(['s0', 's1']);
  it('trusts the server job context first', () => {
    expect(verifyJob(scene, tokens, toJobStatus(jobStatusDto({ sceneToken: 'scene-tok' })), undefined, undefined).kind).toBe('verified');
    expect(verifyJob(scene, tokens, toJobStatus(jobStatusDto({ sceneToken: 'other' })), undefined, undefined).kind).toBe('mismatch');
  });
  it('does not accept a job just because the dataset matches', () => {
    expect(verifyJob(scene, tokens, toJobStatus(jobStatusDto()), undefined, undefined).kind).toBe('unverified');
  });
  it('verifies a completed job by its result sample tokens', () => {
    const st = toJobStatus(jobStatusDto({ status: 'COMPLETED' }));
    expect(verifyJob(scene, tokens, st, undefined, toJobResults(jobResultsDto())).kind).toBe('verified');
    expect(verifyJob(scene, new Set(['other']), st, undefined, toJobResults(jobResultsDto())).kind).toBe('mismatch');
  });
  it('rejects another dataset', () => {
    expect(verifyJob(scene, tokens, toJobStatus(jobStatusDto({ datasetId: 2 })), undefined, undefined).kind).toBe('mismatch');
  });
});

describe('GT category → VESPA comparison class', () => {
  it('follows the upstream VESPA mapping and keeps unmapped categories unmapped', () => {
    expect(comparisonClass('vehicle.bus.rigid', 8)).toBe('bus');
    expect(comparisonClass('vehicle.motorcycle', 3)).toBe('bicycle');
    expect(comparisonClass('human.pedestrian.adult', 1)).toBe('vehicle');
    expect(comparisonClass('movable_object.barrier', 8)).toBe('barrier');            // vespa-patches/0001
    expect(comparisonClass('movable_object.trafficcone', 8)).toBe('traffic_cone');
    expect(comparisonClass('movable_object.barrier', 3)).toBeNull();                 // not in 1/3class
    expect(comparisonClass('movable_object.trafficcone', 1)).toBeNull();
    expect(comparisonClass('movable_object.debris', 8)).toBeNull();
    expect(comparisonClass('vehicle.emergency.police', 1)).toBeNull();
    expect(comparisonClass('something.new', 8)).toBeNull();
    expect(comparisonClass(null, 8)).toBeNull();
  });
});

describe('Rerun selection → box key', () => {
  const rec: Recording = {
    recordingId: 5, datasetId: 1, sceneId: 7, sceneToken: 'scene-tok', jobId: 12, status: 'READY', sdkVersion: '0.38.1',
    rerunRecordingId: 'ds2l-recording-5', timeline: 'sample', entities: { lidar: 'world/lidar', ego: 'world/ego', gt: 'world/gt', prediction: 'world/prediction' },
    samples: [
      { index: 0, sampleToken: 's0', timestampUs: 0, lidarPoints: 10, gtAnnotationIds: [11, 12], predictionIds: [900] },
      { index: 1, sampleToken: 's1', timestampUs: 1, lidarPoints: 10, gtAnnotationIds: [13], predictionIds: [] },
    ],
    contentUrl: '/api/recordings/5/content', sizeBytes: 1, errorMessage: null, errorCode: null, createdAt: 0,
  };
  it('maps entity + instance within the current sample only', () => {
    expect(boxKeyForSelection(rec, 'world/gt', 1, 0)).toBe('GT:1:s0:12');
    expect(boxKeyForSelection(rec, 'world/prediction', 0, 0)).toBe('VESPA:12:1:s0:900');
    expect(boxKeyForSelection(rec, 'world/gt', 1, 1)).toBeNull();
    expect(boxKeyForSelection(rec, 'world/lidar', 0, 0)).toBeNull();
    expect(indexForSample(rec, 's1')).toBe(1);
  });
});
