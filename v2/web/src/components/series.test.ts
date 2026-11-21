import { describe, expect, it } from 'vitest';

import { CATEGORICAL_TOKENS, CategoricalChartBlocked, foldToOther, OTHER_LABEL, SERIES_TOKENS, seriesTokens } from './series';

/** Contract §10: series colour is a fixed order, never a cycle — and §2.3/§14: the categorical ramp is not in
 * `ref/design-system/tokens.css` yet, so a categorical chart is **not built**, not worked around. */
describe('the chart series colours', () => {
  it('uses --data-1 then --data-2, in that order', () => {
    expect(SERIES_TOKENS).toEqual(['--data-1', '--data-2']);
    expect(seriesTokens(1)).toEqual(['--data-1']);
    expect(seriesTokens(2)).toEqual(['--data-1', '--data-2']);
    expect(seriesTokens(0)).toEqual([]);
  });

  it('refuses a third series in words, because the ramp does not exist yet', () => {
    expect(CATEGORICAL_TOKENS).toEqual([]);
    expect(() => seriesTokens(3)).toThrow(CategoricalChartBlocked);
    expect(() => seriesTokens(6)).toThrow(/--c1 … --c6/);
    expect(() => seriesTokens(3)).toThrow(/ref\/design-system\/tokens\.css/);
  });

  it('never invents a hue to fill the gap', () => {
    try {
      seriesTokens(4);
      expect.unreachable('a four-series chart must not be drawable');
    } catch (error) {
      expect(error).toBeInstanceOf(CategoricalChartBlocked);
    }
  });

  it('folds a seventh category into "Other" rather than generating one', () => {
    expect(OTHER_LABEL).toBe('Other');
    const items = [1, 2, 3, 4, 5, 6, 7, 8];
    const folded = foldToOther(items, 6, (rest) => rest.reduce((total, value) => total + value, 0));
    expect(folded).toEqual([1, 2, 3, 4, 5, 6 + 7 + 8]);
    expect(foldToOther([1, 2], 6, () => 0)).toEqual([1, 2]);
  });
});
