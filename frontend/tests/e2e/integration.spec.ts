import { expect, test } from '@playwright/test';
import { DATASET, installMockApi, preferJobsTab } from './fixtures/mockApi';

/** Integration-plan scenarios on route fixtures (UI behaviour only; not real-data or real-AI verification). */
const ws = (sceneId: number, extra = '') => `/scenes/${sceneId}?dataset=${DATASET.id}${extra}`;

test.beforeEach(async ({ page }) => { await preferJobsTab(page); });

test.describe('IT-02/03/04 준비 상태·출처', () => {
  test('VESPA 설정만 확인된 상태는 실행을 막고, 환경 확인(읽기 전용) 후에만 실행할 수 있다', async ({ page }) => {
    const log = await installMockApi(page, { status: { vespa: 'configured-then-ready' } });
    await page.goto(ws(21));
    const run = page.getByTestId('run-job-single');
    await expect(page.getByTestId('vespa-readiness-single')).toHaveAttribute('data-reason', 'EXECUTOR_NOT_CHECKED');
    await expect(run).toBeDisabled();
    await page.getByRole('button', { name: '지금 확인' }).click();
    await expect(run).toBeEnabled();
    expect(log.statusCalls.some((c) => c.refresh)).toBe(true);
    expect(log.jobPosts).toHaveLength(0); // checking the environment never creates work
    await expect(page.getByTestId('vespa-ready-single')).toContainText('실제 추론 성공을 보장하는 확인은 아니에요');
  });

  test('합성 데이터는 목록·작업대에 테스트 배지를 보이고 실제 VESPA 실행을 막는다 (센서 탐색은 유지)', async ({ page }) => {
    const log = await installMockApi(page, { status: { origin: 'SYNTHETIC' } });
    await page.goto(`/scenes?dataset=${DATASET.id}`);
    await expect(page.getByTestId('origin-badge')).toHaveText(/테스트 데이터/);
    await page.goto(ws(21, '&view=six'));
    await expect(page.getByTestId('origin-badge')).toHaveAttribute('data-origin', 'SYNTHETIC');
    await expect(page.getByTestId('vespa-readiness-single')).toHaveAttribute('data-reason', 'SYNTHETIC_DATASET');
    await expect(page.getByRole('button', { name: '지금 확인' })).toHaveCount(0);
    await expect(page.getByTestId('run-job-single')).toBeDisabled();
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    expect(log.jobPosts).toHaveLength(0);
  });

  test('준비 상태 API가 없는 이전 서버는 실행을 막고 출처 정보 없음으로 표시한다', async ({ page }) => {
    await installMockApi(page, { status: { missing: true } });
    await page.goto(ws(21));
    await expect(page.getByTestId('origin-badge').or(page.getByText('출처 정보 없음'))).toBeVisible();
    await expect(page.getByTestId('vespa-readiness-single')).toHaveAttribute('data-reason', 'STATUS_API_UNSUPPORTED');
    await expect(page.getByTestId('run-job-single')).toBeDisabled();
    await expect(page.locator('.cam-media[data-state="ready"]').first()).toBeVisible();
  });

  test('임베딩이 없으면 검색을 막고 이유를 보이며 씬 목록은 유지한다', async ({ page }) => {
    let searchCalls = 0;
    page.on('request', (r) => { if (r.url().includes('/api/search/scenes')) searchCalls++; });
    await installMockApi(page, { status: { search: 'UNAVAILABLE' } });
    await page.goto(`/scenes?dataset=${DATASET.id}`);
    await expect(page.getByTestId('search-readiness')).toHaveAttribute('data-reason', 'EMBEDDINGS_NOT_READY');
    await page.getByLabel('장면 설명으로 검색').fill('rain');
    await expect(page.getByRole('button', { name: '검색', exact: true })).toBeDisabled();
    await expect(page.locator('.card-hit')).toHaveCount(3);
    await page.goto(`/scenes?dataset=${DATASET.id}&q=rain`);
    await expect(page.getByText('이 데이터셋에서는 지금 검색할 수 없어요')).toBeVisible();
    expect(searchCalls).toBe(0);
  });

  test('다른 서버(instance)로 바뀌면 이전 서버의 작업 기록을 연결하지 않는다', async ({ page }) => {
    await installMockApi(page, { status: { instanceId: 'aaaaaaaa-0000-4000-8000-000000000001' }, jobSequence: ['RUNNING'] });
    await page.goto(ws(21));
    await page.getByTestId('run-job-single').click();
    await expect(page.getByTestId('job-card-single')).toContainText('작업 #41');
    await page.unroute('**/api/**');
    await installMockApi(page, { status: { instanceId: 'bbbbbbbb-0000-4000-8000-000000000002' }, jobSequence: ['RUNNING'] });
    await page.goto(ws(21));
    await expect(page.getByText('아직 실행한 작업이 없어요.')).toBeVisible();
    await expect(page.getByTestId('job-card-single')).toHaveCount(0);
  });
});

