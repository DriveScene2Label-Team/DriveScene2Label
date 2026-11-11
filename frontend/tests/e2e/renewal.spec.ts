import { expect, test } from '@playwright/test';
import { DATASET, installMockApi, openTab, sampleToken } from './fixtures/mockApi';

/** UI renewal flows on route fixtures (label edits, library picking, shortcuts, theme). Not live-server verification. */
const ws = (sceneId: number, extra = '') => `/scenes/${sceneId}?dataset=${DATASET.id}${extra}`;
const IS_MAC = process.platform === 'darwin';

test.describe('라벨 수정 (이름 변경·삭제·되돌리기·기록)', () => {
  test('GT 클래스를 모든 프레임에 바꾸고, 토스트로 되돌린다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21));
    const table = page.getByRole('table', { name: /프레임 1의 객체/ });
    await table.getByRole('row', { name: /^GT car,/ }).click();
    const editor = page.getByTestId('object-detail');
    await expect(editor.getByText('이 객체가 나오는 프레임 (4개)')).toBeVisible();
    await editor.getByLabel('클래스', { exact: true }).selectOption('truck');
    const toast = page.getByTestId('toast');
    await expect(toast).toContainText('car를 truck으로 바꿨어요 (4개 프레임)');
    await expect(editor.locator('.ed-label')).toHaveText('truck');
    await expect(editor).toContainText('원래 클래스 car에서 바꿨어요');
    // the same object in another frame is renamed too (selection follows the instance)
    await page.getByRole('button', { name: '다음 프레임' }).click();
    await expect(page.getByTestId('frame-readout-single')).toHaveText(/2\s*\/ 4/);
    await expect(editor.locator('.ed-label')).toHaveText('truck');
    await expect(page.locator('.cam-tile[data-channel="CAM_FRONT"] g[data-object-key="gt:3:inst-21-1"]')).toBeAttached();
    await toast.getByRole('button', { name: '되돌리기' }).click();
    await expect(page.getByTestId('toast')).toContainText('수정을 되돌렸어요');
    await expect(editor.locator('.ed-label')).toHaveText('car');
  });

  test('삭제는 확인 창에서 범위를 고르고, 기록 탭에서 최신 수정부터 되돌린다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21));
    const table = page.getByRole('table', { name: /프레임 1의 객체/ });
    await table.getByRole('row', { name: /^GT car,/ }).click();
    await page.getByTestId('object-detail').getByLabel('클래스', { exact: true }).selectOption('bus');
    await expect(page.getByTestId('toast')).toContainText('car를 bus로 바꿨어요');
    await page.getByTestId('ask-delete').click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('GT bus를 삭제할까요?');
    await expect(dialog.getByRole('radio', { name: /이 객체의 모든 프레임/ })).toBeChecked();
    await dialog.getByRole('radio', { name: /지금 프레임만/ }).check();
    await dialog.getByTestId('confirm-delete').click();
    await expect(page.getByTestId('toast')).toContainText('GT bus를 삭제했어요');
    await expect(table.locator('tbody tr')).toHaveCount(2);
    await expect(page.locator('g[data-object-key="gt:3:inst-21-1"]')).toHaveCount(0);
    // other frames still have the object
    await page.getByRole('button', { name: '다음 프레임' }).click();
    await expect(page.getByRole('table', { name: /프레임 2의 객체/ }).locator('tbody tr')).toHaveCount(3);

    await openTab(page, '기록');
    const rows = page.getByRole('list', { name: '수정 기록' }).getByRole('listitem');
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0)).toContainText('bus 삭제');
    await expect(rows.nth(0)).toContainText('GT · 프레임 1');
    await expect(rows.nth(1)).toContainText('car → bus');
    await expect(rows.nth(1)).toContainText('4개 프레임');
    // the older edit waits for the newer one (same object)
    await expect(rows.nth(1).getByRole('button', { name: '되돌리기' })).toHaveCount(0);
    await rows.nth(0).getByRole('button', { name: '되돌리기' }).click();
    await expect(rows.nth(0)).toContainText('되돌림');
    await rows.nth(1).getByRole('button', { name: '되돌리기' }).click();
    await expect(rows.nth(1)).toContainText('되돌림');
    await expect(page.getByRole('tab', { name: /^기록/ })).not.toContainText(/\d/);
  });

  test('⌘/Ctrl+Z는 마지막 수정을 되돌리고, 예측 박스도 이름을 바꿀 수 있다', async ({ page }) => {
    await installMockApi(page, { jobSequence: ['COMPLETED'] });
    await page.goto(ws(21, '&job=41'));
    await expect(page.locator('.cam-tile[data-channel="CAM_FRONT"] g[data-source="VESPA"]')).toHaveCount(1);
    const table = page.getByRole('table', { name: /프레임 1의 객체/ });
    await table.getByRole('row', { name: /^예측 car,/ }).click();
    const editor = page.getByTestId('object-detail');
    await expect(editor).toContainText('예측 · 작업 #41');
    await expect(editor.getByText('모든 프레임에 적용')).toHaveCount(0); // predictions are edited per box
    await editor.getByLabel('클래스', { exact: true }).selectOption('truck');
    await expect(page.getByTestId('toast')).toContainText('car를 truck으로 바꿨어요');
    await expect(table.getByRole('row', { name: /^예측 truck,.*수정됨/ })).toBeVisible();
    await openTab(page, '자동 라벨링');
    await expect(page.getByTestId('job-card-single')).toContainText('이름 바꾼 박스 1개');
    await page.locator('body').click({ position: { x: 5, y: 300 } });
    await page.keyboard.press(IS_MAC ? 'Meta+z' : 'Control+z');
    await expect(page.getByTestId('toast')).toContainText('수정을 되돌렸어요');
    await openTab(page, '객체');
    await expect(table.getByRole('row', { name: /^예측 car,/ })).toBeVisible();
  });

  test('라벨 수정 API가 없는 이전 서버: 실패를 알리고 화면은 원래 값을 유지한다', async ({ page }) => {
    await installMockApi(page, { labelEdits: 'missing' });
    await page.goto(ws(21));
    await page.getByRole('table', { name: /프레임 1의 객체/ }).getByRole('row', { name: /^GT car,/ }).click();
    const editor = page.getByTestId('object-detail');
    await editor.getByLabel('클래스', { exact: true }).selectOption('truck');
    await expect(page.getByTestId('toast')).toContainText('저장하지 못했어요');
    await expect(editor.getByLabel('클래스', { exact: true })).toHaveValue('car');
    await openTab(page, '기록');
    await expect(page.getByText('이 서버는 라벨 수정 기록을 제공하지 않아요.')).toBeVisible();
  });
});

