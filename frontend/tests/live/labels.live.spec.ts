import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('실제 서버에 업로드하고 UI 수정본을 저장·재조회·다운로드한다', async ({ page, request }) => {
  test.skip(process.env.DS2L_LIVE_ALLOW_LABEL_UPLOAD !== '1', 'Dedicated test DB and explicit upload opt-in required');
  const original = JSON.stringify({ coordinate_frame: 'WORLD', results: { sample: [{
    sample_token: 'sample', detection_name: 'car', detection_score: 1, attribute_name: '',
    translation: [1, 2, 3], size: [2, 4, 1.5], rotation: [1, 0, 0, 0], velocity: [0, 0],
  }], empty: [] } });
  await page.goto('/labels');
  const filename = 'live-labels-' + Date.now() + '.json';
  await page.getByLabel('라벨 JSON 파일').setInputFiles({ name: filename, mimeType: 'application/json', buffer: Buffer.from(original) });
  await page.getByRole('button', { name: '파일 업로드', exact: true }).click();
  await expect(page.getByRole('heading', { name: filename })).toBeVisible();
  await page.getByLabel('편집 객체').selectOption('0');
  await page.getByLabel('라벨 클래스').selectOption('truck');
  await page.getByRole('button', { name: 'X +', exact: true }).click();
  await page.getByRole('button', { name: '회전 +5°', exact: true }).click();
  await page.getByLabel('수정 메모').fill('실제 API UI 저장 검증');
  await page.getByRole('button', { name: '수정본 저장', exact: true }).click();
  await expect(page.getByText('수정본 v1을 서버에 저장했습니다.')).toBeVisible();
  const id = new URL(page.url()).searchParams.get('id');
  await page.reload();
  await page.getByLabel('편집 객체').selectOption('0');
  await expect(page.getByLabel('라벨 클래스')).toHaveValue('truck');
  await expect(page.getByLabel('중심 위치 (m) X', { exact: true })).toHaveValue('1.1');
  const pending = page.waitForEvent('download');
  await page.getByRole('link', { name: '저장본 v1 다운로드' }).click();
  const download = await pending;
  const saved = JSON.parse(await readFile((await download.path())!, 'utf8'));
  expect(saved.results.sample[0].detection_name).toBe('truck');
  expect(saved.results.sample[0].translation[0]).toBe(1.1);
  expect(saved.results.empty).toEqual([]);
  const untouched = await request.get('/api/label-documents/' + id + '/original');
  expect(await untouched.text()).toBe(original);
  if (process.env.DS2L_LABEL_SCREENSHOT) await page.screenshot({ path: process.env.DS2L_LABEL_SCREENSHOT, fullPage: true });
});
