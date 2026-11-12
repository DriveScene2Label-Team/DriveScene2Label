import { describe, expect, it } from 'vitest';
import { jobVariant } from '@/api/mappers';
import type { BoxView } from '@/api/models';
import { parseWorkspace, workspaceUrl } from '@/app/urls';
import { compareJobs, pairBoxes } from './compareBoxes';
import { compareTagOf, visibleBoxes, type PredState } from './useFrameBoxes';

const box = (id: number, extra: Partial<BoxView> = {}) => ({ id, key: `p${id}`, source: 'VESPA', jobId: 26, ...extra }) as BoxView;

describe('comparison job', () => {
  it('names a run by its model version suffix', () => {
    expect(jobVariant('acb2b6e8+ds2l-p1-p2+ver2-rigid')).toBe('ds2l-p1-p2+ver2-rigid');
    expect(jobVariant('acb2b6e8')).toBe('');
    expect(jobVariant(undefined)).toBeNull();
    expect(compareTagOf(35, 'ver2-rigid')).toBe('ver2-rigid');
    expect(compareTagOf(35, 'ds2l-p1-p2+ver2-rigid')).toBe('ver2-rigid');
    expect(compareTagOf(35, '')).toBe('#35');
    expect(compareTagOf(35, null)).toBe('#35');
  });

  it('adds comparison boxes only while their layer is on, after the predictions', () => {
    const pred: PredState = { kind: 'ready', jobId: 26, boxes: [box(1)] };
    const cmp = [box(2, { jobId: 35, compare: true })];
    expect(visibleBoxes(null, pred, { gt: true, pred: true, cmp: true }, cmp).map((b) => b.id)).toEqual([1, 2]);
    expect(visibleBoxes(null, pred, { gt: true, pred: true, cmp: false }, cmp).map((b) => b.id)).toEqual([1]);
    expect(visibleBoxes(null, pred, { gt: true, pred: false, cmp: true }, cmp).map((b) => b.id)).toEqual([2]);
  });

  it('round-trips the cmp URL parameter', () => {
    const url = workspaceUrl({ datasetId: 1, sceneId: 1, job: 26, cmp: 35 });
    expect(url).toContain('cmp=35');
    const sp = new URLSearchParams(url.slice(url.indexOf('?')));
    expect(parseWorkspace('1', sp)).toMatchObject({ job: 26, cmp: 35 });
    expect(parseWorkspace('1', new URLSearchParams('dataset=1&cmp=x')).cmp).toBeNull();
  });
});

const geo = (id: number, cls: string, x: number, extra: Partial<BoxView> = {}) =>
  box(id, { baseCls: cls, center: [x, 0, 0], sizeWLH: [2, 4, 1.5], rotation: { w: 1, x: 0, y: 0, z: 0 }, ...extra });

describe('pairing comparison boxes with predictions', () => {
  it('sorts boxes into same / changed / added and counts removed', () => {
    const pred = [geo(1, 'car', 0), geo(2, 'car', 10), geo(3, 'truck', 20), geo(4, 'pedestrian', 30)];
    const cmp = [
      geo(11, 'car', 0.01),                        // same (1 cm)
      geo(12, 'car', 11),                          // moved 1 m → changed
      geo(13, 'truck', 20, { sizeWLH: [2, 6, 1.5] }), // longer → changed
      geo(14, 'barrier', 40),                      // nothing nearby → added
    ];
    expect(pairBoxes(cmp, pred)).toEqual({ kinds: ['same', 'changed', 'changed', 'added'], removed: 1 });
  });

  it('does not let a moved box take the partner of an unchanged one', () => {
    const pred = [geo(1, 'car', 0)];
    expect(pairBoxes([geo(12, 'car', 0.5), geo(11, 'car', 0)], pred).kinds).toEqual(['added', 'same']);
  });

  it('a turned box is changed', () => {
    const turned = geo(11, 'car', 0, { rotation: { w: Math.cos(0.1), x: 0, y: 0, z: Math.sin(0.1) } });
    expect(pairBoxes([turned], [geo(1, 'car', 0)]).kinds).toEqual(['changed']);
  });

  it('sums over the samples both jobs cover', () => {
    const results = (jobId: number, bySample: Record<string, BoxView[]>) => ({
      jobId, datasetId: 1, mappingName: '8class', classMode: 8, sampleTokens: new Set(Object.keys(bySample)),
      boxesBySample: new Map(Object.entries(bySample)), boxCount: 0, editedCount: 0, artifactCount: 0, artifactPath: null,
    }) as never;
    const a = results(26, { s1: [geo(1, 'car', 0)], s2: [geo(2, 'car', 0)] });
    const b = results(35, { s1: [geo(11, 'car', 0)], s3: [geo(12, 'car', 0)] });
    expect(compareJobs(a, b)).toEqual({ same: 1, changed: 0, added: 0, removed: 0 });
  });
});
