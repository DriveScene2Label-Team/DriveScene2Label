import { useEffect } from 'react';
import { useRouteError } from 'react-router';

const RELOAD_KEY = 'ds2l:chunk-reload-at';
const RELOAD_COOLDOWN_MS = 60_000;

export function isChunkLoadError(error: unknown): boolean {
  return error instanceof Error && /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS|Loading chunk .* failed/i.test(error.message);
}

/** Persist the attempt across reloads so offline/broken deployments cannot loop. */
export function recoverChunkLoad(error: unknown, storage: Pick<Storage, 'getItem' | 'setItem'>, reload: () => void, now = Date.now()): boolean {
  if (!isChunkLoadError(error)) return false;
  try {
    const previous = Number(storage.getItem(RELOAD_KEY));
    if (previous && now - previous < RELOAD_COOLDOWN_MS) return false;
    storage.setItem(RELOAD_KEY, String(now));
  } catch { return false; } // Without persistent storage, offer manual recovery instead.
  reload();
  return true;
}

export function RouteErrorPage() {
  const error = useRouteError();
  const chunkError = isChunkLoadError(error);
  useEffect(() => {
    if (!navigator.onLine) return;
    try { recoverChunkLoad(error, window.sessionStorage, () => window.location.reload()); }
    catch { /* Storage can be blocked by browser privacy settings. Keep the recovery controls. */ }
  }, [error]);
  return <main className="page-state" role="alert"><div>
    <h1>화면을 다시 불러와 주세요</h1>
    <p>{chunkError ? '새 버전의 화면 파일을 불러오지 못했어요. 연결을 확인하고 새로고침해 주세요.' : '화면을 표시하는 중 오류가 발생했어요. 새로고침하거나 씬 목록으로 이동해 주세요.'}</p>
    <p>서버에서 진행 중인 라벨 작업과 저장한 결과는 유지됩니다.</p>
    <button className="btn btn--primary" onClick={() => window.location.reload()}>새로고침</button>{' '}
    <a className="btn btn--weak" href="/scenes">씬 목록</a>
  </div></main>;
}
