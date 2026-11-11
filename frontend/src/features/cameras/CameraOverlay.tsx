import { memo, useMemo } from 'react';
import type { BoxView } from '@/api/models';
import { projectBox, type CompiledCamera, type ProjectedBox } from '@/lib/geometry/projection';
import { objectKey } from '@/features/objects/objectKeys';

export interface ProjectedItem {
  box: BoxView;
  key: string;
  proj: ProjectedBox;
  /** Screen bbox of the clipped edges in image pixels: [x0, y0, x1, y1]. */
  bbox: [number, number, number, number];
  /** Horizontal distance from the ego vehicle at this camera's timestamp (m), or Infinity if unknown. */
  dist: number;
}

/** Project every box into one camera; boxes behind the camera or outside the image are dropped. */
export function projectAll(camera: CompiledCamera | null, boxes: readonly BoxView[], ego: readonly number[] | null): ProjectedItem[] {
  if (!camera) return [];
  const out: ProjectedItem[] = [];
  for (const box of boxes) {
    const proj = projectBox(camera, box);
    if (!proj || !proj.segments.length) continue;
    let x0 = Infinity; let y0 = Infinity; let x1 = -Infinity; let y1 = -Infinity;
    for (const s of proj.segments) {
      x0 = Math.min(x0, s.x1, s.x2); y0 = Math.min(y0, s.y1, s.y2);
      x1 = Math.max(x1, s.x1, s.x2); y1 = Math.max(y1, s.y1, s.y2);
    }
    const dist = ego ? Math.hypot(box.center[0] - ego[0]!, box.center[1] - ego[1]!) : Infinity;
    out.push({ box, key: objectKey(box), proj, bbox: [x0, y0, x1, y1], dist });
  }
  return out;
}

/** Box colours of the design: GT yellow dashed, prediction blue solid (line style also names the source). */
export const BOX_COLOR = { GT: '#ffc800', VESPA: '#3d8bff' } as const;
const INK = { GT: '#191f28', VESPA: '#ffffff' } as const;
const FONT = '-apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Segoe UI", "Malgun Gothic", "Noto Sans KR", sans-serif';

let measureCtx: CanvasRenderingContext2D | null | undefined;
function textWidth(text: string): number {
  if (measureCtx === undefined) {
    try { measureCtx = document.createElement('canvas').getContext('2d'); } catch { measureCtx = null; }
    if (measureCtx) measureCtx.font = `700 11px ${FONT}`;
  }
  return measureCtx ? measureCtx.measureText(text).width : text.length * 6.6;
}

interface Props {
  items: ProjectedItem[];
  width: number;
  height: number;
  /** Screen pixels per image pixel (constant-size strokes, tags and hit slop). */
  scale: number;
  selectedKey: string | null;
  onSelect?: (key: string) => void;
  /** Class name tags (layer "클래스 이름"). */
  names: boolean;
  /** Small tile: only the selected object gets a tag. */
  compact: boolean;
}

/**
 * SVG in original image pixels (viewBox = width×height, xMidYMid meet = the image's object-fit: contain), so boxes
 * stay aligned through resizes. Tags follow the design: GT above the box, prediction below; without a selection only
 * objects within 30 m get a tag and overlapping tags are skipped (the selected object always has one).
 */
export const CameraOverlay = memo(function CameraOverlay({ items, width, height, scale, selectedKey, onSelect, names, compact }: Props) {
  const s = scale > 0 ? 1 / scale : 1;
  // Any selection (even one not visible in this camera) dims the others and hides their tags, as in the design.
  const anySel = selectedKey != null;
  const strokes = useMemo(() => [...items].sort((a, b) => Number(a.key === selectedKey) - Number(b.key === selectedKey) || b.dist - a.dist), [items, selectedKey]);
  const hits = useMemo(() => [...items].map((i) => {
    const [x0, y0, x1, y1] = i.bbox;
    const r = [Math.max(0, x0), Math.max(0, y0), Math.min(width, x1), Math.min(height, y1)] as const;
    return { i, r, area: (r[2] - r[0]) * (r[3] - r[1]) };
  }).filter((h) => h.r[2] - h.r[0] > 1 && h.r[3] - h.r[1] > 1).sort((a, b) => b.area - a.area), [items, width, height]);

  const tags = useMemo(() => {
    if (!names) return [];
    const placed: Array<[number, number, number, number]> = [];
    const out: Array<{ key: string; x: number; y: number; w: number; h: number; text: string; src: 'GT' | 'VESPA'; strong: boolean }> = [];
    const order = [...items].sort((a, b) => Number(b.key === selectedKey) - Number(a.key === selectedKey) || a.dist - b.dist);
    const ph = 19 * s;
    const top = 34 * s;
    for (const it of order) {
      const strong = it.key === selectedKey;
      if (!strong && (compact || anySel || it.dist > 30)) continue;
      const text = it.box.cls;
      const pw = (textWidth(text) + 16) * s;
      const gt = it.box.source === 'GT';
      const x = Math.min(Math.max(it.bbox[0], s), width - pw - s);
      const y = Math.min(Math.max(gt ? it.bbox[1] - ph - s : it.bbox[3] + s, top), height - ph - s);
      if (!strong && placed.some((r) => x < r[2] && x + pw > r[0] && y < r[3] && y + ph > r[1])) continue;
      placed.push([x, y, x + pw, y + ph]);
      out.push({ key: it.key, x, y, w: pw, h: ph, text, src: it.box.source, strong });
    }
    return out;
  }, [items, names, compact, anySel, selectedKey, s, width, height]);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      {strokes.map(({ box, key, proj }) => {
        const selected = key === selectedKey;
        const d = proj.segments.map((g) => `M${g.x1.toFixed(1)} ${g.y1.toFixed(1)}L${g.x2.toFixed(1)} ${g.y2.toFixed(1)}`).join('');
        return (
          <g key={box.key} data-box-key={box.key} data-object-key={key} data-source={box.source} opacity={anySel && !selected ? 0.45 : 1}>
            {selected && <path d={d} stroke="rgba(255,255,255,.85)" strokeWidth={4.5} vectorEffect="non-scaling-stroke" fill="none" />}
            <path d={d} stroke={BOX_COLOR[box.source]} strokeWidth={selected ? 2.5 : 1.5} strokeDasharray={box.source === 'GT' ? '6 4' : undefined}
              vectorEffect="non-scaling-stroke" fill="none" />
          </g>
        );
      })}
      {tags.map((t) => (
        <g key={`tag-${t.key}`} pointerEvents="none">
          <rect x={t.x} y={t.y} width={t.w} height={t.h} rx={t.h / 2} fill={BOX_COLOR[t.src]} stroke={t.strong ? '#fff' : undefined} strokeWidth={t.strong ? 1.5 * s : undefined} />
          <text x={t.x + 8 * s} y={t.y + t.h / 2 + 0.5 * s} dominantBaseline="middle" fontSize={11 * s} fontWeight={700} fill={INK[t.src]} fontFamily={FONT}>{t.text}</text>
        </g>
      ))}
      {onSelect && hits.map(({ i, r }) => (
        <rect key={`hit-${i.box.key}`} className="box-hit" data-hit-key={i.key} x={r[0] - 3 * s} y={r[1] - 3 * s} width={r[2] - r[0] + 6 * s} height={r[3] - r[1] + 6 * s}
          fill="transparent" pointerEvents="all" onClick={(e) => { e.stopPropagation(); onSelect(i.key); }} />
      ))}
    </svg>
  );
});
