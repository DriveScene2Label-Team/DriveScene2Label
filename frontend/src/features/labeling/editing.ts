import type { LabelBox, LabelData } from '@/api/labels';

export const EDIT_CLASSES = ['vehicle', 'car', 'truck', 'bus', 'trailer', 'construction_vehicle', 'pedestrian', 'motorcycle', 'bicycle'];

export function changeBox(data: LabelData, frame: string, index: number, update: (box: LabelBox) => void): LabelData {
  const next = structuredClone(data);
  const box = next.results[frame]?.[index];
  if (box) update(box);
  return next;
}

/** Rotate about WORLD Z without discarding the existing roll/pitch. Quaternion order is W/X/Y/Z. */
export function rotateBox(box: LabelBox, degrees: number): void {
  const angle = degrees * Math.PI / 360;
  const cosine = Math.cos(angle), sine = Math.sin(angle);
  const [w, x, y, z] = box.rotation;
  box.rotation = [cosine * w - sine * z, cosine * x - sine * y, cosine * y + sine * x, cosine * z + sine * w];
}

export function newBox(frame: string, center: [number, number, number] = [0, 0, 0]): LabelBox {
  return { sample_token: frame, detection_name: 'car', translation: [...center], size: [2, 4, 1.5], rotation: [1, 0, 0, 0], velocity: [0, 0], detection_score: 1, attribute_name: '' };
}

export function invalidGeometry(data: LabelData): boolean {
  return Object.values(data.results).some((boxes) => boxes.some((box) =>
    [...box.translation, ...box.size, ...box.rotation, ...box.velocity].some((n) => !Number.isFinite(n))
    || box.size.some((n) => n <= 0) || Math.abs(box.rotation.reduce((sum, n) => sum + n * n, 0) - 1) > 0.001));
}
