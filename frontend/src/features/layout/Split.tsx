import { useRef, useState, type ReactNode } from 'react';
import { useElementSize } from '@/hooks/useElementSize';
import { RATIO_MIN } from '@/stores/layout';

const DIV = 9;

/**
 * Ratio that fits the six cameras without gaps (design rule): 3D below → camera height for a 3×2 grid across the
 * width; 3D on the right → camera width for a 2×3 grid down the height.
 */
export function autoRatio(width: number, height: number, orient: 'stack' | 'side'): number {
  const pad = 24; const padV = 12; const gap = 8;
  if (width < 10 || height < 10) return 0.5;
  const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
  if (orient === 'stack') {
    const tw = (width - pad - gap * 2) / 3;
    return clamp((2 * tw * 9 / 16 + gap + padV) / (height - DIV), 0.3, 0.72);
  }
  const th = (height - padV - gap * 2) / 3;
  return clamp((2 * th * 16 / 9 + gap + pad) / (width - DIV), 0.36, 0.64);
}

interface Props {
  orient: 'stack' | 'side';
  /** null = automatic (fit the cameras). */
  ratio: number | null;
  max: number;
  onChange: (ratio: number) => void;
  onReset: () => void;
  label: string;
  className?: string;
  a: ReactNode;
  b: ReactNode;
}

/** Two areas with a draggable separator: pointer drag, arrow keys (Shift = larger step), Home/End, Enter/double-click to reset. */
export function Split({ orient, ratio, max, onChange, onReset, label, className, a, b }: Props) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const box = useRef<HTMLDivElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const value = ratio ?? autoRatio(size.width, size.height, orient);
  const set = (r: number) => onChange(Math.min(max, Math.max(RATIO_MIN, r)));
  const fromPointer = (x: number, y: number) => {
    const r = box.current?.getBoundingClientRect();
    if (!r) return;
    if (orient === 'stack') { if (r.height > DIV) set((y - r.top - DIV / 2) / (r.height - DIV)); }
    else if (r.width > DIV) set((x - r.left - DIV / 2) / (r.width - DIV));
  };
  const dec = orient === 'stack' ? 'ArrowUp' : 'ArrowLeft';
  const inc = orient === 'stack' ? 'ArrowDown' : 'ArrowRight';
  return (
    <div ref={(el) => { box.current = el; ref(el); }} className={className ? `split ${className}` : 'split'} data-orient={orient} style={{ ['--ratio' as string]: value.toFixed(4) }}>
      <div className="split-a">{a}</div>
      <div className={dragging ? 'divider is-dragging' : 'divider'} role="separator" tabIndex={0}
        aria-orientation={orient === 'stack' ? 'horizontal' : 'vertical'} aria-label={label}
        aria-valuemin={Math.round(RATIO_MIN * 100)} aria-valuemax={Math.round(max * 100)} aria-valuenow={Math.round(value * 100)}
        title="드래그하거나 방향키로 조절, 더블클릭하면 처음대로"
        onPointerDown={(e) => { if (e.button !== 0) return; e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); setDragging(true); }}
        onPointerMove={(e) => { if (dragging) fromPointer(e.clientX, e.clientY); }}
        onPointerUp={(e) => { setDragging(false); if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId); }}
        onPointerCancel={() => setDragging(false)}
        onDoubleClick={onReset}
        onKeyDown={(e) => {
          const step = e.shiftKey ? 0.08 : 0.02;
          if (e.key === dec) set(value - step);
          else if (e.key === inc) set(value + step);
          else if (e.key === 'Home') set(RATIO_MIN);
          else if (e.key === 'End') set(max);
          else if (e.key === 'Enter') onReset();
          else return;
          e.preventDefault();
          e.stopPropagation();
        }} />
      <div className="split-b">{b}</div>
    </div>
  );
}