test.describe('IT-05 오류 원인', () => {
  test('upstream 404 실패는 timeout이 아니라 미지원으로 안내하고, 실행 환경이 없으면 재실행을 막는다', async ({ page }) => {
    await installMockApi(page, { jobSequence: ['FAILED'], failedErrorCode: 'AI_ENDPOINT_UNSUPPORTED', status: { vespa: 'UNAVAILABLE' } });
    await page.goto(ws(21, '&job=41'));
    const card = page.getByTestId('job-card-single');
    await expect(card.locator('[data-error-code="AI_ENDPOINT_UNSUPPORTED"]')).toBeVisible();
    await expect(card).toContainText('연결된 AI 서버가 이 기능을 제공하지 않아요');
    await expect(card).not.toContainText('timed out');
    await expect(card.getByRole('button', { name: /다시 시도/ })).toBeDisabled();
  });
});

test.describe('IT-06/07 요청 snapshot', () => {
  test('응답 전에 다른 씬으로 이동하면 새 씬에 작업을 연결하지 않고 원래 씬 이력에만 남긴다', async ({ page }) => {
    const log = await installMockApi(page, { postDelayMs: 1500, jobSequence: ['RUNNING'] });
    await page.goto(ws(21));
    await page.getByTestId('run-job-single').click();
    await page.getByRole('button', { name: '씬 목록으로' }).click(); // client-side navigation keeps the request alive
    await page.getByRole('link', { name: /scene-0103 열기/ }).click();
    await expect(page.getByRole('heading', { name: 'scene-0103' })).toBeVisible();
    await expect.poll(() => log.jobPosts.length).toBe(1);
    await page.waitForTimeout(1800); // answer arrives while scene-0103 is open
    await expect(page.getByText('아직 실행한 작업이 없어요.')).toBeVisible();
    const receipts = await page.evaluate(() => JSON.parse(localStorage.getItem('ds2l.jobReceipts.v2') ?? '{"data":[]}').data);
    expect(receipts).toHaveLength(1);
    expect(receipts[0]).toMatchObject({ jobId: 41, sceneToken: 'scene-tok-61', sceneId: 21, paneId: 'single', classMode: 8 });
    // back on the original scene its history shows the job
    await page.getByRole('button', { name: '씬 목록으로' }).click();
    await page.getByRole('link', { name: /scene-0061 열기/ }).click();
    await expect(page.getByTestId('job-card-single')).toContainText('작업 #41');
  });

  test('A→B→A로 돌아와 사용자가 고른 작업을 늦은 응답이 덮어쓰지 않는다', async ({ page }) => {
    await installMockApi(page, { postDelayMs: 2000, jobSequence: ['RUNNING'] });
    await page.goto(ws(21));
    await page.getByTestId('run-job-single').click();
    await page.getByRole('button', { name: '씬 목록으로' }).click();
    await page.getByRole('link', { name: /scene-0103 열기/ }).click();
    await page.getByRole('button', { name: '씬 목록으로' }).click();
    await page.getByRole('link', { name: /scene-0061 열기/ }).click();
    await page.getByLabel('번호로 열기').fill('77');
    await page.getByRole('button', { name: '열기', exact: true }).click();
    await expect(page.getByTestId('job-card-single')).toContainText('작업 #77');
    await page.waitForTimeout(2300);
    await expect(page.getByTestId('job-card-single')).toContainText('작업 #77');
  });

  test('비교 화면에서 작업 대상을 바꿔도 응답은 요청한 패널에만 연결된다', async ({ page }) => {
    await installMockApi(page, { postDelayMs: 1500, jobSequence: ['RUNNING'] });
    await page.goto(`/compare?datasetA=${DATASET.id}&sceneA=21&datasetB=${DATASET.id}&sceneB=22`);
    await page.getByTestId('run-job-A').click();
    await page.getByRole('radio', { name: /B\s*scene-0103/ }).click();
    await page.waitForTimeout(1800);
    await expect(page.getByText('아직 실행한 작업이 없어요.')).toBeVisible(); // pane B
    await page.getByRole('radio', { name: /A\s*scene-0061/ }).click();
    await expect(page.getByTestId('job-card-A')).toContainText('작업 #41');
  });

  test('응답 유실 후 "같은 요청 다시 보내기"는 같은 key를 쓰고, 새 실행은 새 key를 쓴다', async ({ page }) => {
    const log = await installMockApi(page, { postAborts: 3, jobSequence: ['FAILED'], failedErrorCode: 'VESPA_EXECUTION_FAILED' });
    await page.goto(ws(21));
    await page.getByTestId('run-job-single').click();
    await expect(page.getByText('요청 결과를 확인하지 못했어요')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: '같은 요청 다시 보내기' }).click();
    await expect(page.getByTestId('job-card-single')).toContainText('작업 #41');
    const keys = new Set(log.jobPosts.map((p) => p.key));
    expect(log.jobPosts.length).toBe(4);
    expect(keys.size).toBe(1);
    await page.getByRole('button', { name: '다시 시도' }).click();
    await expect.poll(() => log.jobPosts.length).toBe(5);
    expect(log.jobPosts[4]!.key).not.toBe(log.jobPosts[0]!.key);
  });
});

