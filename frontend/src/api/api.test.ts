import { afterEach, describe, expect, it, vi } from 'vitest';
import { calibrationDto, gtDto, jobResultsDto, jobStatusDto, poseDto, sampleDetailDto, sampleDto } from '@/test/fixtures';
import type { RecordingDto, SceneSearchResponseDto, SceneSearchResultDto } from './dto';
import { ApiError, getJson, toApiError } from './http';
import { gtToBox, toCalibration, toEgoPose, toJobResults, toJobStatus, toMatchScore, toRecording, toSampleFrame, toSearchResult } from './mappers';
import { matchTooltip } from '@/features/scenes/SceneCard';
import { fetchAllSceneSamples, SAMPLE_PAGE } from './queries';

afterEach(() => vi.restoreAllMocks());

describe('DTO → screen model mappers', () => {
  it('keys cameras by channel regardless of API order and keeps the LiDAR separately', () => {
    const detail = sampleDetailDto(sampleDto(0), ['LIDAR_TOP', 'CAM_BACK', 'CAM_FRONT', 'CAM_BACK_LEFT']);
    const f = toSampleFrame(detail);
    expect([...f.cameras.keys()].sort()).toEqual(['CAM_BACK', 'CAM_BACK_LEFT', 'CAM_FRONT']);
    expect(f.lidar?.channel).toBe('LIDAR_TOP');
    expect(f.cameras.get('CAM_FRONT')!.width).toBe(1600);
    expect(f.location).toBe('singapore-onenorth');
  });

  it('maps GT WORLD centre, size W/L/H and quaternion W/X/Y/Z by name, keeping the original category', () => {
    const b = gtToBox(gtDto(5, { rotationW: 0.9, rotationZ: 0.1, sizeW: 1.9, sizeL: 4.4 }));
    expect(b.source).toBe('GT');
    expect(b.sizeWLH).toEqual([1.9, 4.4, 1.6]);
    expect(b.rotation).toEqual({ w: 0.9, x: 0, y: 0, z: 0.1 });
    expect(b.label).toBe('vehicle.car');
    expect(b.key).toBe('GT:1:s0:5');
  });

  it('treats a missing GT category as unknown, never as a prediction class', () => {
    const { categoryName: _n, categoryToken: _t, ...old } = gtDto(6);
    expect(gtToBox(old).label).toBeNull();
  });

  it('turns flat calibration fields into pose + intrinsic, and null intrinsics into null', () => {
    const c = toCalibration(calibrationDto());
    expect(c.sensorToEgo.translation).toEqual([1.7, 0, 1.5]);
    expect(c.intrinsic).toEqual([1266, 0, 816, 0, 1266, 491, 0, 0, 1]);
    expect(toCalibration(calibrationDto({ intrinsic00: null })).intrinsic).toBeNull();
    expect(toEgoPose(poseDto()).egoToWorld.rotation).toEqual({ w: 1, x: 0, y: 0, z: 0 });
  });

  it('links predictions by top-level datasetId + sampleToken and keeps empty samples', () => {
    const r = toJobResults(jobResultsDto());
    expect(r.boxesBySample.get('s0')!.map((b) => b.key)).toEqual(['VESPA:12:1:s0:900']);
    expect(r.boxesBySample.get('s1')).toEqual([]);
    expect(r.classMode).toBe(8);
  });

  it('reads job context only when the server provides it', () => {
    expect(toJobStatus(jobStatusDto()).sceneToken).toBeNull();
    const s = toJobStatus(jobStatusDto({ sceneToken: 'scene-tok', classMode: 3, status: 'COMPLETED', completedAt: '2026-10-03T12:05:00Z' }));
    expect(s.sceneToken).toBe('scene-tok');
    expect(s.classMode).toBe(3);
    expect(s.completedAt).toBe(Date.parse('2026-10-03T12:05:00Z'));
  });

  it('exposes a recording content URL only when READY', () => {
    const base: Omit<RecordingDto, 'status'> = {
      recordingId: 5, datasetId: 1, sceneId: 7, sceneToken: 't', sceneName: 'scene-0061', jobId: null, sdkVersion: '0.38.1', exportVersion: 'v1',
      coordinateFrame: 'WORLD', applicationId: 'drivescene2label', rerunRecordingId: 'ds2l-recording-5', timeline: 'sample', timeTimeline: 'timestamp',
      entities: { lidar: 'world/lidar', ego: 'world/ego', gt: 'world/gt', prediction: null }, samples: [], contentUrl: '/api/recordings/5/content',
      sizeBytes: 1, errorMessage: null, createdAt: '2026-10-03T12:00:00Z', startedAt: null, completedAt: null,
    };
    expect(toRecording({ ...base, status: 'RUNNING' }).contentUrl).toBeNull();
    expect(toRecording({ ...base, status: 'READY' }).contentUrl).toBe('/api/recordings/5/content');
  });
});

