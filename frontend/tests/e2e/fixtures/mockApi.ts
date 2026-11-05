import { readFileSync, existsSync } from 'node:fs';
import type { Page, Route } from '@playwright/test';

/**
 * Route fixtures for `/api/*` that follow the real Spring DTOs (README_API.md). They exist to exercise UI flows in
 * the browser; they are not evidence of a live-server integration. Dataset id 3 (not 1) on purpose.
 */
export const DATASET = { id: 3, name: 'nuscenes', version: 'v1.0-mini', storageKey: 'nuscenes', rootRelativePath: '.', sourceChecksum: 'x' };
const CHANNELS = ['CAM_FRONT', 'CAM_FRONT_LEFT', 'CAM_FRONT_RIGHT', 'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT'];
const YAW: Record<string, number> = { CAM_FRONT: 0, CAM_FRONT_LEFT: 55, CAM_FRONT_RIGHT: -55, CAM_BACK: 180, CAM_BACK_LEFT: 110, CAM_BACK_RIGHT: -110 };
const T0 = 1_532_402_927_647_951;

export interface SceneFx { id: number; token: string; name: string; description: string; frames: number }
export const SCENES: SceneFx[] = [
  { id: 21, token: 'scene-tok-61', name: 'scene-0061', description: 'Parked truck, construction, intersection', frames: 4 },
  { id: 22, token: 'scene-tok-103', name: 'scene-0103', description: 'Many peds right, wait for turning car', frames: 3 },
  { id: 23, token: 'scene-tok-single', name: 'scene-0999', description: 'Single keyframe scene', frames: 1 },
];

const sampleId = (sceneId: number, i: number) => sceneId * 100 + i;
const sampleToken = (sceneId: number, i: number) => `smp-${sceneId}-${i}`;
const fileId = (sid: number, ch: string) => sid * 10 + CHANNELS.indexOf(ch) + 1;

function samplesOf(scene: SceneFx) {
  return Array.from({ length: scene.frames }, (_, i) => ({
    id: sampleId(scene.id, i), datasetId: DATASET.id, token: sampleToken(scene.id, i), sceneToken: scene.token,
    timestampUs: T0 + scene.id * 1e8 + i * 500_000, prevToken: i ? sampleToken(scene.id, i - 1) : null, nextToken: i < scene.frames - 1 ? sampleToken(scene.id, i + 1) : null,
  }));
}

function findSample(id: number) {
  for (const sc of SCENES) for (const s of samplesOf(sc)) if (s.id === id) return { scene: sc, sample: s, index: s.id - sc.id * 100 };
  return null;
}

/** Ego at (400 + 5·i, 1100, 0), facing world +x. */
const egoX = (i: number) => 400 + 5 * i;

/** q = yaw(ψ) ⊗ q_front, nuScenes-like camera orientations; W/X/Y/Z. */
function camQuat(ch: string) {
  const a = (YAW[ch]! * Math.PI) / 180 / 2;
  const [w1, z1] = [Math.cos(a), Math.sin(a)];
  const [w2, x2, y2, z2] = [0.5, -0.5, 0.5, -0.5];
  return { w: w1 * w2 - z1 * z2, x: w1 * x2 - z1 * y2, y: w1 * y2 + z1 * x2, z: w1 * z2 + z1 * w2 };
}

export function cameraSvg(channel: string, token: string): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900"><rect width="1600" height="900" fill="#1d2733"/><rect y="450" width="1600" height="450" fill="#2b2f36"/><line x1="0" y1="450" x2="1600" y2="450" stroke="#55606e" stroke-width="4"/><line x1="800" y1="0" x2="800" y2="900" stroke="#3a4552" stroke-width="2"/><text x="40" y="90" font-size="64" font-family="sans-serif" fill="#e8edf2">${channel}</text><text x="40" y="170" font-size="48" font-family="monospace" fill="#9fb0c2">${token}</text><text x="40" y="860" font-size="36" font-family="sans-serif" fill="#ffcc4d">E2E FIXTURE IMAGE</text></svg>`;
}

