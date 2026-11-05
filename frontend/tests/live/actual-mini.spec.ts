import { expect, test, type Page } from '@playwright/test';

/**
 * Real-data SUCCESS checks (IT-11/IT-13 GT-only/IT-16) against a running Spring with real nuScenes. Unlike live.spec
 * (which accepts error/empty outcomes to check failure display), every check here requires the normal result:
 * origin NUSCENES, all expected cameras ready on several frames, GT matching the API, LIDAR_TOP present.
 * A synthetic/unknown dataset FAILS this suite instead of passing.
 *
 *   DS2L_ACTUAL=1 DS2L_API=http://127.0.0.1:8080 [DS2L_DATASET=<id>] [DS2L_SCENE=<id>] [DS2L_LIVE_ALLOW_POST=1] \
 *     npx playwright test -c playwright.live.config.ts tests/live/actual-mini.spec.ts
 */
const ACTUAL = !!process.env.DS2L_ACTUAL;
test.skip(!ACTUAL, 'DS2L_ACTUAL not set: real nuScenes success suite not requested');
test.setTimeout(180_000);

interface Ctx { datasetId: number; sceneId: number; sceneName: string; samples: Array<{ id: number; token: string }> }

async function context(page: Page): Promise<Ctx> {
  const req = page.request;
  const datasets = await (await req.get('/api/datasets')).json() as Array<{ id: number }>;
  const datasetId = Number(process.env.DS2L_DATASET ?? datasets[0]?.id);
  const status = await (await req.get(`/api/system/status?datasetId=${datasetId}`)).json();
  test.info().annotations.push({ type: 'dataset', description: JSON.stringify(status.dataset) });
  expect(status.dataset.origin, 'dataset must be recorded as NUSCENES (set NUSCENES_DATA_ORIGIN=NUSCENES at import)').toBe('NUSCENES');
  const scenes = await (await req.get(`/api/datasets/${datasetId}/scenes`)).json() as Array<{ id: number; name: string; nbrSamples: number }>;
  const scene = scenes.find((s) => String(s.id) === process.env.DS2L_SCENE) ?? scenes.find((s) => s.nbrSamples > 1);
  expect(scene, 'a scene with several samples').toBeTruthy();
  const samples = await (await req.get(`/api/scenes/${scene!.id}/samples?limit=500&offset=0`)).json() as Array<{ id: number; token: string }>;
  expect(samples.length).toBeGreaterThan(1);
  test.info().annotations.push({ type: 'scene', description: `${scene!.id} ${scene!.name} samples=${samples.length}` });
  return { datasetId, sceneId: scene!.id, sceneName: scene!.name, samples };
}

async function framesShowReadyCameras(page: Page, ctx: Ctx, index: number) {
  const s = ctx.samples[index]!;
  const detail = await (await page.request.get(`/api/samples/${s.id}`)).json() as { sensorFiles: Array<{ channel: string; modality: string; token: string }> };
  const cams = detail.sensorFiles.filter((f) => f.modality === 'camera');
  expect(cams.length, `sample ${s.token} camera files`).toBe(6);
  expect(detail.sensorFiles.some((f) => f.channel === 'LIDAR_TOP'), 'LIDAR_TOP keyframe').toBe(true);
  await expect(page.locator('.cam-tile .cam-media[data-state="ready"]')).toHaveCount(6, { timeout: 60_000 });
  const shown = await page.locator('.cam-media').evaluateAll((els) => els.map((e) => e.getAttribute('data-sample-data')));
  expect(new Set(shown)).toEqual(new Set(cams.map((c) => c.token))); // images are this sample's files, not another frame's
  const gt = await (await page.request.get(`/api/samples/${s.id}/annotations`)).json() as unknown[];
  await expect(page.locator('.otable tbody tr')).toHaveCount(gt.length);
  test.info().annotations.push({ type: `frame ${index + 1}`, description: `sample=${s.token} gt=${gt.length}` });
}

