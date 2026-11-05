import { useEffect } from 'react';
import { useLayout } from '@/stores/layout';

/** Applies the theme preference to <html data-theme>. "auto" follows the system setting and its changes. */
export function ThemeSync() {
  const theme = useLayout((s) => s.theme);
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    const apply = () => {
      document.documentElement.dataset.theme = theme === 'auto' ? (mq?.matches ? 'dark' : 'light') : theme;
    };
    apply();
    if (theme !== 'auto' || !mq) return;
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, [theme]);
  return null;
}
