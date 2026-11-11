import type { ClassMode } from '@/api/dto';
import type { BoxView } from '@/api/models';
import { comparisonClass } from '@/lib/classes';

/** Short tag on the image: source plus class. GT never borrows a prediction's class name. */
export function boxShortLabel(box: BoxView): string {
  if (box.source === 'GT') return box.label ? `GT ${box.label}` : 'GT · 클래스 정보 없음';
  return `예측 ${box.label ?? ''}${box.trackId != null ? ` · T${box.trackId}` : ''}`.trim();
}

/** Class name shown in lists: original category for GT, detectionName for predictions. */
export function boxClassName(box: BoxView): string {
  if (box.source === 'GT') return box.label ?? '클래스 정보 없음';
  return box.label ?? '-';
}

/** GT comparison class under a classMode (VESPA mapping). Null = 비교 분류 없음. */
export function gtComparisonClass(box: BoxView, mode: ClassMode): string | null {
  return box.source === 'GT' ? comparisonClass(box.label, mode) : box.label;
}

/** Colour key for list dots. */
export function boxColorClass(box: BoxView, mode: ClassMode): string | null {
  return box.source === 'GT' ? comparisonClass(box.label, mode) : box.label;
}
