import { expect, test } from '@playwright/test';
import { DATASET, installMockApi, sampleToken } from './fixtures/mockApi';

const ws = (sceneId: number, extra = '') => `/scenes/${sceneId}?dataset=${DATASET.id}${extra}`;

test.describe('탐색 → 작업대 (QA-01/02)', () => {
  test('검색 결과의 대표 프레임으로 작업대를 열고 URL에 dataset·scene·sample을 담는다', async ({ page }) => {
    await installMockApi(page);
    await page.goto('/scenes');
    await expect(page).toHaveURL(new RegExp(`dataset=${DATASET.id}`)); // first listed dataset, not a hard-coded 1
    await expect(page.getByRole('heading', { name: /모든 씬\s*3/ })).toBeVisible();
    await page.getByLabel('장면 설명으로 검색').fill('rainy night road');
    await page.getByRole('button', { name: '검색', exact: true }).click();
    await expect(page.getByRole('heading', { name: /검색 결과\s*2/ })).toBeVisible();
    await expect(page.getByText('0.31', { exact: true })).toBeVisible();
    await expect(page.getByText(/%/)).toHaveCount(0); // score is not shown as a percentage
    await page.getByRole('link', { name: /scene-0103 열기/ }).click();
    await expect(page).toHaveURL(new RegExp(`/scenes/22\\?dataset=${DATASET.id}&sample=${sampleToken(22, 1)}`));
    await expect(page.getByTestId('frame-readout-single')).toHaveText(/2\s*\/ 3/);
  });

  test('빈 검색 결과와 검색 오류를 구분한다', async ({ page }) => {
    await installMockApi(page, { search: 'empty' });
    await page.goto(`/scenes?dataset=${DATASET.id}&q=snow`);
    await expect(page.getByText('“snow”에 맞는 씬이 없어요')).toBeVisible();
    await page.unroute('**/api/**');
    await installMockApi(page, { search: 'error' });
    await page.goto(`/scenes?dataset=${DATASET.id}&q=snow2`);
    await expect(page.getByText('검색하지 못했어요')).toBeVisible();
  });

  test('새로고침해도 씬·프레임이 복원되고 잘못된 sample은 첫 프레임으로 간다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21, `&sample=${sampleToken(21, 2)}`));
    await expect(page.getByTestId('frame-readout-single')).toHaveText(/3\s*\/ 4/);
    await page.reload();
    await expect(page.getByTestId('frame-readout-single')).toHaveText(/3\s*\/ 4/);
    await page.goto(ws(21, '&sample=not-a-real-token'));
    await expect(page.getByTestId('frame-readout-single')).toHaveText(/1\s*\/ 4/);
  });
});

