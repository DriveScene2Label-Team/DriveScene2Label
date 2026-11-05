import type { ClassMode } from '@/api/dto';
import type { BoxView } from '@/api/models';
import { comparisonClass } from '@/lib/classes';

/** GT comparison class under a classMode (VESPA mapping) from the original category. Null = 비교 분류 없음. */
export function gtComparisonClass(box: BoxView, mode: ClassMode): string | null {
  return box.source === 'GT' ? comparisonClass(box.label, mode) : box.cls;
}
