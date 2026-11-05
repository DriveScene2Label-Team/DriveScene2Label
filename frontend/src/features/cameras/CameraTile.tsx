import { memo, useMemo } from 'react';
import type { BoxView } from '@/api/models';
import { Icon } from '@/components/Icon';
import type { CameraSlot } from '@/features/frames/useFrameBundle';
import { useElementSize } from '@/hooks/useElementSize';
import { containFit } from '@/lib/geometry/fit';
import { CameraGlyph } from './CameraGlyph';
import { CameraOverlay, projectAll } from './CameraOverlay';
import { cameraKo } from './cameraMeta';

const OVERLAY_NOTE: Record<string, string> = {
  'no-calibration': '보정값이 없어 박스를 표시할 수 없어요',
  'no-pose': '차량 자세(pose)가 없어 박스를 표시할 수 없어요',
  'no-intrinsic': '카메라 내부 파라미터가 없어 박스를 표시할 수 없어요',
  invalid: '보정값이 올바르지 않아 박스를 표시할 수 없어요',
};

export interface MediaProps {
  slot: CameraSlot;
  boxes: readonly BoxView[];
  selectedKey: string | null;
  onSelect?: (key: string) => void;
  names: boolean;
  /** 1-based frame number, for the "no image in this frame" message. */
  frameNumber: number;
}

/** JPG keyframe of one camera at one sample with its projected boxes. Used by tiles and the quick look. */
export function CameraMedia({ slot, boxes, selectedKey, onSelect, names, frameNumber }: MediaProps) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const { file, image, camera, overlayIssue } = slot;
  const ego = file?.vehicle ?? null;
  const items = useMemo(() => projectAll(camera, boxes, ego), [camera, boxes, ego]);
  if (!file) {
    return (
      <div className="cam-state cam-state--missing" data-state="missing">
        <Icon name="camoff" />
        <b>이 프레임에 카메라 이미지가 없어요</b>
        <span className="mono">{slot.channel}, 프레임 {frameNumber}</span>
      </div>
    );
  }
  if (!image || image.status === 'loading') return <div className="cam-state cam-state--loading" data-state="loading" aria-label="이미지 불러오는 중"><span>불러오는 중</span></div>;
  if (image.status === 'error') {
    const msg = image.error === 'missing' ? '서버에 이미지 파일이 없어요' : image.error === 'decode' ? '이미지를 읽을 수 없어요' : '이미지를 내려받지 못했어요';
    return (
      <div className="cam-state cam-state--error" data-state="error">
        <Icon name="warn" />
        <b>{msg}</b>
        <span className="mono">{file.channel}</span>
      </div>
    );
  }
  const fit = containFit(file.width, file.height, size.width, size.height);
  return (
    <div className="cam-media" ref={ref} data-state="ready" data-sample-data={file.token}>
      <img src={image.src ?? undefined} alt={`${cameraKo(file.channel)} 카메라 (${file.channel})`} draggable={false} />
      {camera && fit && (
        <CameraOverlay items={items} width={file.width} height={file.height} scale={fit.scale} selectedKey={selectedKey} onSelect={onSelect}
          names={names} compact={size.width < 300} />
      )}
      {overlayIssue && overlayIssue !== 'loading' && boxes.length > 0 && <span className="cam-note">{OVERLAY_NOTE[overlayIssue]}</span>}
    </div>
  );
}

interface TileProps extends MediaProps {
  current: boolean;
  onFocus: () => void;
  onExpand: () => void;
}

export const CameraTile = memo(function CameraTile({ current, onFocus, onExpand, onSelect, ...media }: TileProps) {
  const ch = media.slot.channel;
  const select = onSelect ? (k: string) => { onFocus(); onSelect(k); } : undefined;
  return (
    <div className={current ? 'cam cam-tile is-current' : 'cam cam-tile'} style={{ gridArea: areaOf(ch) }} data-channel={ch}
      onClick={onFocus} onDoubleClick={onExpand}>
      <CameraMedia {...media} onSelect={select} />
      <div className="cam-label"><CameraGlyph channel={ch} /><span>{cameraKo(ch)}</span><span className="ch">{ch}</span></div>
      <button type="button" className="cam-zoom" onClick={(e) => { e.stopPropagation(); onExpand(); }} onDoubleClick={(e) => e.stopPropagation()}
        aria-label={`${cameraKo(ch)} ${ch} 크게 보기`} title="크게 보기 (더블클릭)">
        <Icon name="expand" />
      </button>
    </div>
  );
});

function areaOf(channel: string): string {
  return ({ CAM_FRONT_LEFT: 'fl', CAM_FRONT: 'f', CAM_FRONT_RIGHT: 'fr', CAM_BACK_LEFT: 'bl', CAM_BACK: 'b', CAM_BACK_RIGHT: 'br' } as Record<string, string>)[channel] ?? 'auto';
}