export interface MockOptions {
  /** CAM_BACK missing from this sample id's file list. */
  missingCameraSample?: number;
  /** CAM_BACK_RIGHT content returns 404 for this sample id. */
  brokenImageSample?: number;
  /** Delay (ms) for sample detail by sample id. */
  detailDelay?: Record<number, number>;
  /** Job status sequence returned by successive GETs for job 41. */
  jobSequence?: Array<'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 503>;
  /** First N results GETs fail with 500. */
  resultsFailures?: number;
  /** First N job POSTs are aborted (lost response). */
  postAborts?: number;
  /** recording behaviour */
  recording?: 'none' | 'fail-then-ready' | 'ready';
  rrdPath?: string;
  /** Search response mode. */
  search?: 'hits' | 'empty' | 'error';
  /** GET /api/system/status behaviour (default: UNKNOWN origin, every feature READY). 'missing' = older backend (404). */
  status?: {
    origin?: 'SYNTHETIC' | 'NUSCENES' | 'UNKNOWN';
    vespa?: 'READY' | 'CONFIGURED' | 'UNAVAILABLE' | 'configured-then-ready';
    vespaReason?: string;
    search?: 'READY' | 'UNAVAILABLE';
    recording?: 'READY' | 'UNAVAILABLE';
    instanceId?: string;
    missing?: boolean;
    /** Per-feature validity (expiresAt − checkedAt) in ms; default 600 s (the app caps it at 90 s). */
    ttlMs?: Partial<Record<'media' | 'search' | 'vespa' | 'recording', number>>;
  };
  /** Delay (ms) before answering job POSTs. */
  postDelayMs?: number;
  /** Delay (ms) before answering recording POSTs. */
  recordingPostDelayMs?: number;
  /** First N recording content GETs fail with 500. */
  contentFailures?: number;
  /** errorCode on a FAILED job 41. */
  failedErrorCode?: string | null;
  /** Label edit API: 'missing' = older backend without it (404). */
  labelEdits?: 'missing';
}

/** Server-side label edit state of the fixture (same rules as LabelEditService, simplified). */
interface Override { label?: string; deleted?: boolean }
interface EditFx {
  id: number; datasetId: number; sceneId: number; jobId: number | null; targetType: 'ANNOTATION' | 'PREDICTION'; action: 'RENAME' | 'DELETE';
  scope: 'SAMPLE' | 'INSTANCE'; instanceToken: string | null; fromLabel: string; toLabel: string | null; targetIds: number[]; sampleTokens: string[];
  createdAt: string; revertedAt: string | null; prev: Record<string, Override | null>;
}
const LABELS = ['car', 'truck', 'bus', 'trailer', 'construction_vehicle', 'pedestrian', 'motorcycle', 'bicycle', 'vehicle'];
const gtBase = (cat: string | null) => (cat === 'vehicle.car' ? 'car' : cat ?? 'unknown');

export interface MockLog {
  /** Set at any time during a test: the status API then fails (HTTP 500 or dropped connection) until reset to null. */
  statusFailure: null | 500 | 'abort';
  /** Set during a test: status GETs stay unanswered (no response, no error) until set back to false. */
  statusHang: boolean;
  /** Set during a test to make the status API report another DB instance (server swapped). */
  instanceId: string | null;
  statusCalls: Array<{ datasetId: string | null; refresh: boolean }>;
  contentGets: number;
  jobPosts: Array<{ key: string | null; body: unknown }>;
  recordingPosts: Array<{ sceneId: number; body: unknown }>;
  statusGets: number;
  resultGets: number;
}

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

export function gtFor(sid: number) {
  const f = findSample(sid);
  if (!f) return [];
  const x = egoX(f.index);
  // Same instance token in every frame of the scene (an object = one nuScenes instance across frames).
  const mk = (id: number, dx: number, dy: number, cat: string | null) => ({
    id, datasetId: DATASET.id, token: `ann-${id}`, sampleToken: f.sample.token, instanceToken: `inst-${f.scene.id}-${id % 10}`, visibilityToken: '4',
    centerX: x + dx, centerY: 1100 + dy, centerZ: 0.8, sizeW: 1.9, sizeL: 4.5, sizeH: 1.6, rotationW: 1, rotationX: 0, rotationY: 0, rotationZ: 0,
    numLidarPts: 40, numRadarPts: 1, prevToken: null, nextToken: null, categoryToken: cat ? `cat-${cat}` : null, categoryName: cat,
  });
  return [mk(sid * 10 + 1, 15, 0, 'vehicle.car'), mk(sid * 10 + 2, 12, 5, 'movable_object.barrier'), mk(sid * 10 + 3, -14, 0, null)];
}

