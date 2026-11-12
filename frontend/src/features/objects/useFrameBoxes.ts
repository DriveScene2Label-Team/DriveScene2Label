import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { BoxView, JobResults, SampleRef } from '@/api/models';
import { jobResultsQuery, jobStatusQuery } from '@/api/queries';

export type PredState =
  | { kind: 'none' }
  | { kind: 'loading'; jobId: number }
  | { kind: 'error'; jobId: number; error: unknown; refetch: () => void }
  /** The shown job has no entry for this sample (other scene or dataset): nothing is drawn. */
  | { kind: 'not-in-job'; jobId: number }
  | { kind: 'ready'; jobId: number; boxes: BoxView[] };

/** Predictions of the shown completed job for one sample, matched by datasetId + sampleToken. */
export function predictionsFor(results: JobResults, sample: SampleRef): BoxView[] | null {
  if (results.datasetId !== sample.datasetId || !results.sampleTokens.has(sample.token)) return null;
  return results.boxesBySample.get(sample.token) ?? [];
}

export function usePredictions(resultJobId: number | null, sample: SampleRef | null): PredState {
  const q = useQuery({ ...jobResultsQuery(resultJobId ?? -1), enabled: resultJobId != null });
  if (resultJobId == null) return { kind: 'none' };
  if (q.isPending) return { kind: 'loading', jobId: resultJobId };
  if (q.isError) return { kind: 'error', jobId: resultJobId, error: q.error, refetch: () => void q.refetch() };
  if (!sample) return { kind: 'loading', jobId: resultJobId };
  const boxes = predictionsFor(q.data, sample);
  return boxes ? { kind: 'ready', jobId: resultJobId, boxes } : { kind: 'not-in-job', jobId: resultJobId };
}

/**
 * Boxes of the comparison job for one sample, marked `compare` so the cameras draw them in their own colour.
 * The same job as the shown result is not compared with itself.
 */
export function useComparePredictions(compareJobId: number | null, resultJobId: number | null, sample: SampleRef | null): BoxView[] {
  const id = compareJobId != null && compareJobId !== resultJobId ? compareJobId : null;
  const state = usePredictions(id, sample);
  const status = useQuery({ ...jobStatusQuery(id ?? -1), enabled: id != null });
  const tag = id == null ? '' : compareTagOf(id, status.data?.variant ?? null);
  const boxes = state.kind === 'ready' ? state.boxes : null;
  return useMemo(() => (boxes ? boxes.map((b) => ({ ...b, compare: true, compareTag: tag })) : []), [boxes, tag]);
}

/** Last model-version suffix ("ds2l-p1-p2+ver2-rigid" → "ver2-rigid"), else "#<jobId>". */
export function compareTagOf(jobId: number, variant: string | null): string {
  const last = variant ? variant.split('+').pop() : '';
  return last || `#${jobId}`;
}

export function visibleBoxes(gt: BoxView[] | null, pred: PredState, layers: { gt: boolean; pred: boolean; cmp?: boolean }, compare: BoxView[] = []): BoxView[] {
  const out: BoxView[] = [];
  if (layers.gt && gt) out.push(...gt);
  if (layers.pred && pred.kind === 'ready') out.push(...pred.boxes);
  if (layers.cmp && compare.length) out.push(...compare);
  return out;
}
