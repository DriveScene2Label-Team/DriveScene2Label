import { useEffect, useState } from 'react';
import { useToasts } from '@/stores/toast';
import { Icon } from './Icon';

/** Bottom-centre toast (one at a time) and a polite live region for quiet announcements. */
export function ToastHost() {
  const t = useToasts((s) => s.current);
  const announcement = useToasts((s) => s.announcement);
  const dismiss = useToasts((s) => s.dismiss);
  const [spoken, setSpoken] = useState('');
  useEffect(() => {
    if (!announcement) return;
    setSpoken('');
    const id = window.setTimeout(() => setSpoken(announcement.text), 30);
    return () => window.clearTimeout(id);
  }, [announcement]);
  return (
    <>
      <div className="toast-wrap" role="status" aria-live="polite">
        {t && (
          <div className={`toast${t.kind === 'info' ? '' : ` is-${t.kind}`}`} key={t.id} data-testid="toast">
            {t.kind !== 'info' && <span className="t-ic"><Icon name={t.kind === 'ok' ? 'check' : 'warn'} /></span>}
            <span className="t-text">{t.message}</span>
            {t.action && (
              <>
                <button type="button" className="t-act" onClick={() => { const run = t.action!.run; dismiss(t.id); run(); }}>{t.action.label}</button>
                <button type="button" className="t-x" onClick={() => dismiss(t.id)} aria-label="알림 닫기"><Icon name="close" /></button>
              </>
            )}
          </div>
        )}
      </div>
      <div className="sr-only" aria-live="polite">{spoken}</div>
    </>
  );
}
