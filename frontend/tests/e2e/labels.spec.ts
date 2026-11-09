import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { installMockApi } from './fixtures/mockApi';

const original = {
  coordinate_frame: 'WORLD',
  results: {
    sample: [{ sample_token: 'sample', detection_name: 'car', detection_score: 1, attribute_name: '',
      translation: [1, 2, 3], size: [2, 4, 1.5], rotation: [1, 0, 0, 0], velocity: [0, 0] }],
    empty: [],
  },
};

test('라벨 업로드 → UI 수정 → 저장 → 다시 열기 → 다운로드', async ({ page }) => {
  await installMockApi(page);
  let document: Record<string, unknown> | null = null;
  const revisions = [structuredClone(original)];
  await page.route('**/api/label-documents**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace('/api/label-documents', '');
    const method = route.request().method();
    const number = Number(url.searchParams.get('revision') ?? revisions.length - 1);
    const detail = () => ({ document, revision: number, data: revisions[number] });
    if (!path) return route.fulfill({ json: document ? [document] : [] });
    if (path === '/upload') {
      expect(route.request().postDataBuffer()?.includes(Buffer.from('labels.json'))).toBeTruthy();
      document = { id: 71, name: 'labels.json', datasetId: null, sourceJobId: null, sourceType: 'UPLOAD', headRevision: 0, version: 0, createdAt: '2026-11-09T00:00:00Z' };
      return route.fulfill({ status: 201, json: detail() });
    }
    if (path.endsWith('/revisions') && method === 'POST') {
      const body = route.request().postDataJSON();
      expect(body.expectedVersion).toBe(revisions.length - 1);
      revisions.push(body.data);
      document = { ...document, headRevision: revisions.length - 1, version: revisions.length - 1 };
      return route.fulfill({ status: 201, json: { document, revision: revisions.length - 1, data: body.data } });
    }
    if (path.endsWith('/revisions')) return route.fulfill({ json: revisions.map((_, i) => ({ number: i, note: '', createdAt: '' })).reverse() });
    if (path.endsWith('/download') || path.endsWith('/original')) return route.fulfill({
      contentType: 'application/json', headers: { 'Content-Disposition': 'attachment; filename="labels.json"' },
      body: JSON.stringify(path.endsWith('/original') ? original : revisions[number]),
    });
    return route.fulfill({ json: detail() });
  });
  await page.goto('/labels');
  await page.getByLabel('라벨 JSON 파일').setInputFiles({ name: 'labels.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(original)) });
  await page.getByRole('button', { name: '파일 업로드', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'labels.json' })).toBeVisible();
  await page.getByRole('button', { name: '박스 1 car' }).click();
  await page.getByLabel('라벨 클래스').selectOption('truck');
  await page.getByRole('button', { name: 'X +', exact: true }).click();
  await page.getByLabel('중심 위치 (m) X', { exact: true }).fill('9');
  await page.getByLabel('수정 메모').fill('truck 위치 수정');
  await page.getByRole('button', { name: '수정본 저장', exact: true }).click();
  await expect(page.getByText('수정본 v1을 서버에 저장했습니다.')).toBeVisible();
  expect(revisions[1]!.results.sample[0]!.detection_name).toBe('truck');
  expect(revisions[1]!.results.sample[0]!.translation[0]).toBe(9);
  expect(revisions[0]!.results.sample[0]!.detection_name).toBe('car');
  await page.reload();
  await page.getByLabel('편집 객체').selectOption('0');
  await expect(page.getByLabel('라벨 클래스')).toHaveValue('truck');
  await expect(page.getByLabel('중심 위치 (m) X', { exact: true })).toHaveValue('9');
  const pendingDownload = page.waitForEvent('download');
  await page.getByRole('link', { name: '저장본 v1 다운로드' }).click();
  const download = await pendingDownload;
  const saved = JSON.parse(await readFile((await download.path())!, 'utf8'));
  expect(saved.results.sample[0].detection_name).toBe('truck');
  expect(saved.results.empty).toEqual([]);
  await page.getByLabel('저장 버전').selectOption('0');
  await page.getByLabel('편집 객체').selectOption('0');
  await expect(page.getByLabel('라벨 클래스')).toHaveValue('car');
});

test('데이터셋 ZIP 업로드 후 씬과 원본 다운로드로 연결한다', async ({ page }) => {
  await installMockApi(page);
  await page.route('**/api/label-documents**', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/dataset-uploads', (route) => route.fulfill({ status: 201, json: { datasetId: 18, sceneCount: 2, version: 'v1.0-mini' } }));
  await page.goto('/labels');
  await page.getByLabel('원본 데이터 ZIP').setInputFiles({ name: 'data.zip', mimeType: 'application/zip', buffer: Buffer.from('fixture upload') });
  await page.getByRole('button', { name: '데이터셋 업로드', exact: true }).click();
  await expect(page.getByText('2개 씬을 등록했습니다.')).toBeVisible();
  await expect(page.getByRole('link', { name: '씬 열기 · 자동 라벨링' })).toHaveAttribute('href', '/scenes?dataset=18');
  await expect(page.getByRole('link', { name: '원본 ZIP 다운로드' })).toHaveAttribute('href', '/api/dataset-uploads/18/original');
});
