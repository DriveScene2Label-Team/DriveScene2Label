import { expect, test, type Page } from '@playwright/test';
import { DATASET, installMockApi, preferJobsTab } from './fixtures/mockApi';

/**
 * FU-03: a recording POST answered late must update only its own scene/pane/server context. Route fixtures only
 * (UI behaviour, not real exporter/data verification). Every scenario also checks that nothing is re-created.
 */
const ws = (sceneId: number, extra = '') => `/scenes/${sceneId}?dataset=${DATASET.id}${extra}`;
const DELAY = 1500;

async function openScene(page: Page, name: RegExp) {
  await page.getByRole('button', { name: '씬 목록으로' }).click();
  await page.getByRole('link', { name }).click();
}

test.beforeEach(async ({ page }) => { await preferJobsTab(page); });

test.describe('FU-03 지연 recording 응답의 문맥 고정', () => {
  // A scene/target without a recording requests one automatically (once). These cases check that late answers
  // still land only in their own scene, pane and server, and that nothing is requested twice.
  const posts = (log: { recordingPosts: Array<{ sceneId: number; body: unknown }> }, sceneId: number) =>
    log.recordingPosts.filter((p) => p.sceneId === sceneId);

  test('A에서 요청 후 B로 이동: B는 자기 recording만 받고, A로 돌아오면 원래 recording을 다시 요청하지 않고 연다', async ({ page }) => {
    const log = await installMockApi(page, { recordingPostDelayMs: DELAY });
    await page.goto(ws(21));
    await expect.poll(() => posts(log, 21).length).toBe(1);
    await openScene(page, /scene-0103 열기/);
    await expect(page.getByRole('heading', { name: 'scene-0103' })).toBeVisible();
    await expect.poll(() => posts(log, 22).length).toBe(1);
    await page.waitForTimeout(DELAY + 400);
    await expect(page.getByTestId('recording-badge')).toBeAttached();
    await openScene(page, /scene-0061 열기/);
    await expect(page.getByTestId('recording-badge')).toBeAttached();
    expect(log.recordingPosts).toEqual([{ sceneId: 21, body: {} }, { sceneId: 22, body: {} }]);
    expect(log.jobPosts).toHaveLength(0);
  });

  test('A→B→A 뒤 사용자가 다른 결과(작업 #41)를 고르면 늦은 GT-only 응답이 그 선택을 덮어쓰지 않는다', async ({ page }) => {
    const log = await installMockApi(page, { recordingPostDelayMs: DELAY + 1000, jobSequence: ['COMPLETED'] });
    await page.goto(ws(21));
    await expect.poll(() => posts(log, 21).length).toBe(1);
    await openScene(page, /scene-0103 열기/);
    await openScene(page, /scene-0061 열기/);
    await page.getByLabel('번호로 열기').fill('41');
    await page.getByRole('button', { name: '열기', exact: true }).click();
    await expect(page.locator('[data-status="COMPLETED"]')).toBeVisible();
    await expect.poll(() => posts(log, 21).length).toBe(2); // job #41's own recording is requested
    await page.waitForTimeout(DELAY + 1400); // the late GT-only answer arrives in between
    await expect(page.getByTestId('recording-badge')).toContainText('작업 #41 예측');
    await expect(page.getByTestId('recording-fallback')).toHaveCount(0);
    expect(posts(log, 21)).toEqual([{ sceneId: 21, body: {} }, { sceneId: 21, body: { jobId: 41 } }]);
    expect(log.jobPosts).toHaveLength(0);
  });

  test('비교 화면: 패널마다 자기 scene의 recording 하나만 요청하고 응답은 그 패널에 연결된다', async ({ page }) => {
    const log = await installMockApi(page, { recordingPostDelayMs: DELAY });
    await page.goto(`/compare?datasetA=${DATASET.id}&sceneA=21&datasetB=${DATASET.id}&sceneB=22`);
    // the last clicked pane becomes the active one (only it opens the 3D viewer)
    await page.locator('.pane[data-pane="B"]').getByRole('button', { name: '3D', exact: true }).click();
    await page.locator('.pane[data-pane="A"]').getByRole('button', { name: '3D', exact: true }).click();
    await expect.poll(() => posts(log, 21).length).toBe(1);
    await page.getByRole('radio', { name: /B\s*scene-0103/ }).click();
    await page.waitForTimeout(DELAY + 400);
    await expect(page.locator('.pane[data-pane="B"]').getByTestId('recording-badge')).toBeAttached();
    await page.getByRole('radio', { name: /A\s*scene-0061/ }).click();
    await expect(page.locator('.pane[data-pane="A"]').getByTestId('recording-badge')).toBeAttached();
    expect(log.recordingPosts.map((p) => p.sceneId).sort()).toEqual([21, 22]);
  });

  test('응답 전에 3D 패널이 언마운트돼도 결과는 보존되고 다시 열면 보인다', async ({ page }) => {
    const log = await installMockApi(page, { recordingPostDelayMs: DELAY });
    await page.goto(ws(21));
    await expect.poll(() => log.recordingPosts.length).toBe(1);
    await page.getByRole('group', { name: '보기 방식' }).getByRole('button', { name: '카메라', exact: true }).click(); // RecordingPanel unmounts
    await page.waitForTimeout(DELAY + 400);
    await page.getByRole('group', { name: '보기 방식' }).getByRole('button', { name: '카메라 + 3D', exact: true }).click();
    await expect(page.getByTestId('recording-badge')).toBeAttached();
    expect(log.recordingPosts).toHaveLength(1);
  });

  test('응답 전에 서버(DB instance)가 바뀌면 새 서버에는 그 서버의 recording을 따로 요청한다', async ({ page }) => {
    const log = await installMockApi(page, { recordingPostDelayMs: DELAY + 1000 });
    await page.goto(ws(21));
    await expect.poll(() => log.recordingPosts.length).toBe(1);
    log.instanceId = '22222222-2222-4222-8222-222222222222';
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await expect(page.getByText(/다른 서버\(DB\)에 연결됐어요/)).toBeVisible();
    // the old server's late answer is not used here; the new server is asked once for its own recording
    await expect.poll(() => log.recordingPosts.length).toBe(2);
    await page.waitForTimeout(DELAY + 1400);
    await expect(page.getByTestId('recording-badge')).toBeAttached();
    expect(log.recordingPosts).toHaveLength(2);
    expect(log.jobPosts).toHaveLength(0);
  });
});
