import { expect, test, type Page } from '@playwright/test';
import { DATASET, installMockApi, openTab } from './fixtures/mockApi';

/**
 * FU-06: basic keyboard / focus / reduced-motion / status-message checks on the route-fixture UI (@a11y).
 * Not a screen-reader audit, not the real Safari app, and not image/point-cloud quality on real data.
 */
const ws = (sceneId: number, extra = '') => `/scenes/${sceneId}?dataset=${DATASET.id}${extra}`;

/**
 * WebKit follows Safari's default ("Press Tab to highlight each item" off): Tab skips links/buttons and Option+Tab
 * moves through every element. Use the key a Safari keyboard user would press.
 */
const nextKey = (page: Page) => (page.context().browser()?.browserType().name() === 'webkit' ? 'Alt+Tab' : 'Tab');

async function tabUntil(page: Page, match: (el: { name: string; tag: string }) => boolean, max = 60) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press(nextKey(page));
    const el = await page.evaluate(() => {
      const a = document.activeElement as HTMLElement | null;
      return { name: (a?.getAttribute('aria-label') || a?.textContent || '').trim(), tag: a?.tagName ?? '' };
    });
    if (match(el)) return el;
  }
  throw new Error('focus target not reached by Tab');
}

test.describe('FU-06 기본 접근성 @a11y', () => {
  test('키보드만으로 씬을 열고 프레임 이동·재생/정지, 입력 중에는 단축키가 동작하지 않는다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(`/scenes?dataset=${DATASET.id}`);
    await expect(page.getByRole('link', { name: /scene-0061 열기/ })).toBeVisible();
    await tabUntil(page, (e) => /scene-0061 열기/.test(e.name));
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'scene-0061' })).toBeVisible();
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    const readout = page.getByTestId('frame-readout-single');
    await page.locator('body').focus();
    await page.keyboard.press('ArrowRight');
    await expect(readout).toHaveText(/2\s*\/ 4/);
    await page.keyboard.press('ArrowLeft');
    await expect(readout).toHaveText(/1\s*\/ 4/);
    // typing in an input must not move frames
    await openTab(page, '자동 라벨링');
    const jobInput = page.getByLabel('번호로 열기');
    await jobInput.focus();
    await page.keyboard.press('ArrowRight');
    await page.keyboard.type(' 4');
    await expect(readout).toHaveText(/1\s*\/ 4/);
    await jobInput.blur(); // leave the input (body is not focusable, so focus() alone would keep it)
    await page.keyboard.press('Space');
    await expect(page.getByRole('button', { name: '일시정지' })).toHaveAttribute('aria-pressed', 'true');
    await page.keyboard.press('Space');
    await expect(page.getByRole('button', { name: '재생' })).toHaveAttribute('aria-pressed', 'false');
  });

  test('키보드로 연 카메라 확대: 포커스가 대화상자 안에 머물고 Esc 후 연 버튼으로 돌아온다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21, '&view=six'));
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    const expand = page.getByRole('button', { name: '전방 CAM_FRONT 크게 보기' });
    await expand.focus();
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    for (let i = 0; i < 25; i++) {
      await page.keyboard.press(nextKey(page));
      expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true);
    }
    await page.keyboard.press(`Shift+${nextKey(page)}`);
    expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(expand).toBeFocused();
  });

  test('Tab 포커스는 보이는 outline을 갖는다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21));
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    await page.waitForLoadState('networkidle');
    const seen = new Set<string>();
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press(nextKey(page));
      const r = await page.evaluate(() => {
        const a = document.activeElement as HTMLElement | null;
        if (!a || a === document.body) return null;
        const s = getComputedStyle(a);
        return { tag: a.tagName, label: a.getAttribute('aria-label') || a.textContent?.trim().slice(0, 30) || '', style: s.outlineStyle, width: parseFloat(s.outlineWidth), visible: a.matches(':focus-visible') };
      });
      if (!r || !['BUTTON', 'A'].includes(r.tag)) continue;
      seen.add(r.label);
      expect(r.visible, `${r.tag} ${r.label} ${JSON.stringify(r)}`).toBe(true);
      expect(r.style, `${r.tag} ${r.label}`).not.toBe('none');
      expect(r.width, `${r.tag} ${r.label}`).toBeGreaterThanOrEqual(2);
    }
    expect(seen.size).toBeGreaterThan(3);
  });

  test('prefers-reduced-motion: 회전·전환 애니메이션을 사실상 끈다', async ({ page }) => {
    await installMockApi(page);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(ws(21));
    await expect(page.locator('.cam-media[data-state="ready"]').first()).toBeVisible();
    const d = await page.evaluate(() => {
      const spin = document.createElement('span');
      spin.className = 'spinner';
      document.body.appendChild(spin);
      const btn = document.querySelector('.btn') as HTMLElement;
      const out = { spin: getComputedStyle(spin).animationDuration, iter: getComputedStyle(spin).animationIterationCount, btn: getComputedStyle(btn).transitionDuration };
      spin.remove();
      return out;
    });
    const secs = (v: string) => Math.max(...v.split(',').map((x) => (x.trim().endsWith('ms') ? parseFloat(x) / 1000 : parseFloat(x))));
    expect(secs(d.spin)).toBeLessThan(0.01);
    expect(d.iter).toBe('1');
    expect(secs(d.btn)).toBeLessThan(0.01);
  });

  test('상태 안내는 live region(status/alert)으로 노출된다', async ({ page }) => {
    const log = await installMockApi(page, { status: { origin: 'SYNTHETIC', vespa: 'UNAVAILABLE', vespaReason: 'SYNTHETIC_DATASET' } });
    await page.goto(ws(21));
    await openTab(page, '자동 라벨링');
    const readiness = page.getByTestId('vespa-readiness-single');
    await expect(readiness).toHaveAttribute('role', 'status');
    await expect(readiness).toContainText(/테스트\(합성\) 데이터/);
    await expect(page.locator('.toast-wrap')).toHaveAttribute('aria-live', 'polite');
    // FU-01 message (status API unreachable) is announced in the same status region
    log.statusFailure = 500;
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await expect(readiness).toHaveAttribute('data-reason', 'STATUS_UNREACHABLE');
    await expect(readiness).toHaveAttribute('role', 'status');
  });

  test('작업대의 보이는 버튼·링크·입력은 모두 접근 가능한 이름이 있다', async ({ page }) => {
    await installMockApi(page);
    for (const url of [`/scenes?dataset=${DATASET.id}`, ws(21), ws(21, '&view=six'), `/compare?datasetA=${DATASET.id}&sceneA=21&datasetB=${DATASET.id}&sceneB=22`]) {
      await page.goto(url);
      await page.waitForLoadState('networkidle');
      const unnamed = await page.evaluate(() => {
        const nameOf = (el: HTMLElement) => {
          const by = el.getAttribute('aria-labelledby');
          const ref = by ? by.split(/\s+/).map((id) => document.getElementById(id)?.textContent ?? '').join(' ') : '';
          const label = el.id ? document.querySelector(`label[for="${el.id}"]`)?.textContent ?? '' : '';
          const wrap = el.closest('label')?.textContent ?? '';
          return (el.getAttribute('aria-label') || ref || label || wrap || el.textContent || el.getAttribute('title') || (el as HTMLInputElement).placeholder || '').trim();
        };
        return Array.from(document.querySelectorAll<HTMLElement>('button, a[href], input:not([type=hidden]), select, [role=button], [role=radio], [role=separator][tabindex]'))
          .filter((el) => el.offsetParent !== null || el.getClientRects().length > 0)
          .filter((el) => !nameOf(el))
          .map((el) => el.outerHTML.slice(0, 120));
      });
      expect(unnamed, url).toEqual([]);
    }
  });
});
