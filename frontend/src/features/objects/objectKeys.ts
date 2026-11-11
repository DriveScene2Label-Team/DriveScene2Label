import type { BoxView } from '@/api/models';

/**
 * Object identity for selection and "hide": a GT instance (same object in every frame) or one prediction box
 * (predictions have no track id, so a prediction is never matched across frames). Prefixes gt:/pred: are relied on by
 * the workspace store (hiding a layer drops a selection of that source).
 */
export function objectKey(box: BoxView): string {
  if (box.source === 'GT') return box.instanceToken ? `gt:${box.datasetId}:${box.instanceToken}` : `gt:box:${box.key}`;
  return `pred:${box.jobId}:${box.id}`;
}

/** instanceToken of a GT instance key, or null. */
export function instanceOfKey(key: string | null): string | null {
  if (!key || !key.startsWith('gt:') || key.startsWith('gt:box:')) return null;
  const rest = key.slice(3);
  const i = rest.indexOf(':');
  return i >= 0 ? rest.slice(i + 1) : null;
}
