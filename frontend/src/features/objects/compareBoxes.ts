import type { BoxView, JobResults } from '@/api/models';

/**
 * Pairs the boxes of a comparison job with the shown predictions of the same sample.
 * same    = same class, centre within 5 cm, size within 5 cm, heading within ~0.8°: the run did not change it.
 * changed = same class, centre within 2 m but not "same": the box moved, grew or turned.
 * added   = no prediction of that class nearby. removed = prediction left without a partner.
 */
export type CompareKind = 'same' | 'changed' | 'added';
export interface CompareCounts { same: number; changed: number; added: number; removed: number }

const SAME_M = 0.05;
const NEAR_M = 2;
const SAME_DOT = 0.99997; // |q1·q2| ≥ cos(θ/2) for θ ≈ 0.9°

const dist = (a: BoxView, b: BoxView) => Math.hypot(a.center[0] - b.center[0], a.center[1] - b.center[1], a.center[2] - b.center[2]);
const sizeDiff = (a: BoxView, b: BoxView) => Math.max(...a.sizeWLH.map((v, i) => Math.abs(v - b.sizeWLH[i]!)));
const quatDot = (a: BoxView, b: BoxView) => { const p = a.rotation; const q = b.rotation; return Math.abs(p.w * q.w + p.x * q.x + p.y * q.y + p.z * q.z); };

export function isSameBox(a: BoxView, b: BoxView): boolean {
  return a.baseCls === b.baseCls && dist(a, b) <= SAME_M && sizeDiff(a, b) <= SAME_M && quatDot(a, b) >= SAME_DOT;
}

/** Kind of every comparison box (same order as `compare`) and how many predictions were left without a partner. */
export function pairBoxes(compare: readonly BoxView[], pred: readonly BoxView[]): { kinds: CompareKind[]; removed: number } {
  const used = new Set<number>();
  const kinds: CompareKind[] = compare.map(() => 'added');
  // Exact matches first, so a moved box cannot steal the partner of an unchanged neighbour.
  compare.forEach((c, i) => {
    const j = pred.findIndex((p, k) => !used.has(k) && isSameBox(c, p));
    if (j >= 0) { used.add(j); kinds[i] = 'same'; }
  });
  compare.forEach((c, i) => {
    if (kinds[i] !== 'added') return;
    let best = -1;
    let bestD = NEAR_M;
    pred.forEach((p, k) => {
      if (used.has(k) || p.baseCls !== c.baseCls) return;
      const d = dist(c, p);
      if (d <= bestD) { best = k; bestD = d; }
    });
    if (best >= 0) { used.add(best); kinds[i] = 'changed'; }
  });
  return { kinds, removed: pred.length - used.size };
}

/** Whole-job comparison over the samples both jobs cover. */
export function compareJobs(base: JobResults, other: JobResults): CompareCounts {
  const out: CompareCounts = { same: 0, changed: 0, added: 0, removed: 0 };
  if (base.datasetId !== other.datasetId) return out;
  for (const token of other.sampleTokens) {
    if (!base.sampleTokens.has(token)) continue;
    const { kinds, removed } = pairBoxes(other.boxesBySample.get(token) ?? [], base.boxesBySample.get(token) ?? []);
    for (const k of kinds) out[k] += 1;
    out.removed += removed;
  }
  return out;
}
