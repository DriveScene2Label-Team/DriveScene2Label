import { expect, test, type Locator } from '@playwright/test';
import { DATASET, installMockApi, openTab, preferJobsTab, sampleToken } from './fixtures/mockApi';

/** Keyboard-driven slider move (Home, then →×n): exercises the real input path. */
async function setSlider(slider: Locator, n: number) {
  await slider.focus();
  await slider.press('Home');
  for (let i = 0; i < n; i++) await slider.press('ArrowRight');
}

const ws = (sceneId: number, extra = '') => `/scenes/${sceneId}?dataset=${DATASET.id}${extra}`;

test.beforeEach(async ({ page }) => { await preferJobsTab(page); });

test.describe('VESPA 작업', () => {
  test('응답 유실 후 같은 Idempotency-Key로 재시도해 같은 job을 받고, 완료 결과를 이미지에 그린다 (QA-06)', async ({ page }) => {
    const log = await installMockApi(page, { postAborts: 1, jobSequence: ['PENDING', 'RUNNING', 'COMPLETED'] });
    await page.goto(ws(21, '&view=six'));
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    await page.getByLabel('클래스', { exact: true }).selectOption('3');
    await page.getByRole('button', { name: '라벨 생성하기' }).click();
    await expect(page.getByTestId('job-card-single')).toContainText('작업 #41');
    expect(log.jobPosts).toHaveLength(2);
    expect(log.jobPosts[0]!.key).toBeTruthy();
    expect(log.jobPosts[1]!.key).toBe(log.jobPosts[0]!.key);
    expect(log.jobPosts[0]!.body).toEqual({ sceneToken: 'scene-tok-61', datasetId: DATASET.id, classMode: 3 });
    await expect(page.locator('[data-status="COMPLETED"]')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/예측 박스 3개/)).toBeVisible();
    await expect(page.locator('.cam-tile[data-channel="CAM_FRONT"] g[data-source="VESPA"]')).toHaveCount(1);
    await expect(page).toHaveURL(/job=41/);
    // elapsed time stops at completedAt (2m 30s after startedAt)
    await expect(page.getByTestId('job-card-single')).toContainText('2분 30초');
    // last frame of the job has no boxes: a normal empty state, not an error
    await setSlider(page.getByRole('slider', { name: '프레임' }), 3);
    await openTab(page, '객체');
    await page.getByRole('group', { name: '구분' }).getByRole('button', { name: /예측/ }).click();
    await expect(page.getByText('이 프레임에 해당하는 객체가 없어요.')).toBeVisible();
    await expect(page.locator('.obj-warn')).toHaveCount(0);
    // a new user run uses a new key
    expect(new Set(log.jobPosts.map((p) => p.key)).size).toBe(1);
  });

  test('상태 GET 실패는 작업 실패로 표시하지 않고 복구된다 (QA-07)', async ({ page }) => {
    await installMockApi(page, { jobSequence: ['RUNNING', 503, 503, 'RUNNING', 'COMPLETED'] });
    await page.goto(ws(21, '&job=41'));
    await expect(page.getByText('연결을 확인할 수 없어요')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-status="FAILED"]')).toHaveCount(0);
    await expect(page.locator('[data-status="COMPLETED"]')).toBeVisible({ timeout: 20000 });
  });

  test('완료 결과 GET 실패 시 결과만 다시 읽고 새 job을 만들지 않는다 (QA-15)', async ({ page }) => {
    const log = await installMockApi(page, { jobSequence: ['COMPLETED'], resultsFailures: 1 });
    await page.goto(ws(21, '&job=41'));
    await expect(page.getByTestId('job-card-single').getByText('결과를 불러오지 못했어요')).toBeVisible();
    await page.getByRole('button', { name: '결과 다시 불러오기' }).first().click();
    await expect(page.getByText(/예측 박스 3개/)).toBeVisible();
    expect(log.jobPosts).toHaveLength(0);
    expect(log.resultGets).toBe(2);
  });

  test('실패한 작업은 이유를 보여 주고 새 작업은 새 key로 만든다 (FR-23)', async ({ page }) => {
    const log = await installMockApi(page, { jobSequence: ['FAILED'] });
    await page.goto(ws(21, '&job=41'));
    await expect(page.getByText('AI request failed or timed out')).toBeVisible();
    await page.getByRole('button', { name: '다시 시도' }).click();
    await expect.poll(() => log.jobPosts.length).toBe(1);
    expect(log.jobPosts[0]!.key).toMatch(/^ds2l-/);
  });

  test('다른 씬의 job 링크는 결과를 연결하지 않는다 (QA-14)', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21, '&job=77'));
    await expect(page.getByText('이 씬의 작업이 아니에요')).toBeVisible();
    await expect(page.locator('g[data-source="VESPA"]')).toHaveCount(0);
  });

  test('없는 job 링크는 안내 후 연결을 해제한다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21, '&job=999'));
    await expect(page.getByText('작업을 찾을 수 없어요')).toBeVisible();
    await page.getByRole('button', { name: '연결 해제' }).click();
    await expect(page).not.toHaveURL(/job=999/);
  });

  test('receipt로 새로고침 후 작업을 복원한다 (FR-24)', async ({ page }) => {
    await installMockApi(page, { jobSequence: ['RUNNING'] });
    await page.goto(ws(21));
    await page.getByRole('button', { name: '라벨 생성하기' }).click();
    await expect(page.getByTestId('job-card-single')).toContainText('작업 #41');
    await page.goto(ws(21)); // no job in URL
    await expect(page.getByTestId('job-card-single')).toContainText('작업 #41');
    await expect(page.locator('[data-status="RUNNING"]')).toBeVisible();
  });
});

