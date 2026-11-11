import { describe, expect, it } from 'vitest';
import { gtToBox, predictionToBox, toJobResults, toLabelEdit, toSceneInstances } from '@/api/mappers';
import type { PredictionDto } from '@/api/dto';
import { chooseLayout } from '@/features/cameras/CameraGrid';
import { autoRatio } from '@/features/layout/Split';
import { instanceOfKey, objectKey } from '@/features/objects/objectKeys';
import { objectKeyForBoxKey } from '@/features/viewer/recordingMap';
import { gtDto, jobResultsDto } from '@/test/fixtures';
import { gtBaseClass, LABEL_OPTIONS } from './classes';
import { josa } from './edits/labelEdits';

const pred = (over: Partial<PredictionDto> = {}): PredictionDto => ({
  id: 900, sampleToken: 's0', boxIndex: 0, detectionName: 'car', centerX: 1, centerY: 2, centerZ: 0.8, sizeW: 2, sizeL: 4, sizeH: 1.6,
  rotationW: 1, rotationX: 0, rotationY: 0, rotationZ: 0, velocityX: 0, velocityY: 0, detectionScore: 1, attributeName: '', ...over,
});

describe('label edit fields in screen models', () => {
  it('GT keeps the original category and shows the edited class', () => {
    const plain = gtToBox(gtDto(1, { categoryName: 'vehicle.car' }));
    expect([plain.label, plain.baseCls, plain.cls, plain.edited]).toEqual(['vehicle.car', 'car', 'car', false]);
    const edited = gtToBox(gtDto(1, { categoryName: 'vehicle.car', labelOverride: 'truck' }));
    expect([edited.label, edited.baseCls, edited.cls, edited.edited]).toEqual(['vehicle.car', 'car', 'truck', true]);
  });

  it('unmapped or missing categories are never coerced to vehicle', () => {
    expect(gtBaseClass('movable_object.debris')).toBe('movable_object.debris');
    expect(gtBaseClass('movable_object.barrier')).toBe('barrier'); // 8class since vespa-patches/0001
    expect(gtBaseClass(null)).toBe('클래스 정보 없음');
    expect(gtBaseClass('human.pedestrian.child')).toBe('pedestrian');
    expect(LABEL_OPTIONS).toContain('vehicle');
    expect(LABEL_OPTIONS).toEqual(expect.arrayContaining(['barrier', 'traffic_cone']));
  });

  it('predictions keep detectionName; results skip deleted boxes and count edited ones', () => {
    const b = predictionToBox(pred({ labelOverride: 'bus' }), 12, 1);
    expect([b.label, b.cls, b.edited]).toEqual(['car', 'bus', true]);
    const dto = jobResultsDto();
    const r = toJobResults({ ...dto, boxes: [pred({ id: 1, sampleToken: dto.sampleTokens[0]! }), pred({ id: 2, sampleToken: dto.sampleTokens[0]!, labelOverride: 'truck' }), pred({ id: 3, sampleToken: dto.sampleTokens[0]!, deleted: true })] });
    expect([r.boxCount, r.editedCount]).toEqual([2, 1]);
    expect(r.boxesBySample.get(dto.sampleTokens[0]!)?.map((x) => x.id)).toEqual([1, 2]);
  });

  it('scene GT → instance frames index without deleted rows', () => {
    const idx = toSceneInstances([
      gtDto(1, { instanceToken: 'i1', sampleToken: 's0' }), gtDto(2, { instanceToken: 'i1', sampleToken: 's1' }),
      gtDto(3, { instanceToken: 'i2', sampleToken: 's1', deleted: true }),
    ]);
    expect([...idx.get('i1')!]).toEqual(['s0', 's1']);
    expect(idx.has('i2')).toBe(false);
  });

  it('maps label edit DTOs (timestamps, nullable job)', () => {
    const e = toLabelEdit({ id: 5, datasetId: 1, sceneId: 7, jobId: null, targetType: 'ANNOTATION', action: 'RENAME', scope: 'INSTANCE', instanceToken: 'i1', fromLabel: 'car', toLabel: 'truck', targetIds: [1, 2], sampleTokens: ['s0', 's1'], count: 2, createdAt: '2026-11-05T01:02:03Z', revertedAt: null, revertible: true });
    expect([e.createdAt, e.revertedAt, e.count, e.revertible]).toEqual([Date.parse('2026-11-05T01:02:03Z'), null, 2, true]);
  });
});

describe('object keys', () => {
  it('GT = instance (same object every frame), prediction = one box', () => {
    const g = gtToBox(gtDto(3, { instanceToken: 'inst-x', datasetId: 4 }));
    expect(objectKey(g)).toBe('gt:4:inst-x');
    expect(instanceOfKey('gt:4:inst-x')).toBe('inst-x');
    expect(instanceOfKey('pred:12:900')).toBeNull();
    expect(objectKey(predictionToBox(pred(), 12, 1))).toBe('pred:12:900');
  });

  it('Rerun box keys resolve to object keys', () => {
    expect(objectKeyForBoxKey('VESPA:12:1:s0:900', () => undefined)).toBe('pred:12:900');
    expect(objectKeyForBoxKey('GT:1:s0:3', () => ({ instanceToken: 'inst-x', datasetId: 1 }))).toBe('gt:1:inst-x');
    expect(objectKeyForBoxKey('GT:1:s0:3', () => undefined)).toBeNull();
  });
});

describe('layout rules of the design', () => {
  it('chooses 3×2 for wide areas and 2×3 for tall ones; width-fit is always 3×2', () => {
    expect(chooseLayout(1050, 400).layout).toBe('3x2');
    expect(chooseLayout(800, 900).layout).toBe('2x3');
    expect(chooseLayout(500, 2000, { fit: 'width' })).toMatchObject({ layout: '3x2', cols: 3 });
    expect(chooseLayout(480, 300, { flow: true })).toMatchObject({ layout: '2x3', cols: 2 });
  });

  it('auto split ratio fits the cameras and stays within bounds', () => {
    const r = autoRatio(1050, 760, 'stack');
    const tile = (1050 - 24 - 16) / 3;
    expect(r).toBeCloseTo((2 * tile * 9 / 16 + 8 + 12) / (760 - 9), 5);
    expect(autoRatio(1050, 200, 'stack')).toBe(0.72);
    expect(autoRatio(1600, 700, 'side')).toBeGreaterThanOrEqual(0.36);
    expect(autoRatio(5, 5, 'side')).toBe(0.5);
  });
});

describe('Korean particles after latin/digits', () => {
  it('chooses by the last sound', () => {
    expect(josa('car', '을/를')).toBe('car를');
    expect(josa('truck', '으로/로')).toBe('truck으로');
    expect(josa('scene-0061', '과/와')).toBe('scene-0061과');
    expect(josa('scene-0103', '과/와')).toBe('scene-0103과');
    expect(josa('pedestrian', '을/를')).toBe('pedestrian을');
    expect(josa('bicycle', '으로/로')).toBe('bicycle로');
  });
});
