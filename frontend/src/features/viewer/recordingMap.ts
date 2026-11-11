import type { Recording } from '@/api/models';

/** Rerun reports entity paths with a leading slash ("/world/gt"); metadata uses "world/gt". */
export function normalizeEntity(path: string): string {
  return path.replace(/^\/+/, '');
}

export function indexForSample(rec: Recording, sampleToken: string | null): number {
  if (!sampleToken) return -1;
  return rec.samples.find((s) => s.sampleToken === sampleToken)?.index ?? -1;
}

/**
 * Selected Rerun instance → the same key the camera overlay and object list use.
 * Instance ids are only meaningful within the current sample; nothing is carried across frames.
 */
export function boxKeyForSelection(rec: Recording, entity: string, instance: number, sampleIndex: number): string | null {
  const s = rec.samples.find((x) => x.index === sampleIndex);
  if (!s || instance < 0) return null;
  if (entity === normalizeEntity(rec.entities.gt)) {
    const id = s.gtAnnotationIds[instance];
    return id == null ? null : `GT:${rec.datasetId}:${s.sampleToken}:${id}`;
  }
  if (rec.entities.prediction && entity === normalizeEntity(rec.entities.prediction) && rec.jobId != null) {
    const id = s.predictionIds[instance];
    return id == null ? null : `VESPA:${rec.jobId}:${rec.datasetId}:${s.sampleToken}:${id}`;
  }
  return null;
}

/**
 * Box key (per frame, from boxKeyForSelection) → object key used for selection (GT instance / prediction box).
 * `findGt` looks the GT box up (e.g. in the annotation query cache) to read its instance token.
 */
export function objectKeyForBoxKey(key: string, findGt: (boxKey: string) => { instanceToken: string | null; datasetId: number } | undefined): string | null {
  if (key.startsWith('VESPA:')) {
    const parts = key.split(':');
    return parts.length >= 5 ? `pred:${parts[1]}:${parts[parts.length - 1]}` : null;
  }
  if (key.startsWith('GT:')) {
    const box = findGt(key);
    if (!box) return null;
    return box.instanceToken ? `gt:${box.datasetId}:${box.instanceToken}` : `gt:box:${key}`;
  }
  return null;
}