test.describe('6카메라·프레임 이동', () => {
  test('6개 채널이 이름 기준으로 같은 sample을 보여 주고 함께 이동한다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21, '&view=six'));
    const tiles = page.locator('.cam-tile');
    await expect(tiles).toHaveCount(6);
    await expect(page.locator('.cam-tile[data-channel="CAM_FRONT_LEFT"]')).toHaveCSS('grid-area', /fl/);
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    const tokens = await page.locator('.cam-media').evaluateAll((els) => els.map((e) => e.getAttribute('data-sample-data')));
    expect(new Set(tokens.map((t) => t!.split('-')[1]))).toEqual(new Set([String(2100)]));
    await page.getByRole('button', { name: '다음 프레임' }).click();
    await expect(page.getByTestId('frame-readout-single')).toHaveText(/2\s*\/ 4/);
    await expect(page).toHaveURL(new RegExp(`sample=${sampleToken(21, 1)}`));
    const after = await page.locator('.cam-media').evaluateAll((els) => els.map((e) => e.getAttribute('data-sample-data')));
    expect(new Set(after.map((t) => t!.split('-')[1]))).toEqual(new Set(['2101']));
  });

  test('누락 카메라와 다운로드 실패는 해당 채널에만 표시된다 (QA-04)', async ({ page }) => {
    await installMockApi(page, { missingCameraSample: 2100, brokenImageSample: 2100 });
    await page.goto(ws(21, '&view=six'));
    await expect(page.locator('.cam-tile[data-channel="CAM_BACK"] [data-state="missing"]')).toBeVisible();
    await expect(page.locator('.cam-tile[data-channel="CAM_BACK_RIGHT"] [data-state="error"]')).toContainText('서버에 이미지 파일이 없어요');
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(4);
    await page.getByRole('button', { name: '다음 프레임' }).click();
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
  });

  test('늦게 도착한 이전 프레임 응답이 최신 프레임을 덮지 않는다 (QA-03)', async ({ page }) => {
    await installMockApi(page, { detailDelay: { 2101: 1500 } });
    await page.goto(ws(21, '&view=six'));
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    await page.getByRole('button', { name: '다음 프레임' }).click(); // frame 2 (slow)
    await page.getByRole('button', { name: '다음 프레임' }).click(); // frame 3
    await expect(page.getByTestId('frame-readout-single')).toHaveText(/3\s*\/ 4/);
    await page.waitForTimeout(1800); // let the slow frame-2 response arrive
    await expect(page.getByTestId('frame-readout-single')).toHaveText(/3\s*\/ 4/);
    const tokens = await page.locator('.cam-media').evaluateAll((els) => els.map((e) => e.getAttribute('data-sample-data')));
    expect(tokens.every((t) => t!.includes('2102'))).toBe(true);
  });

  test('확대 모달: Esc로 닫고 포커스가 돌아온다 (QA-13)', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21, '&view=six'));
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    const expand = page.getByRole('button', { name: '전방 CAM_FRONT 크게 보기' });
    await expand.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading')).toContainText('CAM_FRONT');
    await dialog.getByRole('button', { name: '후방', exact: true }).click();
    await expect(dialog.getByRole('heading')).toContainText('CAM_BACK');
    // Arrow keys inside the camera switcher (a group) move between buttons, as in the design; elsewhere they move frames.
    await dialog.getByRole('button', { name: '닫기 (Esc)' }).focus();
    await page.keyboard.press('ArrowRight');
    await expect(dialog.getByTestId('frame-readout-single')).toHaveText(/2\s*\/ 4/);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(expand).toBeFocused();
  });

  test('재생은 timestamp 간격으로 진행하고 끝에서 멈춘다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21, '&view=six'));
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    await page.getByRole('button', { name: '재생' }).click();
    await expect(page.getByTestId('frame-readout-single')).toHaveText(/4\s*\/ 4/, { timeout: 8000 });
    await expect(page.getByRole('button', { name: '재생' })).toBeVisible();
  });
});

test.describe('투영·레이어', () => {
  test('GT 박스가 이미지와 같은 좌표로 그려지고 분할 크기를 바꿔도 맞는다 (QA-05)', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21));
    const front = page.locator('.cam-tile[data-channel="CAM_FRONT"]');
    await expect(front.locator('g[data-source="GT"]').first()).toBeAttached();
    // Measured in one evaluation after layout settles (split changes re-flow the grid via ResizeObserver).
    const centred = () => expect(async () => {
      const img = await front.locator('img').boundingBox();
      // GT car is 15 m straight ahead → horizontally centred in CAM_FRONT.
      const box = await front.locator('g[data-box-key="GT:3:smp-21-0:21001"] path').last().boundingBox();
      expect(img && box).toBeTruthy();
      const dx = Math.abs(box!.x + box!.width / 2 - (img!.x + img!.width / 2));
      expect(dx).toBeLessThan(img!.width * 0.03);
    }).toPass({ timeout: 3000 });
    await centred();
    const divider = page.getByRole('separator', { name: '카메라와 3D 영역 높이 비율' });
    await divider.focus();
    await page.keyboard.press('ArrowUp');
    await page.keyboard.press('ArrowUp');
    await centred();
    // layer toggle hides GT
    await page.getByRole('button', { name: 'GT', exact: true }).click();
    await expect(front.locator('g[data-source="GT"]')).toHaveCount(0);
  });

  test('객체 목록에서 원본 category·비교 분류·미매핑을 구분한다 (QA-17)', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21));
    await expect(page.locator('.cam-media[data-state="ready"]').first()).toBeVisible({ timeout: 15_000 });
    const table = page.getByRole('table', { name: /프레임 1의 객체/ });
    await expect(table.locator('tbody tr')).toHaveCount(3);
    // GT shows the 8class comparison class; the original category stays visible in the details.
    await table.getByRole('row', { name: /^GT car,/ }).click();
    await expect(page.getByTestId('object-detail').locator('.ed-label')).toHaveText('car');
    await expect(page.getByTestId('object-detail')).toContainText('vehicle.car');
    await table.getByRole('row', { name: /movable_object\.barrier/ }).click();
    await expect(page.getByTestId('object-detail')).toContainText('비교 분류 없음');
    await table.getByRole('row', { name: /클래스 정보 없음/ }).click();
    await expect(page.getByTestId('object-detail')).toContainText('클래스 정보 없음');
  });
});