describe('HTTP error model', () => {
  it('normalizes the business error body', async () => {
    const e = await toApiError(new Response(JSON.stringify({ code: 'HTTP_409', message: 'Job has not completed successfully' }), { status: 409 }), '/api/x');
    expect([e.status, e.code, e.message, e.transient]).toEqual([409, 'HTTP_409', 'Job has not completed successfully', false]);
  });
  it('normalizes Spring default errors and empty bodies', async () => {
    const e = await toApiError(new Response(JSON.stringify({ status: 405, error: 'Method Not Allowed', path: '/api/x' }), { status: 405 }), '/api/x');
    expect([e.status, e.message]).toEqual([405, 'Method Not Allowed']);
    const empty = await toApiError(new Response('', { status: 503 }), '/api/x');
    expect(empty.transient).toBe(true);
  });
  it('separates connection failure from an HTTP error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(getJson('/api/datasets')).rejects.toMatchObject({ kind: 'network', transient: true });
  });
  it('refuses non-Spring paths', async () => {
    await expect(getJson('http://127.0.0.1:8000/health')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('scene sample paging', () => {
  it('keeps paging past the first page and sorts by timestamp', async () => {
    const all = Array.from({ length: SAMPLE_PAGE + 3 }, (_, i) => sampleDto(i));
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = new URL(String(input), 'http://x');
      const offset = Number(url.searchParams.get('offset'));
      const limit = Number(url.searchParams.get('limit'));
      return new Response(JSON.stringify(all.slice(offset, offset + limit).reverse()), { status: 200 });
    });
    const samples = await fetchAllSceneSamples(7);
    expect(samples).toHaveLength(SAMPLE_PAGE + 3);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(samples[0]!.token).toBe('s0');
    expect(samples.at(-1)!.token).toBe(`s${SAMPLE_PAGE + 2}`);
  });
});

describe('search match score', () => {
  const dto = (extra: Partial<SceneSearchResultDto>): SceneSearchResultDto => ({
    sceneId: 7, datasetId: 1, sceneToken: 'scene-tok', sceneName: 'scene-1077', description: 'Night', score: 0.258, distance: 0.742,
    matchedImages: 234, contributingImages: 3, bestImageId: 42, bestSampleToken: 's0', bestImagePath: 'samples/CAM_FRONT/x.jpg',
    contentUrl: '/api/sensor-files/42/content', ...extra,
  });
  const response = (scenes: SceneSearchResultDto[]): SceneSearchResponseDto => ({
    query: 'rainy night road', modelName: 'ViT-L-14-quickgelu/openai', preprocess: 'lr-square-crop-mean',
    aggregation: 'TOP_K_AVERAGE', imageTopK: 3, keyframesOnly: true, scenes,
  });
  it('keeps the raw score and maps matchScore, tolerating servers without it', () => {
    const hits = toSearchResult(response([dto({ matchScore: 99 }), dto({}), dto({ matchScore: null })])).hits;
    expect(hits.map((h) => h.score)).toEqual([0.258, 0.258, 0.258]);
    expect(hits.map((h) => h.matchScore)).toEqual([99, null, null]);
  });
  it('rejects values that are not an integer 0..100', () => {
    expect([0, 100, 65].map(toMatchScore)).toEqual([0, 100, 65]);
    expect([-1, 101, 0.5, Number.NaN, '65', undefined].map(toMatchScore)).toEqual([null, null, null, null, null, null]);
  });
  it('tooltip shows the cosine value and says it is not a probability, without %', () => {
    const withScore = matchTooltip(0.258, 99);
    expect(withScore).toContain('코사인 유사도 0.258');
    expect(withScore).toContain('확률이 아니에요');
    expect(matchTooltip(0.258, null)).toContain('확률이 아니에요');
    expect(withScore + matchTooltip(0.258, null)).not.toContain('%');
  });
});
