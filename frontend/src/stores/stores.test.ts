import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ImageCache } from '@/lib/imageCache';
import { resetWorkspace, useWorkspace } from './workspace';

describe('A/B pane independence', () => {
  beforeEach(() => resetWorkspace());

  it('keeps frame, playback, layers, selection and job separate when both panes open the same scene', () => {
    const s = useWorkspace.getState();
    s.openScene('A', { datasetId: 1, sceneId: 7, sampleToken: 's0' });
    s.openScene('B', { datasetId: 1, sceneId: 7, sampleToken: 's5' });
    s.requestSample('A', 's1', 'user');
    s.setPlaying('A', true);
    s.toggleLayer('A', 'gt');
    s.selectBox('B', 'GT:1:s5:3');
    s.watchJob('A', 12);
    const { A, B } = useWorkspace.getState().panes;
    expect([A.requestedSampleToken, B.requestedSampleToken]).toEqual(['s1', 's5']);
    expect([A.playing, B.playing]).toEqual([true, false]);
    expect([A.layers.gt, B.layers.gt]).toEqual([false, true]);
    expect([A.selectedBoxKey, B.selectedBoxKey]).toEqual([null, 'GT:1:s5:3']);
    expect([A.jobId, B.jobId]).toEqual([12, null]);
  });

  it('keeps the selected object across frames (object keys, not per-frame rows) and clears it with another scene', () => {
    const s = useWorkspace.getState();
    s.openScene('single', { datasetId: 1, sceneId: 7, sampleToken: 's0' });
    s.selectBox('single', 'gt:1:inst-a');
    s.requestSample('single', 's1', 'user');
    expect(useWorkspace.getState().panes.single.selectedBoxKey).toBe('gt:1:inst-a');
    s.openScene('single', { datasetId: 1, sceneId: 8 });
    expect(useWorkspace.getState().panes.single.selectedBoxKey).toBeNull();
  });

  it('hiding a layer drops a selection of that source only; names layer never does', () => {
    const s = useWorkspace.getState();
    s.openScene('A', { datasetId: 1, sceneId: 7 });
    s.selectBox('A', 'pred:12:900');
    s.toggleLayer('A', 'gt');
    expect(useWorkspace.getState().panes.A.selectedBoxKey).toBe('pred:12:900');
    s.toggleLayer('A', 'names');
    expect(useWorkspace.getState().panes.A.selectedBoxKey).toBe('pred:12:900');
    s.toggleLayer('A', 'pred');
    expect(useWorkspace.getState().panes.A.selectedBoxKey).toBeNull();
    expect(useWorkspace.getState().panes.A.layers).toEqual({ gt: false, pred: false, names: false });
  });

  it('keeps hidden objects per pane and resets them for another scene', () => {
    const s = useWorkspace.getState();
    s.openScene('A', { datasetId: 1, sceneId: 7 });
    s.openScene('B', { datasetId: 1, sceneId: 7 });
    s.toggleHidden('A', 'gt:1:inst-a');
    s.toggleHidden('A', 'pred:12:900');
    expect(useWorkspace.getState().panes.A.hidden).toEqual(['gt:1:inst-a', 'pred:12:900']);
    expect(useWorkspace.getState().panes.B.hidden).toEqual([]);
    s.toggleHidden('A', 'gt:1:inst-a');
    expect(useWorkspace.getState().panes.A.hidden).toEqual(['pred:12:900']);
    s.openScene('A', { datasetId: 1, sceneId: 9 });
    expect(useWorkspace.getState().panes.A.hidden).toEqual([]);
  });

  it('resets per-scene state when a pane switches to another scene', () => {
    const s = useWorkspace.getState();
    s.openScene('A', { datasetId: 1, sceneId: 7, sampleToken: 's3', jobId: 12 });
    s.showResult('A', 12);
    s.openScene('A', { datasetId: 1, sceneId: 8 });
    const A = useWorkspace.getState().panes.A;
    expect([A.sceneId, A.requestedSampleToken, A.jobId, A.resultJobId]).toEqual([8, null, null, null]);
  });

  it('only marks a frame displayed when told, keeping requested and displayed apart', () => {
    const s = useWorkspace.getState();
    s.openScene('single', { datasetId: 1, sceneId: 7, sampleToken: 's0' });
    s.markDisplayed('single', 's0');
    s.requestSample('single', 's1', 'playback');
    const p = useWorkspace.getState().panes.single;
    expect([p.requestedSampleToken, p.displayedSampleToken, p.lastOrigin]).toEqual(['s1', 's0', 'playback']);
  });
});

describe('image cache', () => {
  const make = (status = 200) => {
    const revoked: string[] = [];
    let n = 0;
    const fetchImpl = vi.fn(async (_u: RequestInfo | URL, init?: RequestInit) => {
      if (init?.signal?.aborted) throw new DOMException('aborted', 'AbortError');
      return new Response(status === 200 ? 'jpg' : '', { status });
    });
    const cache = new ImageCache({
      maxIdle: 2,
      fetchImpl: fetchImpl as unknown as typeof fetch,
      decode: async () => ({ width: 1600, height: 900 }),
      createObjectURL: () => `blob:${++n}`,
      revokeObjectURL: (u) => revoked.push(u),
    });
    return { cache, revoked, fetchImpl };
  };

  it('decodes, keeps held images and revokes evicted blob URLs', async () => {
    const { cache, revoked } = make();
    cache.acquire('/a');
    await cache.prefetch('/a');
    expect(cache.get('/a')).toMatchObject({ status: 'ready', width: 1600, objectUrl: 'blob:1' });
    for (const u of ['/b', '/c', '/d']) await cache.prefetch(u);
    expect(cache.get('/a')?.status).toBe('ready'); // held: never evicted
    expect(cache.get('/b')).toBeUndefined(); // idle LRU of 2
    expect(revoked).toContain('blob:2');
    cache.release('/a');
    cache.trim(0);
    expect(cache.size).toBe(0);
    expect(revoked).toContain('blob:1');
  });

  it('reports a missing file separately from a download failure and retries failed idle entries', async () => {
    const { cache, fetchImpl } = make(404);
    await cache.prefetch('/x');
    expect(cache.get('/x')).toMatchObject({ status: 'error', error: 'missing' });
    await cache.prefetch('/x');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
});
