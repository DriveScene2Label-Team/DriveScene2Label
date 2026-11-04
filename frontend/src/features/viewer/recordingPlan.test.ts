import { describe, expect, it } from 'vitest';
import type { Recording } from '@/api/models';
import { planRecording } from './recordingPlan';

const rec = (recordingId: number, jobId: number | null, status: Recording['status'], createdAt = recordingId): Recording => ({
  recordingId, datasetId: 1, sceneId: 8, sceneToken: 'scene-tok', jobId, status, sdkVersion: '0.38.1', rerunRecordingId: `r${recordingId}`,
  timeline: 'sample', entities: { lidar: 'world/lidar', ego: 'world/ego', gt: 'world/gt', prediction: jobId != null ? 'world/prediction' : null },
  samples: [], contentUrl: status === 'READY' ? `/api/recordings/${recordingId}/content` : null, sizeBytes: null, errorMessage: null,
  errorCode: null, createdAt,
});

describe('which 3D recording a pane shows', () => {
  it('a finished label job without its own recording keeps the GT recording on screen and asks for the job one', () => {
    const plan = planRecording([rec(2, null, 'READY')], 16, null);
    expect(plan.primary).toBeUndefined();
    expect(plan.fallback?.recordingId).toBe(2);
    expect(plan.autoCreate).toBe(true);
  });

  it('keeps showing GT while the job recording is being made, then switches to it', () => {
    const making = planRecording([rec(2, null, 'READY'), rec(17, 16, 'RUNNING')], 16, null);
    expect(making.primary?.recordingId).toBe(17);
    expect(making.fallback?.recordingId).toBe(2);
    expect(making.autoCreate).toBe(false);
    const ready = planRecording([rec(2, null, 'READY'), rec(17, 16, 'READY')], 16, null);
    expect(ready.primary?.recordingId).toBe(17);
    expect(ready.fallback).toBeUndefined();
  });

  it('a scene with no recording at all asks for a GT recording', () => {
    const plan = planRecording([], null, null);
    expect(plan.primary).toBeUndefined();
    expect(plan.fallback).toBeUndefined();
    expect(plan.autoCreate).toBe(true);
  });

  it('a failed recording is not requested again automatically and GT is not used to hide the failure', () => {
    const plan = planRecording([rec(2, null, 'READY'), rec(17, 16, 'FAILED')], 16, null);
    expect(plan.primary?.status).toBe('FAILED');
    expect(plan.autoCreate).toBe(false);
    expect(plan.fallback).toBeUndefined();
  });

  it('only a READY GT recording can stand in, and only for a job target', () => {
    expect(planRecording([rec(2, null, 'RUNNING')], 16, null).fallback).toBeUndefined();
    expect(planRecording([rec(2, null, 'RUNNING')], null, null).fallback).toBeUndefined();
    expect(planRecording([rec(2, null, 'READY'), rec(3, null, 'READY', 9)], 16, null).fallback?.recordingId).toBe(3); // newest
  });

  it('an explicit choice of the pane wins over the newest one', () => {
    const plan = planRecording([rec(10, 16, 'READY'), rec(17, 16, 'READY')], 16, 10);
    expect(plan.primary?.recordingId).toBe(10);
  });
});
