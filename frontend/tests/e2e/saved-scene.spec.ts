import { expect, test } from '@playwright/test';
import { installMockApi, preferJobsTab } from './fixtures/mockApi';

test('fresh scene restores completed server result despite newer failure, and survives reload without inference', async ({ page }) => {
  await preferJobsTab(page);
  const log = await installMockApi(page, { jobSequence: ['COMPLETED'] });
  const completed = { jobId: 41, datasetId: 3, sceneToken: 'scene-tok-61', sceneId: 21, sceneName: 'scene-0061', classMode: 8, mappingName: '8class', status: 'COMPLETED', createdAt: '2026-10-03T12:00:00Z', startedAt: '2026-10-03T12:00:01Z', completedAt: '2026-10-03T12:02:31Z', errorMessage: null };
  await page.route('**/api/auto-label/jobs?sceneId=*', (route) => route.fulfill({ json: new URL(route.request().url()).searchParams.get('sceneId') === '21' ? [
    { ...completed, jobId: 42, status: 'FAILED', createdAt: '2026-10-04T12:00:00Z' }, completed,
  ] : [] }));
  await page.goto('/scenes/21?dataset=3&view=six');
  await expect(page.getByTestId('job-card-single')).toContainText('작업 #41');
  await expect(page.getByTestId('job-card-single')).toContainText('예측 박스 3개');
  await expect(page.locator('.job-row')).toHaveCount(2);
  await page.reload();
  await expect(page.getByTestId('job-card-single')).toContainText('예측 박스 3개');
  expect(log.jobPosts).toHaveLength(0);
  await page.goto('/scenes/22?dataset=3&view=six');
  await expect(page.getByTestId('job-card-single')).toHaveCount(0);
  expect(log.jobPosts).toHaveLength(0);
});
