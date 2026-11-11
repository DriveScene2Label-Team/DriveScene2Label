import { expect, test } from '@playwright/test';

/** Data-agnostic smoke against the real Spring API: it accepts error/empty outcomes (failure display). Real-data success is actual-mini.spec.ts. */
test('real Spring: datasets → scene → 6 cameras, GT and job/recording states', async ({ page, request }) => {
  const note = (type: string, description: string) => test.info().annotations.push({ type, description });
  const datasets = await (await request.get('/api/datasets')).json() as Array<{ id: number; name: string; version: string }>;
  expect(datasets.length).toBeGreaterThan(0);
  const ds = datasets[0]!;
  note('dataset', `${ds.id} ${ds.name} ${ds.version}`);
  const scenes = await (await request.get(`/api/datasets/${ds.id}/scenes`)).json() as Array<{ id: number; name: string; nbrSamples: number }>;
  const scene = scenes[0]!;
  note('scene', `${scene.id} ${scene.name} (${scene.nbrSamples} samples)`);

  await page.goto('/scenes');
  await expect(page).toHaveURL(new RegExp(`dataset=${ds.id}`));
  await expect(page.locator('.card-hit')).toHaveCount(scenes.length);
  await page.getByRole('link', { name: new RegExp(`${scene.name} 열기`) }).click();
  await expect(page.getByRole('heading', { name: scene.name })).toBeVisible();

  // every camera tile settles into ready / missing / error (never stuck loading)
  await expect(page.locator('.cam-tile')).toHaveCount(6);
  await expect(page.locator('.cam-tile [data-state="loading"]')).toHaveCount(0, { timeout: 30_000 });
  const states = await page.locator('.cam-tile').evaluateAll((els) => els.map((e) => `${e.getAttribute('data-channel')}:${e.querySelector('[data-state]')?.getAttribute('data-state')}`));
  note('cameras', states.join(', '));

  // GT list equals the API's annotations for the displayed sample
  const samples = await (await request.get(`/api/scenes/${scene.id}/samples?limit=1&offset=0`)).json() as Array<{ id: number }>;
  const gt = await (await request.get(`/api/samples/${samples[0]!.id}/annotations`)).json() as Array<{ categoryName?: string | null }>;
  await expect(page.locator('.otable tbody tr')).toHaveCount(gt.length);
  note('gt', `${gt.length} boxes, categories: ${[...new Set(gt.map((g) => g.categoryName ?? 'null'))].join(', ')}`);

  // search answers with results, an empty state, or an error state — never a silent mock
  await page.goto(`/scenes?dataset=${ds.id}&q=rainy%20night%20road`);
  // settled = a result grid or a state box (the loading skeleton grid is aria-hidden)
  await expect(page.locator('#results .empty, #results .grid:not([aria-hidden])').first()).toBeVisible({ timeout: 45_000 });
  note('search', (await page.locator('#results').innerText()).replace(/\s+/g, ' ').slice(0, 160));
  note('search-readiness', (await page.getByTestId('search-readiness').getAttribute('data-reason').catch(() => null)) ?? 'READY');

  const jobId = process.env.DS2L_LIVE_JOB_ID;
  if (jobId) {
    await page.goto(`/scenes/${scene.id}?dataset=${ds.id}&job=${jobId}`);
    await page.getByRole('tab', { name: /자동 라벨링/ }).click();
    const card = page.getByTestId('job-card-single');
    await expect(card.locator('[data-status]')).toBeVisible({ timeout: 15_000 });
    note('job', (await card.innerText()).replace(/\s+/g, ' ').slice(0, 200));
  }

  await page.goto(`/scenes/${scene.id}?dataset=${ds.id}&view=split`);
  const lidar = page.locator('.v3d');
  await expect(lidar.locator('.v3d-state, [data-testid="rerun-host"]').first()).toBeVisible({ timeout: 20_000 });
  if (process.env.DS2L_LIVE_ALLOW_POST && await page.getByRole('button', { name: /3D recording 만들기|recording 다시 만들기/ }).count()) {
    await page.getByRole('button', { name: /3D recording 만들기|recording 다시 만들기/ }).click();
    // READY (viewer opens) or FAILED (reason shown) — whichever the real worker reaches.
    await expect(page.locator('[data-testid="rerun-host"][data-phase="ready"], .v3d-state[role="alert"]').first()).toBeVisible({ timeout: 75_000 });
  }
  note('recording', (await lidar.innerText()).replace(/\s+/g, ' ').slice(0, 200));
  await page.screenshot({ path: 'test-results/live/workspace.png' });
});
