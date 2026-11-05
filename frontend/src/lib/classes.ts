import type { ClassMode } from '@/api/dto';

/**
 * nuScenes category → VESPA comparison class for each classMode.
 *
 * Source: VESPA upstream `assets/class_mapping/{1,3,8}class.yaml`, `mapping_nuscenes`, commit
 * acb2b6e8683363795528f049fe0444ef9f3efdb9 (the commit the AI image pins). Copied verbatim, including the
 * upstream choices that differ from intuition: 3class maps motorcycle → bicycle, 1class maps pedestrians to "vehicle"
 * (VESPA's single generic class). `null` = upstream marks the category as not evaluated.
 *
 * The original GT category is always kept and shown; this table only adds the comparison class.
 * A category missing here or mapped to null is shown as "비교 분류 없음" — never coerced to vehicle.
 */
const NUSC_8: Record<string, string | null> = {
  animal: null,
  'human.pedestrian.adult': 'pedestrian',
  'human.pedestrian.child': 'pedestrian',
  'human.pedestrian.construction_worker': 'pedestrian',
  'human.pedestrian.personal_mobility': null,
  'human.pedestrian.police_officer': 'pedestrian',
  'human.pedestrian.stroller': null,
  'human.pedestrian.wheelchair': null,
  'movable_object.barrier': null,
  'movable_object.debris': null,
  'movable_object.pushable_pullable': null,
  'movable_object.trafficcone': null,
  'static_object.bicycle_rack': null,
  'vehicle.bicycle': 'bicycle',
  'vehicle.bus.bendy': 'bus',
  'vehicle.bus.rigid': 'bus',
  'vehicle.car': 'car',
  'vehicle.construction': 'construction_vehicle',
  'vehicle.emergency.ambulance': null,
  'vehicle.emergency.police': null,
  'vehicle.motorcycle': 'motorcycle',
  'vehicle.trailer': 'trailer',
  'vehicle.truck': 'truck',
};

const FROM_8: Record<1 | 3, Record<string, string>> = {
  3: { car: 'vehicle', truck: 'vehicle', bus: 'vehicle', trailer: 'vehicle', construction_vehicle: 'vehicle', pedestrian: 'pedestrian', motorcycle: 'bicycle', bicycle: 'bicycle' },
  1: { car: 'vehicle', truck: 'vehicle', bus: 'vehicle', trailer: 'vehicle', construction_vehicle: 'vehicle', pedestrian: 'vehicle', motorcycle: 'vehicle', bicycle: 'vehicle' },
};

export const CLASS_MODES: Record<ClassMode, readonly string[]> = {
  1: ['vehicle'],
  3: ['vehicle', 'pedestrian', 'bicycle'],
  8: ['car', 'truck', 'bus', 'trailer', 'construction_vehicle', 'pedestrian', 'motorcycle', 'bicycle'],
};


export function isClassMode(n: unknown): n is ClassMode {
  return n === 1 || n === 3 || n === 8;
}

/** Comparison class of an original nuScenes category under a classMode, or null (unmapped / unknown). */
export function comparisonClass(categoryName: string | null | undefined, mode: ClassMode): string | null {
  if (!categoryName) return null;
  const eight = NUSC_8[categoryName];
  if (!eight) return null;
  return mode === 8 ? eight : FROM_8[mode][eight] ?? null;
}

export function classModeFromMapping(mappingName: string | null | undefined): ClassMode | null {
  const n = mappingName ? Number.parseInt(mappingName, 10) : NaN;
  return isClassMode(n) ? n : null;
}

/** Classes a box can be renamed to. Must match the server list (LabelClasses.LABELS). */
export const LABEL_OPTIONS = ['car', 'truck', 'bus', 'trailer', 'construction_vehicle', 'pedestrian', 'motorcycle', 'bicycle', 'vehicle'] as const;

/**
 * Original display class of a GT category: the 8class comparison class, or the category itself when VESPA does not
 * evaluate it (never coerced to "vehicle"). Same rule as the server's LabelClasses.gtBase.
 */
export function gtBaseClass(categoryName: string | null | undefined): string {
  if (!categoryName) return '클래스 정보 없음';
  return comparisonClass(categoryName, 8) ?? categoryName;
}