test('IT-11: real 6 cameras + GT across several frames (no missing/error accepted)', async ({ page }) => {
  const ctx = await context(page);
  await page.goto(`/scenes/${ctx.sceneId}?dataset=${ctx.datasetId}&view=six&sample=${ctx.samples[0]!.token}`);
  await expect(page.getByTestId('origin-badge')).toHaveAttribute('data-origin', 'NUSCENES');
  await framesShowReadyCameras(page, ctx, 0);
  await page.getByRole('button', { name: '다음 프레임' }).click();
  await expect(page.getByTestId('frame-readout-single')).toHaveText(new RegExp(`2\\s*/ ${ctx.samples.length}`));
  await framesShowReadyCameras(page, ctx, 1);
  const last = ctx.samples.length - 1;
  await page.goto(`/scenes/${ctx.sceneId}?dataset=${ctx.datasetId}&view=six&sample=${ctx.samples[last]!.token}`);
  await framesShowReadyCameras(page, ctx, last);
  await page.screenshot({ path: 'test-results/live/actual-six.png' });
});

test('IT-16: same real scene in A/B at different frames stays independent', async ({ page }) => {
  const ctx = await context(page);
  await page.goto(`/compare?datasetA=${ctx.datasetId}&sceneA=${ctx.sceneId}&datasetB=${ctx.datasetId}&sceneB=${ctx.sceneId}&sampleB=${ctx.samples[1]!.token}`);
  await expect(page.locator('.pane[data-pane="A"] .cam-media[data-state="ready"]')).toHaveCount(6, { timeout: 60_000 });
  await expect(page.locator('.pane[data-pane="B"] .cam-media[data-state="ready"]')).toHaveCount(6, { timeout: 60_000 });
  await page.getByRole('button', { name: '씬 A 다음 프레임' }).click();
  await expect(page.getByTestId('frame-readout-A')).toHaveText(/2\s*\//);
  await expect(page.getByTestId('frame-readout-B')).toHaveText(/2\s*\//);
  await page.getByRole('button', { name: '씬 A 다음 프레임' }).click();
  await expect(page.getByTestId('frame-readout-A')).toHaveText(/3\s*\//);
  await expect(page.getByTestId('frame-readout-B')).toHaveText(/2\s*\//);
});

test('IT-13 (GT-only part): real LiDAR recording READY with points, opened at the camera frame', async ({ page }) => {
  test.skip(!process.env.DS2L_LIVE_ALLOW_POST, 'set DS2L_LIVE_ALLOW_POST=1 to let this test create a GT-only recording');
  const ctx = await context(page);
  await page.goto(`/scenes/${ctx.sceneId}?dataset=${ctx.datasetId}&view=split`);
  const create = page.getByTestId('create-recording');
  if (await create.count()) await create.click();
  const host = page.getByTestId('rerun-host');
  await expect(host).toHaveAttribute('data-phase', 'ready', { timeout: 150_000 });
  const list = await (await page.request.get(`/api/scenes/${ctx.sceneId}/recordings`)).json() as Array<{ recordingId: number; status: string; jobId: number | null }>;
  const rec = list.find((r) => r.status === 'READY' && r.jobId == null)!;
  const detail = await (await page.request.get(`/api/recordings/${rec.recordingId}`)).json() as { samples: Array<{ lidarPoints: number; sampleToken: string }>; sdkVersion: string; sizeBytes: number };
  expect(detail.sdkVersion).toBe('0.38.1');
  expect(detail.samples.length).toBe(ctx.samples.length);
  expect(detail.samples.every((s) => s.lidarPoints > 0), 'every keyframe has LiDAR points').toBe(true);
  test.info().annotations.push({ type: 'recording', description: `${rec.recordingId} size=${detail.sizeBytes} points[0]=${detail.samples[0]!.lidarPoints}` });
  await page.getByRole('button', { name: '다음 프레임' }).click();
  await expect(host).toHaveAttribute('data-viewer-time', '1', { timeout: 20_000 });
  await page.screenshot({ path: 'test-results/live/actual-3d.png' });
});