test.describe('표시·단축키', () => {
  test('숨기기(H)와 G/P 단축키, 모두 보이기', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21, '&view=six'));
    await expect(page.locator('.cam-media[data-state="ready"]')).toHaveCount(6);
    await page.getByRole('table', { name: /프레임 1의 객체/ }).getByRole('row', { name: /^GT car,/ }).click();
    await page.locator('body').click({ position: { x: 5, y: 300 } });
    await page.keyboard.press('h');
    await expect(page.locator('g[data-object-key="gt:3:inst-21-1"]')).toHaveCount(0);
    await expect(page.locator('.hud-note')).toContainText('숨긴 객체 1개');
    await page.getByRole('button', { name: '모두 보이기' }).first().click();
    await expect(page.locator('g[data-object-key="gt:3:inst-21-1"]').first()).toBeAttached();
    await page.keyboard.press('g');
    await expect(page.locator('g[data-source="GT"]')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'GT', exact: true })).toHaveAttribute('aria-pressed', 'false');
    await page.keyboard.press('g');
    await expect(page.locator('g[data-source="GT"]').first()).toBeAttached();
    await page.keyboard.press('?');
    await expect(page.getByRole('dialog', { name: '단축키' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: '단축키' })).toBeHidden();
  });

  test('화면 색은 메뉴에서 바꾸고 새로고침 뒤에도 유지된다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(`/scenes?dataset=${DATASET.id}`);
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await page.getByRole('button', { name: '더 보기' }).click();
    await page.getByRole('menuitemradio', { name: '어둡게' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  });

  test('카메라 + 3D 배치를 3D 오른쪽으로 바꾸면 분할 방향이 바뀐다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21));
    await expect(page.locator('.split[data-orient="stack"]')).toBeAttached();
    await page.getByRole('button', { name: '더 보기' }).click();
    await page.getByRole('menuitemradio', { name: '3D를 카메라 오른쪽에' }).click();
    await expect(page.locator('.split[data-orient="side"]')).toBeAttached();
    await expect(page.getByRole('separator', { name: '카메라와 3D 영역 너비 비율' })).toBeVisible();
  });
});

test.describe('라이브러리에서 비교할 씬 고르기', () => {
  test('두 씬을 고르면 비교 화면을 열고, 비교 닫기는 작업 대상 씬으로 돌아간다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(`/scenes?dataset=${DATASET.id}`);
    await page.getByRole('button', { name: '비교할 씬 고르기' }).click();
    const bar = page.getByRole('region', { name: '비교할 씬' });
    await expect(bar.getByRole('button', { name: '비교하기' })).toBeDisabled();
    await page.getByRole('button', { name: /^scene-0061\./ }).click();
    await page.getByRole('button', { name: /^scene-0103\./ }).click();
    await expect(bar).toContainText('scene-0061과 scene-0103');
    await bar.getByRole('button', { name: '비교하기' }).click();
    await expect(page).toHaveURL(/\/compare\?.*sceneA=21.*sceneB=22/);
    await expect(page.getByRole('heading', { name: '두 씬 비교' })).toBeVisible();
    await page.getByRole('radio', { name: /B\s*scene-0103/ }).click();
    await page.getByRole('button', { name: '비교 닫기' }).click();
    await expect(page).toHaveURL(/\/scenes\/22\?/);
    await expect(page.getByRole('heading', { name: 'scene-0103' })).toBeVisible();
  });

  test('작업대의 비교 모드는 현재 씬과 다음 씬을 연다', async ({ page }) => {
    await installMockApi(page);
    await page.goto(ws(21, `&sample=${sampleToken(21, 1)}`));
    await page.getByRole('group', { name: '보기 방식' }).getByRole('button', { name: '비교' }).click();
    await expect(page).toHaveURL(/sceneA=21.*sampleA=smp-21-1.*sceneB=22/);
    await expect(page.getByTestId('frame-readout-A')).toHaveText(/2\s*\/ 4/);
  });
});
