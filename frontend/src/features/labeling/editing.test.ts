import { describe, expect, it } from 'vitest';
import { changeBox, invalidGeometry, newBox, rotateBox } from './editing';
import type { LabelData } from '@/api/labels';

describe('label edits', () => {
  it('edits a copy without changing the imported source or other frames', () => {
    const original: LabelData = { coordinate_frame: 'WORLD', results: { frame: [newBox('frame')], empty: [] } };
    const edited = changeBox(original, 'frame', 0, (box) => { box.detection_name = 'truck'; box.translation[0] = 5; });
    expect(original.results.frame![0]!.detection_name).toBe('car');
    expect(edited.results.frame![0]!.translation[0]).toBe(5);
    expect(edited.results.empty).toEqual([]);
  });
  it('rotates a unit quaternion without losing roll and pitch', () => {
    const box = newBox('frame'); box.rotation = [Math.SQRT1_2, Math.SQRT1_2, 0, 0];
    rotateBox(box, 90);
    expect(box.rotation[0]).toBeCloseTo(0.5); expect(box.rotation[1]).toBeCloseTo(0.5);
    expect(box.rotation[2]).toBeCloseTo(0.5); expect(box.rotation[3]).toBeCloseTo(0.5);
    expect(Math.hypot(...box.rotation)).toBeCloseTo(1);
  });
  it('blocks invalid dimensions and non-unit rotations', () => {
    const data: LabelData = { coordinate_frame: 'WORLD', results: { frame: [newBox('frame')] } };
    expect(invalidGeometry(data)).toBe(false);
    data.results.frame![0]!.size[0] = 0; expect(invalidGeometry(data)).toBe(true);
    data.results.frame![0]!.size[0] = 2; data.results.frame![0]!.rotation = [0, 0, 0, 0];
    expect(invalidGeometry(data)).toBe(true);
  });
});
