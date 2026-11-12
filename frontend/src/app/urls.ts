/**
 * Shareable URLs. Numeric ids (dataset, scene, job) and original tokens (sample) are kept in separate parameters
 * and never substituted for each other.
 *
 *   /scenes?dataset=1&q=...
 *   /scenes/7?dataset=1&sample=TOKEN&job=12&cmp=35&view=split|six   (cmp: comparison job drawn in another colour)
 *   /compare?datasetA=1&sceneA=7&sampleA=..&jobA=..&datasetB=1&sceneB=7&sampleB=..&sync=relative&active=B
 */
export type WorkspaceView = 'split' | 'six';

export function parseId(v: string | null): number | null {
  if (v == null || !/^[1-9]\d*$/.test(v)) return null;
  const n = Number(v);
  return Number.isSafeInteger(n) ? n : null;
}

export function parseToken(v: string | null): string | null {
  return v && /^[A-Za-z0-9_.-]{1,128}$/.test(v) ? v : null;
}

export interface WorkspaceParams {
  datasetId: number | null;
  sceneId: number | null;
  sample: string | null;
  job: number | null;
  cmp: number | null;
  view: WorkspaceView;
}

export function parseWorkspace(sceneParam: string | undefined, sp: URLSearchParams): WorkspaceParams {
  return {
    datasetId: parseId(sp.get('dataset')),
    sceneId: parseId(sceneParam ?? null),
    sample: parseToken(sp.get('sample')),
    job: parseId(sp.get('job')),
    cmp: parseId(sp.get('cmp')),
    view: sp.get('view') === 'six' ? 'six' : 'split',
  };
}

export function workspaceUrl(p: { datasetId: number; sceneId: number; sample?: string | null; job?: number | null; cmp?: number | null; view?: WorkspaceView }): string {
  const sp = new URLSearchParams({ dataset: String(p.datasetId) });
  if (p.sample) sp.set('sample', p.sample);
  if (p.job != null) sp.set('job', String(p.job));
  if (p.cmp != null) sp.set('cmp', String(p.cmp));
  sp.set('view', p.view ?? 'split');
  return `/scenes/${p.sceneId}?${sp.toString()}`;
}

export function searchUrl(datasetId: number | null, q?: string): string {
  const sp = new URLSearchParams();
  if (datasetId != null) sp.set('dataset', String(datasetId));
  if (q) sp.set('q', q);
  const s = sp.toString();
  return s ? `/scenes?${s}` : '/scenes';
}

export interface ComparePaneParams {
  datasetId: number | null;
  sceneId: number | null;
  sample: string | null;
  job: number | null;
}

export interface CompareParams {
  A: ComparePaneParams;
  B: ComparePaneParams;
  sync: boolean;
  active: 'A' | 'B';
}

export function parseCompare(sp: URLSearchParams): CompareParams {
  const side = (s: 'A' | 'B'): ComparePaneParams => ({
    datasetId: parseId(sp.get(`dataset${s}`)),
    sceneId: parseId(sp.get(`scene${s}`)),
    sample: parseToken(sp.get(`sample${s}`)),
    job: parseId(sp.get(`job${s}`)),
  });
  return { A: side('A'), B: side('B'), sync: sp.get('sync') === 'relative', active: sp.get('active') === 'B' ? 'B' : 'A' };
}

export function compareUrl(p: CompareParams): string {
  const sp = new URLSearchParams();
  for (const s of ['A', 'B'] as const) {
    const v = p[s];
    if (v.datasetId != null) sp.set(`dataset${s}`, String(v.datasetId));
    if (v.sceneId != null) sp.set(`scene${s}`, String(v.sceneId));
    if (v.sample) sp.set(`sample${s}`, v.sample);
    if (v.job != null) sp.set(`job${s}`, String(v.job));
  }
  if (p.sync) sp.set('sync', 'relative');
  if (p.active === 'B') sp.set('active', 'B');
  return `/compare?${sp.toString()}`;
}
