import { describe, expect, it } from 'vitest';
import { matchLevel, matchTooltip } from './SceneCard';

describe('match score bands on search cards', () => {
  it('splits at 80 and 50 (docs/search-match-score.md)', () => {
    expect([100, 80, 79, 50, 49, 0].map((n) => matchLevel(n).label)).toEqual(['잘 맞음', '잘 맞음', '관련 있음', '관련 있음', '약함', '약함']);
    expect(matchLevel(80).level).toBe('good');
    expect(matchLevel(49).level).toBe('weak');
  });

  it('tooltip keeps the raw cosine, says it is not a probability and names the bands', () => {
    const tip = matchTooltip(0.2138, 69);
    expect(tip).toContain('원래 코사인 유사도 0.214');
    expect(tip).toContain('확률이 아니에요');
    expect(tip).toContain('80점 이상 잘 맞음');
    expect(tip).not.toMatch(/%/);
  });
});
