/**
 * Icon set of the renewal design (docs/frontend-design/renewal-mockup.html): one hidden SVG sprite rendered once by
 * the app, and <Icon name> referencing a symbol. Line icons use currentColor via the .ic class.
 */
export type IconName = 'play' | 'pause' | 'prev' | 'next' | 'expand' | 'close' | 'eye' | 'eye-off' | 'back' | 'link' | 'sidebar' | 'more' | 'search' | 'check' | 'reset' | 'text' | 'warn' | 'info' | 'cube' | 'camoff';

export function IconSprite() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true" focusable="false">
      <defs>
        <symbol id="i-play" viewBox="0 0 16 16"><path d="M4.6 2.6c0-.6.6-.9 1.1-.6l8 5.4c.4.3.4.9 0 1.2l-8 5.4c-.5.3-1.1 0-1.1-.6z" fill="currentColor" stroke="none"/></symbol>
        <symbol id="i-pause" viewBox="0 0 16 16"><rect x="3.6" y="2.6" width="3" height="10.8" rx=".9" fill="currentColor" stroke="none"/><rect x="9.4" y="2.6" width="3" height="10.8" rx=".9" fill="currentColor" stroke="none"/></symbol>
        <symbol id="i-prev" viewBox="0 0 16 16"><rect x="2.6" y="3" width="1.8" height="10" rx=".7" fill="currentColor" stroke="none"/><path d="M13.4 3.6c0-.5-.6-.8-1-.5L6 7.5c-.4.3-.4.8 0 1L12.4 13c.4.3 1 0 1-.5z" fill="currentColor" stroke="none"/></symbol>
        <symbol id="i-next" viewBox="0 0 16 16"><rect x="11.6" y="3" width="1.8" height="10" rx=".7" fill="currentColor" stroke="none"/><path d="M2.6 3.6c0-.5.6-.8 1-.5L10 7.5c.4.3.4.8 0 1L3.6 13c-.4.3-1 0-1-.5z" fill="currentColor" stroke="none"/></symbol>
        <symbol id="i-expand" viewBox="0 0 16 16"><path d="M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5 9.2 6.8M2.5 13.5l4.3-4.3"/></symbol>
        <symbol id="i-close" viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8"/></symbol>
        <symbol id="i-eye" viewBox="0 0 16 16"><path d="M1.6 8S4.1 3.6 8 3.6 14.4 8 14.4 8 11.9 12.4 8 12.4 1.6 8 1.6 8z"/><circle cx="8" cy="8" r="2"/></symbol>
        <symbol id="i-eye-off" viewBox="0 0 16 16"><path d="M2.6 2.6l10.8 10.8"/><path d="M6.4 3.9c.5-.2 1-.3 1.6-.3 3.9 0 6.4 4.4 6.4 4.4s-.6 1.1-1.8 2.3M4.3 5.3C2.6 6.5 1.6 8 1.6 8S4.1 12.4 8 12.4c1 0 1.9-.3 2.7-.7"/></symbol>
        <symbol id="i-back" viewBox="0 0 16 16"><path d="M10 3.2 5.2 8l4.8 4.8"/></symbol>
        <symbol id="i-link" viewBox="0 0 16 16"><path d="M6.9 9.1a2.7 2.7 0 0 0 3.8 0l2.3-2.3a2.7 2.7 0 0 0-3.8-3.8l-.9.9"/><path d="M9.1 6.9a2.7 2.7 0 0 0-3.8 0L3 9.2A2.7 2.7 0 0 0 6.8 13l.9-.9"/></symbol>
        <symbol id="i-sidebar" viewBox="0 0 16 16"><rect x="1.8" y="2.8" width="12.4" height="10.4" rx="2.2"/><path d="M10.2 2.8v10.4"/><path d="M11.7 5.3h1M11.7 7.1h1"/></symbol>
        <symbol id="i-more" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.3"/><circle cx="5.1" cy="8" r=".8" fill="currentColor" stroke="none"/><circle cx="8" cy="8" r=".8" fill="currentColor" stroke="none"/><circle cx="10.9" cy="8" r=".8" fill="currentColor" stroke="none"/></symbol>
        <symbol id="i-search" viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.4"/><path d="m10.3 10.3 3.4 3.4"/></symbol>
        <symbol id="i-check" viewBox="0 0 16 16"><path d="M3.4 8.6 6.4 11.6 12.6 4.6"/></symbol>
        <symbol id="i-reset" viewBox="0 0 16 16"><path d="M3.3 8a4.7 4.7 0 1 0 1.4-3.3"/><path d="M3.1 2.6v2.7h2.7"/></symbol>
        <symbol id="i-text" viewBox="0 0 16 16"><path d="M1.8 12.6 5.4 3.4l3.6 9.2M3 9.6h4.8"/><path d="M12 7.9a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM14 7.9v4.7"/></symbol>
        <symbol id="i-warn" viewBox="0 0 16 16"><path d="M8 2.4 1.6 13.4h12.8z"/><path d="M8 6.6v3.2M8 11.5v.1"/></symbol>
        <symbol id="i-info" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.3"/><path d="M8 7.3v4M8 4.9v.1"/></symbol>
        <symbol id="i-cube" viewBox="0 0 16 16"><path d="M8 1.8 2.6 4.9v6.2L8 14.2l5.4-3.1V4.9z"/><path d="M2.6 4.9 8 8l5.4-3.1M8 8v6.2"/></symbol>
        <symbol id="i-camoff" viewBox="0 0 24 24"><path d="M3 3l18 18"/><path d="M8.5 6H9l1.5-2h3L15 6h3a2 2 0 0 1 2 2v8.5M17.5 19H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2"/><path d="M9.8 10.2a3 3 0 0 0 4 4"/></symbol>
      </defs>
    </svg>
  );
}

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg className={className ? `ic ${className}` : 'ic'} aria-hidden="true" focusable="false">
      <use href={`#i-${name}`} />
    </svg>
  );
}