export async function installMockApi(page: Page, opts: MockOptions = {}): Promise<MockLog> {
  const log: MockLog = { statusFailure: null, statusHang: false, instanceId: null, statusCalls: [], contentGets: 0, jobPosts: [], recordingPosts: [], statusGets: 0, resultGets: 0 };
  let contentFailures = opts.contentFailures ?? 0;
  let vespaRefreshed = false;
  let postAborts = opts.postAborts ?? 0;
  let resultsFailures = opts.resultsFailures ?? 0;
  const seq = opts.jobSequence ?? ['PENDING', 'RUNNING', 'COMPLETED'];
  // Recordings belong to one scene of one server instance (a swapped DB does not have them).
  const recordings: Array<{ id: number; status: string; jobId: number | null; sceneId: number; instanceId: string }> = [];
  const currentInstance = () => log.instanceId ?? opts.status?.instanceId ?? '11111111-1111-4111-8111-111111111111';
  let recordingSeq = 4;
  const overrides = new Map<string, Override>();
  const edits: EditFx[] = [];
  const allGt = (sceneId: number) => { const sc = SCENES.find((x) => x.id === sceneId); return sc ? samplesOf(sc).flatMap((smp) => gtFor(smp.id)) : []; };
  const withOverride = <T extends { id: number }>(type: string, row: T) => {
    const o = overrides.get(`${type}:${row.id}`);
    return { ...row, labelOverride: o?.label ?? null, deleted: !!o?.deleted };
  };
  const conflict = (e: EditFx) => edits.some((x) => x.id > e.id && !x.revertedAt && x.targetType === e.targetType && x.targetIds.some((t) => e.targetIds.includes(t)));
  const editView = (e: EditFx) => { const { prev: _p, ...rest } = e; return { ...rest, count: e.targetIds.length, revertible: !e.revertedAt && !conflict(e) }; };
  const setOv = (key: string, o: Override, base: string) => {
    const next: Override = { ...o };
    if (!next.label || next.label === base) delete next.label;
    if (!next.deleted) delete next.deleted;
    if (Object.keys(next).length) overrides.set(key, next); else overrides.delete(key);
  };
  const applyEdit = (e: Omit<EditFx, 'id' | 'createdAt' | 'revertedAt' | 'prev'>, keys: string[], bases: string[]) => {
    const prev = Object.fromEntries(keys.map((k) => [k, overrides.has(k) ? { ...overrides.get(k)! } : null]));
    keys.forEach((k, i) => setOv(k, e.action === 'RENAME' ? { ...overrides.get(k), label: e.toLabel! } : { ...overrides.get(k), deleted: true }, bases[i]!));
    const full: EditFx = { ...e, id: edits.length + 1, createdAt: new Date().toISOString(), revertedAt: null, prev };
    edits.push(full);
    return { edit: editView(full) };
  };

  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const p = url.pathname;
    const m = (re: RegExp) => p.match(re);
    let r: RegExpMatchArray | null;

    if (p === '/api/system/status') {
      const refresh = url.searchParams.get('refresh') === 'true';
      log.statusCalls.push({ datasetId: url.searchParams.get('datasetId'), refresh });
      if (log.statusHang) {
        // never answered while hanging; released (as a dropped connection) only to let the page close cleanly
        await new Promise<void>((resolve) => { const t = setInterval(() => { if (!log.statusHang) { clearInterval(t); resolve(); } }, 200); });
        return route.abort('connectionrefused').catch(() => undefined);
      }
      if (log.statusFailure === 'abort') return route.abort('connectionrefused');
      if (log.statusFailure === 500) return json(route, { code: 'HTTP_500', message: 'status failed' }, 500);
      const st = opts.status ?? {};
      if (st.missing) return json(route, { timestamp: '2026-10-05T00:00:00Z', status: 404, error: 'Not Found', path: p }, 404);
      if (refresh) vespaRefreshed = true;
      const now = new Date().toISOString();
      const nowMs = Date.parse(now);
      const later = new Date(nowMs + 600_000).toISOString();
      const cap = (state: string, reasonCode: string | null, message: string | null, extra: Record<string, unknown> = {}) =>
        ({ state, canExecute: state === 'READY', reasonCode, message, checkedAt: now, expiresAt: later, ...extra });
      const ttl = (k: 'media' | 'search' | 'vespa' | 'recording', c: Record<string, unknown>) =>
        (st.ttlMs?.[k] != null ? { ...c, expiresAt: new Date(nowMs + st.ttlMs[k]!).toISOString() } : c);
      const origin = st.origin ?? 'UNKNOWN';
      let vespa = cap('READY', null, null, { executor: 'local' });
      const mode = st.vespa ?? 'READY';
      if (origin === 'SYNTHETIC') vespa = cap('UNAVAILABLE', 'SYNTHETIC_DATASET', '테스트(합성) 데이터에서는 실제 VESPA 실행을 막아 두었어요.', { executor: 'local' });
      else if (mode === 'CONFIGURED' || (mode === 'configured-then-ready' && !vespaRefreshed)) vespa = cap('CONFIGURED', 'EXECUTOR_NOT_CHECKED', 'VESPA 설정은 있지만 실행 환경을 아직 확인하지 않았어요.', { executor: 'local' });
      else if (mode === 'UNAVAILABLE') vespa = cap('UNAVAILABLE', st.vespaReason ?? 'VESPA_NOT_CONFIGURED', 'VESPA 실행 환경이 설정되지 않았어요.', { executor: 'local' });
      const ds = url.searchParams.get('datasetId');
      return json(route, {
        schemaVersion: 1, instanceId: currentInstance(), checkedAt: now,
        dataset: ds ? { id: Number(ds), version: 'v1.0-mini', origin, metadataChecksum: 'c'.repeat(64), mediaValidation: 'PARTIAL' } : null,
        capabilities: {
          catalog: cap('READY', null, null),
          media: ttl('media', { ...cap('CONFIGURED', 'MEDIA_NOT_FULLY_VALIDATED', '센서 파일 일부만 확인했어요.'), canExecute: true }),
          search: ttl('search', st.search === 'UNAVAILABLE' ? cap('UNAVAILABLE', 'EMBEDDINGS_NOT_READY', '이 데이터셋의 검색 인덱스(이미지 임베딩)가 아직 없어요.') : cap('READY', null, '검색 인덱스 이미지 10개')),
          vespa: ttl('vespa', vespa),
          recording: ttl('recording', st.recording === 'UNAVAILABLE' ? cap('UNAVAILABLE', 'RECORDING_NOT_CONFIGURED', '3D recording exporter가 설정되지 않았어요.') : cap('READY', null, null)),
        },
      });
    }
    if (p === '/api/datasets') return json(route, [DATASET]);
    if ((r = m(/^\/api\/datasets\/(\d+)\/scenes$/))) {
      if (Number(r[1]) !== DATASET.id) return json(route, { code: 'HTTP_404', message: 'Record not found' }, 404);
      return json(route, SCENES.map((s) => ({ id: s.id, datasetId: DATASET.id, token: s.token, logToken: 'log', name: s.name, description: s.description, nbrSamples: s.frames, firstSampleToken: sampleToken(s.id, 0), lastSampleToken: sampleToken(s.id, s.frames - 1) })));
    }
    if ((r = m(/^\/api\/scenes\/(\d+)\/samples$/))) {
      const sc = SCENES.find((s) => s.id === Number(r![1]));
      if (!sc) return json(route, { code: 'HTTP_404', message: 'Record not found' }, 404);
      const limit = Number(url.searchParams.get('limit') ?? 100);
      const offset = Number(url.searchParams.get('offset') ?? 0);
      return json(route, samplesOf(sc).slice(offset, offset + limit));
    }
    if ((r = m(/^\/api\/samples\/(\d+)$/))) {
      const sid = Number(r[1]);
      const f = findSample(sid);
      if (!f) return json(route, { code: 'HTTP_404', message: 'Record not found' }, 404);
      const delay = opts.detailDelay?.[sid];
      if (delay) await new Promise((res) => setTimeout(res, delay));
      const chans = CHANNELS.filter((c) => !(opts.missingCameraSample === sid && c === 'CAM_BACK'));
      const files = [...chans, 'LIDAR_TOP'].map((ch) => ({
        id: ch === 'LIDAR_TOP' ? sid * 10 + 9 : fileId(sid, ch), token: `sd-${sid}-${ch}`, channel: ch, modality: ch === 'LIDAR_TOP' ? 'lidar' : 'camera',
        relativePath: `samples/${ch}/${sid}.jpg`, timestampUs: f.sample.timestampUs + 10, isKeyFrame: true, width: ch === 'LIDAR_TOP' ? 0 : 1600, height: ch === 'LIDAR_TOP' ? 0 : 900,
        egoPoseToken: `ep-${sid}`, calibratedSensorToken: `cs-${ch}`, vehicleX: egoX(f.index), vehicleY: 1100, vehicleZ: 0,
        contentUrl: `/api/sensor-files/${ch === 'LIDAR_TOP' ? sid * 10 + 9 : fileId(sid, ch)}/content`,
      })).reverse(); // API order must not matter
      return json(route, { sample: f.sample, sensorFiles: files, maps: [{ id: 1, token: 'map', relativePath: 'maps/x.png', location: 'singapore-onenorth', contentUrl: '/api/maps/1/content' }] });
    }
    if ((r = m(/^\/api\/samples\/(\d+)\/annotations$/))) {
      const all = url.searchParams.get('includeDeleted') === 'true';
      return json(route, gtFor(Number(r[1])).map((g) => withOverride('ANNOTATION', g)).filter((g) => all || !g.deleted));
    }
    if ((r = m(/^\/api\/scenes\/(\d+)\/annotations$/))) return json(route, allGt(Number(r[1])).map((g) => withOverride('ANNOTATION', g)).filter((g) => !g.deleted));
    const editsMissing = opts.labelEdits === 'missing';
    if ((r = m(/^\/api\/scenes\/(\d+)\/label-edits$/))) {
      if (editsMissing) return json(route, { status: 404, error: 'Not Found', path: p }, 404);
      const sceneId = Number(r[1]);
      const job = url.searchParams.get('jobId');
      return json(route, edits.filter((e) => e.sceneId === sceneId && (e.targetType === 'ANNOTATION' || String(e.jobId) === job)).sort((a, b) => b.id - a.id).map(editView));
    }
    if ((r = m(/^\/api\/annotations\/(\d+)$/)) && (req.method() === 'PATCH' || req.method() === 'DELETE')) {
      if (editsMissing) return json(route, { status: 404, error: 'Not Found', path: p }, 404);
      const id = Number(r[1]);
      const f = findSample(Math.floor(id / 10));
      const g = f && gtFor(f.sample.id).find((x) => x.id === id);
      if (!f || !g) return json(route, { code: 'HTTP_404', message: 'Annotation not found' }, 404);
      const body = req.method() === 'PATCH' ? (req.postDataJSON() as { label: string; scope?: string }) : null;
      const scope = (body?.scope ?? url.searchParams.get('scope') ?? 'SAMPLE') as 'SAMPLE' | 'INSTANCE';
      const self = overrides.get(`ANNOTATION:${id}`);
      if (self?.deleted) return json(route, { code: 'TARGET_DELETED', message: 'The annotation is already deleted' }, 409);
      if (body && !LABELS.includes(body.label)) return json(route, { code: 'INVALID_LABEL', message: 'invalid label' }, 400);
      const targets = (scope === 'INSTANCE' ? allGt(f.scene.id).filter((x) => x.instanceToken === g.instanceToken) : [g])
        .filter((x) => !overrides.get(`ANNOTATION:${x.id}`)?.deleted)
        .filter((x) => !body || (overrides.get(`ANNOTATION:${x.id}`)?.label ?? gtBase(x.categoryName)) !== body.label);
      if (!targets.length) return json(route, { code: 'SAME_LABEL', message: 'The annotation already has this class' }, 400);
      return json(route, applyEdit({
        datasetId: DATASET.id, sceneId: f.scene.id, jobId: null, targetType: 'ANNOTATION', action: body ? 'RENAME' : 'DELETE', scope, instanceToken: g.instanceToken,
        fromLabel: self?.label ?? gtBase(g.categoryName), toLabel: body?.label ?? null, targetIds: targets.map((x) => x.id), sampleTokens: targets.map((x) => x.sampleToken),
      }, targets.map((x) => `ANNOTATION:${x.id}`), targets.map((x) => gtBase(x.categoryName))));
    }
    if ((r = m(/^\/api\/auto-label\/predictions\/(\d+)$/))) {
      if (editsMissing) return json(route, { status: 404, error: 'Not Found', path: p }, 404);
      const id = Number(r[1]);
      const sc = SCENES.find((x) => samplesOf(x).some((smp) => 5000 + smp.id === id));
      if (!sc) return json(route, { code: 'HTTP_404', message: 'Prediction not found' }, 404);
      const smp = samplesOf(sc).find((x) => 5000 + x.id === id)!;
      const key = `PREDICTION:${id}`;
      const cur = overrides.get(key);
      if (cur?.deleted) return json(route, { code: 'TARGET_DELETED', message: 'deleted' }, 409);
      const body = req.method() === 'PATCH' ? (req.postDataJSON() as { label: string }) : null;
      if (body && (cur?.label ?? 'car') === body.label) return json(route, { code: 'SAME_LABEL', message: 'same' }, 400);
      return json(route, applyEdit({
        datasetId: DATASET.id, sceneId: sc.id, jobId: sc.id === 22 ? 77 : 41, targetType: 'PREDICTION', action: body ? 'RENAME' : 'DELETE', scope: 'SAMPLE', instanceToken: null,
        fromLabel: cur?.label ?? 'car', toLabel: body?.label ?? null, targetIds: [id], sampleTokens: [smp.token],
      }, [key], ['car']));
    }
    if ((r = m(/^\/api\/label-edits\/(\d+)\/revert$/))) {
      if (editsMissing) return json(route, { status: 404, error: 'Not Found', path: p }, 404);
      const e = edits.find((x) => x.id === Number(r![1]));
      if (!e) return json(route, { code: 'HTTP_404', message: 'Edit not found' }, 404);
      if (e.revertedAt) return json(route, { code: 'ALREADY_REVERTED', message: 'already reverted' }, 409);
      if (conflict(e)) return json(route, { code: 'LATER_EDIT_EXISTS', message: 'revert the newest edit first' }, 409);
      for (const [k, v] of Object.entries(e.prev)) { if (v) overrides.set(k, v); else overrides.delete(k); }
      e.revertedAt = new Date().toISOString();
      return json(route, { edit: editView(e) });
    }
    if ((r = m(/^\/api\/sensor-files\/(\d+)\/(calibration|pose|content)$/))) {
      const id = Number(r[1]);
      const sid = Math.floor(id / 10);
      const ch = CHANNELS[(id % 10) - 1] ?? 'LIDAR_TOP';
      const f = findSample(sid);
      if (!f) return json(route, { code: 'HTTP_404', message: 'Record not found' }, 404);
      if (r[2] === 'calibration') {
        const q = camQuat(ch);
        return json(route, { id: 1, datasetId: DATASET.id, token: `cs-${ch}`, sensorToken: `sensor-${ch}`, translationX: 1.5, translationY: 0, translationZ: 1.5, rotationW: q.w, rotationX: q.x, rotationY: q.y, rotationZ: q.z, intrinsic00: 1260, intrinsic01: 0, intrinsic02: 800, intrinsic10: 0, intrinsic11: 1260, intrinsic12: 450, intrinsic20: 0, intrinsic21: 0, intrinsic22: 1 });
      }
      if (r[2] === 'pose') return json(route, { id, datasetId: DATASET.id, token: `ep-${sid}`, timestampUs: f.sample.timestampUs, translationX: egoX(f.index), translationY: 1100, translationZ: 0, rotationW: 1, rotationX: 0, rotationY: 0, rotationZ: 0 });
      if (opts.brokenImageSample === sid && ch === 'CAM_BACK_RIGHT') return json(route, { code: 'HTTP_404', message: 'Dataset file unavailable' }, 404);
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: cameraSvg(ch, f.sample.token) });
    }
    if (p === '/api/search/scenes') {
      if (opts.search === 'error') return json(route, { code: 'HTTP_503', message: 'AI server unavailable' }, 503);
      const hits = opts.search === 'empty' ? [] : [SCENES[1]!, SCENES[0]!].map((s, i) => ({
        sceneId: s.id, datasetId: DATASET.id, sceneToken: s.token, sceneName: s.name, description: s.description, score: 0.31 - i * 0.05, distance: 0.69 + i * 0.05,
        matchedImages: 200, contributingImages: 3, bestImageId: fileId(sampleId(s.id, 1), 'CAM_FRONT'), bestSampleToken: sampleToken(s.id, 1), bestImagePath: 'samples/CAM_FRONT/x.jpg',
        contentUrl: `/api/sensor-files/${fileId(sampleId(s.id, 1), 'CAM_FRONT')}/content`,
      }));
      return json(route, { query: url.searchParams.get('q'), modelName: 'ViT-L-14-quickgelu/openai', preprocess: 'clip-text-tokenizer', aggregation: 'TOP_K_AVERAGE', imageTopK: 3, keyframesOnly: true, scenes: hits });
    }
    if (p === '/api/auto-label/jobs' && req.method() === 'POST') {
      log.jobPosts.push({ key: req.headers()['idempotency-key'] ?? null, body: req.postDataJSON() });
      if (opts.postDelayMs) await new Promise((res) => setTimeout(res, opts.postDelayMs));
      if (postAborts > 0) { postAborts--; return route.abort('connectionreset'); }
      return json(route, { jobId: 41, status: 'PENDING' }, 202);
    }
    if ((r = m(/^\/api\/auto-label\/jobs\/(\d+)$/))) {
      const id = Number(r[1]);
      if (id === 77) return json(route, { jobId: 77, datasetId: DATASET.id, status: 'COMPLETED', errorMessage: null, createdAt: '2026-10-03T12:00:00Z', startedAt: '2026-10-03T12:00:01Z', completedAt: '2026-10-03T12:03:00Z', sceneToken: 'scene-tok-103', sceneId: 22, sceneName: 'scene-0103', classMode: 8, mappingName: '8class' });
      if (id !== 41) return json(route, { code: 'HTTP_404', message: 'Job not found' }, 404);
      const st = seq[Math.min(log.statusGets, seq.length - 1)]!;
      log.statusGets++;
      if (st === 503) return json(route, { code: 'DATABASE_UNAVAILABLE', message: 'Database operation unavailable' }, 503);
      const done = st === 'COMPLETED' || st === 'FAILED';
      return json(route, {
        jobId: 41, datasetId: DATASET.id, status: st, errorMessage: st === 'FAILED' ? (opts.failedErrorCode === 'AI_ENDPOINT_UNSUPPORTED' ? 'AI server has no /auto-label endpoint (HTTP 404)' : 'AI request failed or timed out') : null,
        errorCode: st === 'FAILED' ? (opts.failedErrorCode ?? null) : null,
        createdAt: '2026-10-03T12:00:00Z', startedAt: st === 'PENDING' ? null : '2026-10-03T12:00:01Z', completedAt: done ? '2026-10-03T12:02:31Z' : null,
        sceneToken: 'scene-tok-61', sceneId: 21, sceneName: 'scene-0061', classMode: 8, mappingName: '8class',
      });
    }
    if ((r = m(/^\/api\/auto-label\/jobs\/(\d+)\/results$/))) {
      log.resultGets++;
      if (resultsFailures > 0) { resultsFailures--; return json(route, { code: 'HTTP_500', message: 'boom' }, 500); }
      const sc = Number(r[1]) === 77 ? SCENES[1]! : SCENES[0]!;
      const smp = samplesOf(sc);
      const boxes = smp.flatMap((s, i) => (i === smp.length - 1 ? [] : [{
        id: 5000 + s.id, sampleToken: s.token, boxIndex: 0, detectionName: 'car', centerX: egoX(i) + 15.3, centerY: 1100.2, centerZ: 0.8, sizeW: 2, sizeL: 4.3, sizeH: 1.6,
        rotationW: 1, rotationX: 0, rotationY: 0, rotationZ: 0, velocityX: 1, velocityY: 0, detectionScore: 1, attributeName: '',
      }])).map((b) => withOverride('PREDICTION', b)).filter((b) => !b.deleted);
      return json(route, { jobId: Number(r[1]), datasetId: DATASET.id, mappingName: '8class', coordinateFrame: 'WORLD', scoreType: 'VESPA_CONSTANT', sampleTokens: smp.map((s) => s.token), boxes, artifacts: [] });
    }
    if ((r = m(/^\/api\/scenes\/(\d+)\/recordings$/))) {
      if (req.method() === 'POST') {
        log.recordingPosts.push({ sceneId: Number(r[1]), body: req.postDataJSON() });
        const instance = currentInstance();
        if (opts.recordingPostDelayMs) await new Promise((res) => setTimeout(res, opts.recordingPostDelayMs));
        recordingSeq++;
        const fail = opts.recording === 'fail-then-ready' && log.recordingPosts.length === 1;
        recordings.unshift({ id: recordingSeq, status: fail ? 'FAILED' : 'READY', jobId: (req.postDataJSON() as { jobId?: number }).jobId ?? null, sceneId: Number(r[1]), instanceId: instance });
        return json(route, { recordingId: recordingSeq, status: 'PENDING', reused: false }, 202);
      }
      const sceneId = Number(r[1]);
      const mine = recordings.filter((x) => x.sceneId === sceneId && x.instanceId === currentInstance());
      const list = opts.recording === 'ready' && !recordings.length ? [recordingView(5, 'READY', null, sceneId)] : mine.map((x) => recordingView(x.id, x.status, x.jobId, x.sceneId));
      return json(route, list);
    }
    if ((r = m(/^\/api\/recordings\/(\d+)$/))) {
      const id = Number(r[1]);
      const st = recordings.find((x) => x.id === id) ?? { id, status: 'READY', jobId: null, sceneId: 21 };
      return json(route, recordingView(id, st.status, st.jobId, st.sceneId));
    }
    if ((r = m(/^\/api\/recordings\/(\d+)\/content$/))) {
      log.contentGets++;
      if (contentFailures > 0) { contentFailures--; return json(route, { code: 'HTTP_500', message: 'boom' }, 500); }
      if (!opts.rrdPath || !existsSync(opts.rrdPath)) return json(route, { code: 'HTTP_404', message: 'Recording file not found' }, 404);
      return route.fulfill({ status: 200, contentType: 'application/octet-stream', body: readFileSync(opts.rrdPath) });
    }
    return json(route, { status: 404, error: 'Not Found', path: p }, 404);
  });
  return log;
}