test.describe('IT-10 라벨 토글 적용 범위', () => {
  test('GT/예측 토글은 카메라 라벨 범위로 표시되고 패널별로 독립이다', async ({ page }) => {
    await installMockApi(page, { recording: 'ready' });
    await page.goto(`/compare?datasetA=${DATASET.id}&sceneA=21&datasetB=${DATASET.id}&sceneB=21`);
    // The display bar applies to the work-target pane (tagged A/B); each pane keeps its own layers.
    const hud = page.getByRole('toolbar', { name: '씬 A 표시' });
    await expect(page.locator('.pane[data-pane="B"] g[data-source="GT"]').first()).toBeAttached();
    await hud.getByRole('button', { name: 'GT', exact: true }).click();
    await expect(page.locator('.pane[data-pane="A"] g[data-source="GT"]')).toHaveCount(0);
    await expect(page.locator('.pane[data-pane="B"] g[data-source="GT"]').first()).toBeAttached();
    await page.getByRole('radio', { name: /B\s*scene-0061/ }).click();
    const hudB = page.getByRole('toolbar', { name: '씬 B 표시' });
    await expect(hudB.getByRole('button', { name: 'GT', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await page.goto(ws(21));
    await expect(page.getByTestId('recording-badge')).toContainText('표시는 위 버튼을 따라요');
  });
});

test.describe('FU-01 상태 조회 실패·만료 뒤 이전 READY 미사용', () => {
  for (const failure of [500, 'abort'] as const) {
    test(`READY → 상태 API ${failure === 500 ? 'HTTP 500' : '연결 실패'}: 새 실행 차단, 기존 결과·작업 조회 유지, 복구 시 다시 허용`, async ({ page }) => {
      const log = await installMockApi(page, { jobSequence: ['COMPLETED'] });
      await page.goto(ws(21, '&job=41&view=six'));
      const run = page.getByTestId('run-job-single');
      await expect(run).toBeEnabled();
      await expect(page.locator('.cam-tile[data-channel="CAM_FRONT"] g[data-source="VESPA"]')).toHaveCount(1);
      log.statusFailure = failure;
      await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange'))); // triggers a status re-read
      const box = page.getByTestId('vespa-readiness-single');
      await expect(box).toHaveAttribute('data-reason', 'STATUS_UNREACHABLE');
      await expect(run).toBeDisabled();
      await expect(page.getByTestId('vespa-last-known-single')).toContainText('준비됨');
      // previous completed result and job status stay usable
      await expect(page.locator('[data-status="COMPLETED"]')).toBeVisible();
      await expect(page.locator('.cam-tile[data-channel="CAM_FRONT"] g[data-source="VESPA"]')).toHaveCount(1);
      // a light re-check that still fails keeps it blocked (no heavy refresh=true is sent for a status problem)
      const refreshesBefore = log.statusCalls.filter((c) => c.refresh).length;
      await page.getByRole('button', { name: '지금 확인' }).click();
      await expect(run).toBeDisabled();
      expect(log.statusCalls.filter((c) => c.refresh).length).toBe(refreshesBefore);
      log.statusFailure = null;
      await page.getByRole('button', { name: '지금 확인' }).click();
      await expect(run).toBeEnabled();
      expect(log.jobPosts).toHaveLength(0);
      expect(log.recordingPosts).toHaveLength(0);
    });
  }

  test('수동 환경 확인과 뒤따른 GET이 모두 실패해도 이전 READY로 돌아가지 않는다', async ({ page }) => {
    const log = await installMockApi(page, { status: { vespa: 'CONFIGURED' } });
    await page.goto(ws(21));
    const run = page.getByTestId('run-job-single');
    await expect(run).toBeDisabled();
    log.statusFailure = 500;
    await page.getByRole('button', { name: '지금 확인' }).click();
    await expect(page.getByTestId('vespa-readiness-single')).toHaveAttribute('data-reason', 'STATUS_UNREACHABLE');
    await expect(run).toBeDisabled();
    expect(log.jobPosts).toHaveLength(0);
  });
});

test.describe('FU-02 구버전 이력의 DB 귀속 방지', () => {
  const INSTANCE = '11111111-1111-4111-8111-111111111111';
  // A request made against ANOTHER database: same datasetId/sceneToken/jobId as this server's job 41, different request.
  const v1 = { jobId: 41, datasetId: DATASET.id, sceneId: 21, sceneToken: 'scene-tok-61', sceneName: 'scene-0061', classMode: 8, idempotencyKey: 'old-db-request-key', requestedAt: 1_700_000_000_000 };

  test('v1 기록은 서버 job의 dataset/scene이 같아도 이 서버 작업으로 연결하지 않고 미확인으로 보존한다', async ({ page }) => {
    await page.addInitScript((r) => { localStorage.setItem('ds2l.jobReceipts', JSON.stringify({ v: 1, data: [r] })); }, v1);
    await installMockApi(page, { jobSequence: ['RUNNING'] });
    await page.goto(ws(21));
    await expect(page.getByText('아직 실행한 작업이 없어요.')).toBeVisible();
    await expect(page.getByTestId('legacy-receipts-single')).toContainText('1건');
    await page.reload(); // repeated initialisation does not attach it either
    await expect(page.getByText('아직 실행한 작업이 없어요.')).toBeVisible();
    const stored = await page.evaluate(() => [localStorage.getItem('ds2l.jobReceipts'), localStorage.getItem('ds2l.jobReceipts.v2')]);
    expect(JSON.parse(stored[0]!).data).toHaveLength(1); // v1 kept as is
    expect(stored[1] === null || JSON.parse(stored[1]).data.every((r: { paneId: string }) => r.paneId !== 'legacy')).toBe(true);
  });

  test('과거 로직이 귀속시킨 legacy v2 기록은 미확인으로 다루고, 정상 v2 기록은 그대로 복원한다', async ({ page }) => {
    const legacyV2 = { ...v1, instanceId: INSTANCE, datasetChecksum: null, paneId: 'legacy' };
    const normal = { ...v1, jobId: 77, sceneId: 22, sceneToken: 'scene-tok-103', sceneName: 'scene-0103', idempotencyKey: 'k-new', instanceId: INSTANCE, datasetChecksum: null, paneId: 'single', requestedAt: 1_800_000_000_000 };
    await page.addInitScript((d) => { localStorage.setItem('ds2l.jobReceipts.v2', JSON.stringify({ v: 2, data: d })); }, [legacyV2, normal]);
    await installMockApi(page, { jobSequence: ['RUNNING'] });
    await page.goto(ws(21));
    await expect(page.getByText('아직 실행한 작업이 없어요.')).toBeVisible();
    await expect(page.getByTestId('legacy-receipts-single')).toContainText('1건');
    await page.goto(ws(22));
    await expect(page.getByTestId('job-card-single')).toContainText('작업 #77');
    const v2 = await page.evaluate(() => JSON.parse(localStorage.getItem('ds2l.jobReceipts.v2')!).data);
    expect(v2).toHaveLength(2); // nothing deleted or overwritten
  });
});

test.describe('기능별 만료 시점의 화면 갱신 (만료 보완)', () => {
  test('응답 없이도 VESPA는 60초, recording은 90초에 각각 실행 버튼이 막히고 기존 결과는 유지된다', async ({ page }) => {
    await page.clock.install();
    const log = await installMockApi(page, { jobSequence: ['COMPLETED'], status: { ttlMs: { search: 15_000, vespa: 60_000, recording: 90_000 } } });
    await page.goto(ws(21, '&job=41'));
    const run = page.getByTestId('run-job-single');
    const create = page.getByTestId('create-recording');
    const box = page.getByTestId('vespa-readiness-single');
    await expect(run).toBeEnabled();
    await expect(create).toBeEnabled();
    await expect(page.locator('[data-status="COMPLETED"]')).toBeVisible();
    log.statusHang = true; // every later status GET stays unanswered
    const getsBefore = log.statusCalls.length;

    await page.clock.runFor(16_000); // search expired; VESPA/recording still valid
    await expect(run).toBeEnabled();
    await expect(create).toBeEnabled();

    await page.clock.runFor(46_000); // t ≈ 62 s
    await expect(run).toBeDisabled();
    await expect(box).toHaveAttribute('data-reason', 'STATUS_EXPIRED');
    await expect(page.getByTestId('vespa-last-known-single')).toContainText('준비됨');
    await expect(create).toBeEnabled(); // recording valid until 90 s
    await expect(page.locator('[data-status="COMPLETED"]')).toBeVisible(); // existing result kept
    await expect(page.locator('.cam-tile[data-channel="CAM_FRONT"] g[data-source="VESPA"]')).toHaveCount(1);

    await page.clock.runFor(30_000); // t ≈ 92 s
    await expect(create).toBeDisabled();
    await expect(run).toBeDisabled();
    await page.clock.runFor(60_000); // nothing left to expire: only the bounded poll, no GET loop
    expect(log.statusCalls.length - getsBefore).toBeLessThanOrEqual(3);
    expect(log.statusCalls.every((c) => !c.refresh)).toBe(true);

    log.statusHang = false; // fresh answers again
    await page.getByRole('button', { name: '지금 확인' }).click();
    await expect(run).toBeEnabled();
    await expect(create).toBeEnabled();
    expect(log.jobPosts).toHaveLength(0);
    expect(log.recordingPosts).toHaveLength(0);
  });
});
