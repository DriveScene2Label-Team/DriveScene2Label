import { existsSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { DATASET, installMockApi } from './fixtures/mockApi';

/**
 * Rerun technical check: a real .rrd produced by the project exporter with rerun-sdk 0.38.1 (synthetic point cloud,
 * not nuScenes) is served through the recording content route and opened by @rerun-io/web-viewer 0.38.1.
 * Set DS2L_RRD to the file; the test is skipped when it is absent (generated files are not committed).
 * Regenerate with: ai-server/tests/recording_fixtures.py --out <dir>
 */
const RRD = process.env.DS2L_RRD ?? '';

test.describe('Rerun Web Viewer 0.38.1', () => {
  test.skip(!RRD || !existsSync(RRD), 'DS2L_RRD .rrd file not provided');

  test('loads the recording, follows the React timeline and survives resize/unmount', async ({ page }) => {
    test.setTimeout(150_000); // first WASM compile of the 51 MB viewer is slow in headless CI
    const errors: string[] = [];
    page.on('console', (m) => { if (process.env.DS2L_DEBUG) console.log(`[browser ${m.type()}] ${m.text().slice(0, 300)}`); });
    page.on('pageerror', (e) => errors.push(e.message));
    await installMockApi(page, { recording: 'ready', rrdPath: RRD });
    await page.goto(`/scenes/21?dataset=${DATASET.id}`);
    const host = page.getByTestId('rerun-host');
    await expect(host).toHaveAttribute('data-phase', 'ready', { timeout: 120_000 });
    await expect(host.locator('canvas')).toBeVisible();

    // React → viewer: moving the frame sets the "sample" timeline; the viewer reports the same time back.
    await page.getByRole('button', { name: '다음 프레임' }).click();
    await expect(host).toHaveAttribute('data-viewer-time', '1', { timeout: 10_000 });
    await page.getByRole('button', { name: '다음 프레임' }).click();
    await expect(host).toHaveAttribute('data-viewer-time', '2', { timeout: 10_000 });
    await expect(page.getByTestId('frame-readout-single')).toHaveText(/3\s*\/ 4/); // no ping-pong back

    // resize via the split handle
    const before = await host.boundingBox();
    const divider = page.getByRole('separator', { name: '카메라와 3D 영역 높이 비율' });
    await divider.focus();
    await page.keyboard.press('ArrowUp');
    await page.keyboard.press('ArrowUp');
    await expect.poll(async () => (await host.boundingBox())!.height).toBeGreaterThan(before!.height + 20);
    await page.waitForTimeout(1500);
    const canvas = await host.locator('canvas').boundingBox();
    const area = await host.boundingBox();
    expect(canvas!.height).toBeGreaterThan(area!.height * 0.9); // canvas follows the host after resize
    await page.screenshot({ path: 'test-results/screens/rerun-viewer.png' });

    // switching to six-camera view unmounts the viewer (stop() frees it) without page errors
    await page.getByRole('group', { name: '보기 방식' }).getByRole('button', { name: '카메라', exact: true }).click();
    await expect(page.getByTestId('rerun-host')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('maps a box picked in the viewer (entity + instance) to the same object in the inspector', async ({ page }) => {
    test.setTimeout(150_000);
    await installMockApi(page, { recording: 'ready', rrdPath: RRD });
    await page.goto(`/scenes/21?dataset=${DATASET.id}`);
    const host = page.getByTestId('rerun-host');
    await expect(host).toHaveAttribute('data-phase', 'ready', { timeout: 120_000 });
    await page.waitForTimeout(1500);
    const b = (await host.boundingBox())!;
    // The synthetic recording puts its boxes ahead of the ego; probe the view until a pick lands on one.
    let hit = false;
    for (let fy = 0.4; fy <= 0.7 && !hit; fy += 0.05) {
      for (let fx = 0.4; fx <= 0.95 && !hit; fx += 0.05) {
        await page.mouse.click(b.x + b.width * fx, b.y + b.height * fy);
        await page.waitForTimeout(100);
        hit = (await page.getByTestId('object-detail').count()) > 0;
      }
    }
    expect(hit).toBe(true);
    await expect(page.getByTestId('object-detail')).toContainText('GT');
    // the matching row in the object list is pressed (same key as the camera overlay)
    await expect(page.locator('.otable tbody tr.is-sel')).toHaveCount(1);
  });

  test('IT-09: a failed download of a READY recording is re-opened without creating anything', async ({ page }) => {
    test.setTimeout(150_000);
    const log = await installMockApi(page, { recording: 'ready', rrdPath: RRD, contentFailures: 1 });
    await page.goto(`/scenes/21?dataset=${DATASET.id}`);
    await expect(page.getByTestId('viewer-download-error')).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('viewer-download-error')).toContainText('HTTP 500');
    await page.getByTestId('reopen-recording').click();
    const host = page.getByTestId('rerun-host');
    await expect(host).toHaveAttribute('data-phase', 'ready', { timeout: 120_000 });
    await expect(host).toHaveAttribute('data-attempt', '1');
    expect(log.contentGets).toBe(2);
    expect(log.recordingPosts).toHaveLength(0);
    expect(log.jobPosts).toHaveLength(0);
  });
});