function recordingView(id: number, status: string, jobId: number | null, sceneId: number) {
  const sc = SCENES.find((s) => s.id === sceneId) ?? SCENES[0]!;
  const smp = samplesOf(sc);
  const ready = status === 'READY';
  return {
    recordingId: id, datasetId: DATASET.id, sceneId: sc.id, sceneToken: sc.token, sceneName: sc.name, jobId, status, sdkVersion: '0.38.1', exportVersion: 'ds2l-rrd-v1',
    coordinateFrame: 'WORLD', applicationId: ready ? 'drivescene2label' : null, rerunRecordingId: ready ? `ds2l-recording-${id}` : null, timeline: ready ? 'sample' : null, timeTimeline: ready ? 'timestamp' : null,
    entities: ready ? { lidar: 'world/lidar', ego: 'world/ego', gt: 'world/gt', prediction: jobId != null ? 'world/prediction' : null } : null,
    samples: ready ? smp.map((s, i) => ({ index: i, sampleToken: s.token, timestampUs: s.timestampUs, lidarPoints: 1321, gtAnnotationIds: gtFor(s.id).map((g) => g.id), predictionIds: [] })) : [],
    contentUrl: ready ? `/api/recordings/${id}/content` : null, sizeBytes: ready ? 98292 : null, errorMessage: status === 'FAILED' ? 'AI recording export failed (HTTP 502 RECORDING_EXPORT_FAILED)' : null, errorCode: status === 'FAILED' ? 'RECORDING_EXPORT_FAILED' : null,
    createdAt: '2026-10-03T12:10:00Z', startedAt: null, completedAt: null,
  };
}

export { sampleToken, sampleId };

/** Open the workspace with the 자동 라벨링 tab selected (layout prefs v2 in localStorage). */
export async function preferJobsTab(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('ds2l.layout', JSON.stringify({ v: 2, data: { theme: 'light', orient: 'stack', splitRatio: null, compareRatio: 0.5, inspectorHidden: false, sideTab: 'jobs' } }));
  });
}

/** Inspector tabs of the renewal (객체 / 자동 라벨링 / 기록). Job controls live in 자동 라벨링. */
export async function openTab(page: Page, name: '객체' | '자동 라벨링' | '기록') {
  await page.getByRole('tab', { name: new RegExp(`^${name}`) }).click();
}
