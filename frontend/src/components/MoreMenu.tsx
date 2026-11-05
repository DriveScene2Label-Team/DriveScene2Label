import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { useLayout, type Orient, type Theme } from '@/stores/layout';
import { useOverlay } from '@/stores/overlay';
import { Icon } from './Icon';

/** "더 보기" menu: camera + 3D arrangement (workspace), colour theme, shortcut sheet (workspace). */
export function MoreMenu({ workspace }: { workspace: boolean }) {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();
  const orient = useLayout((s) => s.orient);
  const theme = useLayout((s) => s.theme);
  const setOrient = useLayout((s) => s.setOrient);
  const setTheme = useLayout((s) => s.setTheme);
  const openOverlay = useOverlay((s) => s.open);

  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>('[role^="menuitem"]')?.focus();
    const onDown = (e: PointerEvent) => {
      if (!menu.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  }, [open]);

  const close = (focusButton: boolean) => { setOpen(false); if (focusButton) btn.current?.focus(); };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const items = [...(menu.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]') ?? [])];
    const k = items.indexOf(document.activeElement as HTMLElement);
    if (e.key === 'ArrowDown') items[(k + 1) % items.length]?.focus();
    else if (e.key === 'ArrowUp') items[(k - 1 + items.length) % items.length]?.focus();
    else if (e.key === 'Home') items[0]?.focus();
    else if (e.key === 'End') items[items.length - 1]?.focus();
    else if (e.key === 'Escape') close(true);
    else if (e.key === 'Tab') { setOpen(false); return; }
    else return;
    e.preventDefault();
    e.stopPropagation();
  };
  const radio = (checked: boolean, label: string, onPick: () => void) => (
    <button type="button" role="menuitemradio" aria-checked={checked} onClick={() => { onPick(); close(true); }}>{label}</button>
  );
  const orientItem = (o: Orient, label: string) => radio(orient === o, label, () => setOrient(o));
  const themeItem = (t: Theme, label: string) => radio(theme === t, label, () => setTheme(t));

  return (
    <div className="menu-wrap">
      <button ref={btn} type="button" className="icon-btn" aria-haspopup="menu" aria-expanded={open} aria-controls={id} aria-label="더 보기" title="더 보기" onClick={() => setOpen((v) => !v)}>
        <Icon name="more" />
      </button>
      {open && (
        <div ref={menu} className="menu" id={id} role="menu" aria-label="더 보기" onKeyDown={onKey}>
          {workspace && (
            <>
              <div className="menu-label">카메라 + 3D 배치</div>
              {orientItem('stack', '3D를 카메라 아래에')}
              {orientItem('side', '3D를 카메라 오른쪽에')}
              <div className="menu-sep" role="separator" />
            </>
          )}
          <div className="menu-label">화면 색</div>
          {themeItem('light', '밝게')}
          {themeItem('dark', '어둡게')}
          {themeItem('auto', '시스템 설정 따르기')}
          {workspace && (
            <>
              <div className="menu-sep" role="separator" />
              <button type="button" role="menuitem" onClick={() => { close(false); openOverlay({ kind: 'keys' }); }}>단축키<span className="menu-key">?</span></button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
