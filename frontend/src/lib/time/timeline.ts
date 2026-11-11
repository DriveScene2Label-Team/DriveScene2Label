/**
 * Time helpers over samples ordered by `timestampUs` (epoch microseconds).
 * Playback follows the real keyframe spacing; relative sync maps by fraction of each scene's time span.
 */
export interface Timed {
  readonly token: string;
  readonly timestampUs: number;
}

export const SPEEDS = [0.5, 1, 2, 4] as const;
export type Speed = (typeof SPEEDS)[number];

/** Fallback when two samples share a timestamp or the gap is invalid: nuScenes keyframes are ~2 Hz. */
export const FALLBACK_INTERVAL_MS = 500;
/** Upper bound so a data gap does not freeze playback for minutes. */
export const MAX_INTERVAL_MS = 5000;

/** Wall-clock delay before showing `samples[index + 1]` at the given speed. */
export function playbackDelayMs(samples: readonly Timed[], index: number, speed: number): number {
  const a = samples[index];
  const b = samples[index + 1];
  if (!a || !b || !(speed > 0)) return FALLBACK_INTERVAL_MS;
  const dt = (b.timestampUs - a.timestampUs) / 1000;
  const real = Number.isFinite(dt) && dt > 0 ? dt : FALLBACK_INTERVAL_MS;
  return Math.min(real, MAX_INTERVAL_MS) / speed;
}

export function indexOfToken(samples: readonly Timed[], token: string | null | undefined): number {
  if (!token) return -1;
  return samples.findIndex((s) => s.token === token);
}

/** Index of the sample whose timestamp is closest to `t`. Ties go to the earlier sample. */
export function nearestIndex(samples: readonly Timed[], t: number): number {
  if (!samples.length) return -1;
  let lo = 0;
  let hi = samples.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (samples[mid]!.timestampUs < t) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0 && Math.abs(samples[lo - 1]!.timestampUs - t) <= Math.abs(samples[lo]!.timestampUs - t)) return lo - 1;
  return lo;
}

/** Fraction (0..1) of a sample within its scene's time span. Single-frame / zero-span scenes return 0. */
export function relativeProgress(samples: readonly Timed[], index: number): number {
  const first = samples[0];
  const last = samples[samples.length - 1];
  const cur = samples[index];
  if (!first || !last || !cur) return 0;
  const span = last.timestampUs - first.timestampUs;
  if (!(span > 0)) return 0;
  return Math.min(1, Math.max(0, (cur.timestampUs - first.timestampUs) / span));
}

/**
 * Relative sync (FR-16): progress = (tA - startA)/(endA - startA); targetB = startB + progress·(endB - startB).
 * Returns the B index closest to targetB. Does not claim the two frames were captured at the same time.
 */
export function mapRelative(source: readonly Timed[], sourceIndex: number, target: readonly Timed[]): number {
  if (!target.length) return -1;
  const first = target[0]!;
  const last = target[target.length - 1]!;
  const span = last.timestampUs - first.timestampUs;
  if (!(span > 0)) return 0;
  const p = relativeProgress(source, sourceIndex);
  return nearestIndex(target, first.timestampUs + p * span);
}
