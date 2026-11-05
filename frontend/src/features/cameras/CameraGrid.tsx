import type { BoxView } from '@/api/models';
import type { CameraSlot } from '@/features/frames/useFrameBundle';
import { useElementSize } from '@/hooks/useElementSize';
import { useFlowLayout } from '@/hooks/useMediaQuery';
import { CameraTile } from './CameraTile';

const GAP = 8;
const PAD_X = 24; // .camgrid padding 0 12px 12px
const PAD_Y = 12;
const ASPECT = 16 / 9;

export type GridLayout = '3x2' | '2x3';

/**
 * Pick 3×2 or 2×3 so the six cameras are as large as possible (design rule). `fit: 'width'` (compare pane with 3D
 * below) always uses 3×2 across the width; narrow/flow layouts choose by width only.
 */
export function chooseLayout(width: number, height: number, opts: { fit?: 'width'; flow?: boolean } = {}): { layout: GridLayout; cols: number; tileWidth: number } {
  const W = Math.max(0, width - PAD_X);
  const H = Math.max(0, height - PAD_Y);
  if (opts.fit === 'width') return { layout: '3x2', cols: 3, tileWidth: Math.floor((W - GAP * 2) / 3) };
  if (opts.flow || H < 60) {
    const cols = W < 520 ? 2 : 3;
    return { layout: cols === 3 ? '3x2' : '2x3', cols, tileWidth: Math.floor((W - GAP * (cols - 1)) / cols) };
  }
  const c3 = Math.min((W - GAP * 2) / 3, ((H - GAP) / 2) * ASPECT);
  const c2 = Math.min((W - GAP) / 2, ((H - GAP * 2) / 3) * ASPECT);
  return c3 >= c2 * 0.97 ? { layout: '3x2', cols: 3, tileWidth: Math.floor(c3) } : { layout: '2x3', cols: 2, tileWidth: Math.floor(c2) };
}

interface Props {
  cameras: CameraSlot[];
  boxes: readonly BoxView[];
  selectedKey: string | null;
  focusCamera: string | null;
  names: boolean;
  frameNumber: number;
  onSelect: (key: string) => void;
  onFocus: (channel: string) => void;
  onExpand: (channel: string) => void;
  fit?: 'width';
  label: string;
}

export function CameraGrid({ cameras, boxes, selectedKey, focusCamera, names, frameNumber, onSelect, onFocus, onExpand, fit, label }: Props) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const flow = useFlowLayout();
  const pick = chooseLayout(size.width, size.height, { fit, flow });
  return (
    <div ref={ref} className="camgrid" data-layout={pick.layout} data-fit={fit} role="group" aria-label={label}
      style={{ gridTemplateColumns: size.width > 0 ? `repeat(${pick.cols}, ${Math.max(40, pick.tileWidth)}px)` : `repeat(${pick.cols}, minmax(0, 1fr))` }}>
      {cameras.map((slot) => (
        <CameraTile key={slot.channel} slot={slot} boxes={boxes} selectedKey={selectedKey} onSelect={onSelect} names={names} frameNumber={frameNumber}
          current={focusCamera === slot.channel} onFocus={() => onFocus(slot.channel)} onExpand={() => onExpand(slot.channel)} />
      ))}
    </div>
  );
}