test.describe('두 씬 비교', () => {
  test('같은 씬을 A/B에 열어도 프레임·레이어가 독립이다 (QA-09)', async ({ page }) => {
    await installMockApi(page);
    await page.goto(`/compare?datasetA=${DATASET.id}&sceneA=21&datasetB=${DATASET.id}&sceneB=21&sampleB=${sampleToken(21, 2)}`);
    await expect(page.getByTestId('frame-readout-A')).toHaveText(/1\s*\/ 4/);
    await expect(page.getByTestId('frame-readout-B')).toHaveText(/3\s*\/ 4/);
    await page.getByRole('button', { name: '씬 A 다음 프레임' }).click();
    await expect(page.getByTestId('frame-readout-A')).toHaveText(/2\s*\/ 4/);
    await expect(page.getByTestId('frame-readout-B')).toHaveText(/3\s*\/ 4/);
    await page.getByRole('toolbar', { name: '씬 A 표시' }).getByRole('button', { name: 'GT', exact: true }).click();
    await expect(page.locator('.pane[data-pane="A"] g[data-source="GT"]')).toHaveCount(0);
    await expect(page.locator('.pane[data-pane="B"] g[data-source="GT"]').first()).toBeAttached();
    // active pane drives the inspector target
    await page.getByRole('radio', { name: /B\s*scene-0061/ }).click();
    await expect(page.getByRole('button', { name: '씬 B 라벨 생성하기' })).toBeVisible();
    await expect(page).toHaveURL(/active=B/);
  });

  test('상대 위치 동기화는 timestamp 비율로 다른 씬을 옮기고 꺼지면 독립이다 (QA-10)', async ({ page }) => {
    await installMockApi(page);
    await page.goto(`/compare?datasetA=${DATASET.id}&sceneA=21&datasetB=${DATASET.id}&sceneB=22`);
    await expect(page.getByTestId('frame-readout-B')).toHaveText(/1\s*\/ 3/);
    await page.getByText('재생 위치 맞추기', { exact: true }).click();
    await setSlider(page.locator('.pane[data-pane="A"]').getByRole('slider'), 3); // A at 100 %
    await expect(page.getByTestId('frame-readout-B')).toHaveText(/3\s*\/ 3/);
    await setSlider(page.locator('.pane[data-pane="A"]').getByRole('slider'), 1); // A at 1/3 → B nearest to 1/3 of its span
    await expect(page.getByTestId('frame-readout-B')).toHaveText(/2\s*\/ 3/);
    await page.getByText('재생 위치 맞추기', { exact: true }).click();
    await setSlider(page.locator('.pane[data-pane="A"]').getByRole('slider'), 0);
    await expect(page.getByTestId('frame-readout-B')).toHaveText(/2\s*\/ 3/);
  });

  test('단일 프레임 씬과 동기화해도 오류가 없다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(`/compare?datasetA=${DATASET.id}&sceneA=21&datasetB=${DATASET.id}&sceneB=23&sync=relative`);
    await setSlider(page.locator('.pane[data-pane="A"]').getByRole('slider'), 2);
    await expect(page.getByTestId('frame-readout-B')).toHaveText(/1\s*\/ 1/);
  });
});

test.describe('3D recording', () => {
  test('recording 실패는 recording만 다시 요청하고 VESPA를 다시 실행하지 않는다 (QA-16)', async ({ page }) => {
    const log = await installMockApi(page, { recording: 'fail-then-ready' });
    await page.goto(ws(21));
    // no recording yet: the GT-only one is requested without a click (and fails once here)
    await expect(page.getByText('3D recording을 만들지 못했어요')).toBeVisible();
    expect(log.recordingPosts).toEqual([{ sceneId: 21, body: {} }]);
    await expect(page.getByText(/RECORDING_EXPORT_FAILED/)).toBeVisible();
    await page.getByRole('button', { name: 'recording 다시 만들기' }).click();
    await expect(page.getByTestId('recording-badge')).toBeAttached();
    expect(log.recordingPosts).toHaveLength(2);
    expect(log.jobPosts).toHaveLength(0);
    // camera UI stays usable while the 3D area changes state
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
  });
});
