import { expect, test, type Page } from '@playwright/test';
import { DATASET, installMockApi, sampleToken } from './fixtures/mockApi';

/** Layout checks run on every viewport project (1440/1280/1024/768/375). Screenshots go to test-results/screens (git-ignored). */
async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

async function shot(page: Page, name: string) {
  const project = test.info().project.name;
  await page.screenshot({ path: `test-results/screens/${project}-${name}.png`, fullPage: false });
}

test.describe('@layout 화면 크기별 배치', () => {
  test('@layout 탐색 화면', async ({ page }) => {
    await installMockApi(page);
    await page.goto(`/scenes?dataset=${DATASET.id}`);
    await expect(page.locator('.card-hit')).toHaveCount(3);
    await expect(page.locator('.card-thumb img').first()).toBeVisible();
    await noHorizontalScroll(page);
    await shot(page, 'search');
  });

  test('@layout 작업대 카메라 + LiDAR', async ({ page }) => {
    await installMockApi(page);
    await page.goto(`/scenes/21?dataset=${DATASET.id}&sample=${sampleToken(21, 1)}`);
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    await expect(page.getByRole('button', { name: '다음 프레임' }).first()).toBeVisible();
    await expect(page.getByRole('tab', { name: /자동 라벨링/ })).toBeAttached();
    await noHorizontalScroll(page);
    await shot(page, 'workspace-split');
  });

  test('@layout 작업대 6개 카메라와 패널 접기', async ({ page }) => {
    await installMockApi(page);
    await page.goto(`/scenes/21?dataset=${DATASET.id}&view=six`);
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    await noHorizontalScroll(page);
    await shot(page, 'workspace-six');
    const toggle = page.getByRole('button', { name: '인스펙터 보기' });
    await expect(toggle).toHaveAttribute('aria-pressed', 'true');
    const before = (await page.locator('.cam-tile').first().boundingBox())!.width;
    await toggle.click();
    await expect(page.locator('#side')).toBeHidden();
    // More room never makes the cameras noticeably smaller (the design prefers 3×2 within 3 % of the 2×3 size).
    await expect.poll(async () => (await page.locator('.cam-tile').first().boundingBox())!.width).toBeGreaterThanOrEqual(before * 0.96);
    await noHorizontalScroll(page);
    await shot(page, 'workspace-six-collapsed');
    await toggle.click();
    await expect(page.locator('#side')).toBeVisible();
  });

  test('@layout 두 씬 비교', async ({ page }) => {
    await installMockApi(page);
    await page.goto(`/compare?datasetA=${DATASET.id}&sceneA=21&datasetB=${DATASET.id}&sceneB=22`);
    await expect(page.locator('.pane[data-pane="A"] .cam-media[data-state="ready"]')).toHaveCount(6);
    await expect(page.locator('.pane[data-pane="B"] .cam-media[data-state="ready"]')).toHaveCount(6);
    await noHorizontalScroll(page);
    await shot(page, 'compare');
  });
});
