import { useEffect, useState, type ReactNode } from 'react';

/** Presentation only: oauth2-proxy enforces authentication on every API request. */
export function AuthGate({ children, required = import.meta.env.VITE_AUTH_REQUIRED === 'true' }: { children: ReactNode; required?: boolean }) {
  const [state, setState] = useState<'checking' | 'ready' | 'login' | 'error'>(required ? 'checking' : 'ready');
  useEffect(() => {
    if (!required) return;
    const controller = new AbortController();
    fetch('/oauth2/auth', { signal: controller.signal, cache: 'no-store' })
      .then(response => setState(response.status === 202 ? 'ready' : response.status === 401 ? 'login' : 'error'))
      .catch(() => { if (!controller.signal.aborted) setState('error'); });
    return () => controller.abort();
  }, [required]);
  if (state === 'ready') return children;
  const destination = window.location.origin + window.location.pathname + window.location.search;
  return <main className="page-state" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', gap: 16 }}>
    <h1>DriveScene2Label</h1>
    {state === 'checking' && <p role="status">로그인을 확인하고 있어요.</p>}
    {state === 'login' && <>
      <p>팀 계정으로 로그인해 주세요.</p>
      <a className="btn btn-primary" href={`/oauth2/start?rd=${encodeURIComponent(destination)}`}>팀 계정으로 로그인</a>
    </>}
    {state === 'error' && <>
      <p role="alert">서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.</p>
      <button className="btn" onClick={() => window.location.reload()}>다시 시도</button>
    </>}
  </main>;
}
