/** Contract §10: series colour is a fixed order, never a cycle — and the categorical ramp does not exist yet.
 *
 * `--c1 … --c6` are decided in the design system's `DESIGN.md` §4 but absent from `ref/design-system/tokens.css`,
 * and `src/theme/tokens.test.ts` fails any `var()` the token file does not define. So a **categorical** chart is
 * not drawn in v2 yet (contract §2.3, §14): this module refuses it in words rather than cycling a hue, and the
 * day those six tokens land, `CATEGORICAL_TOKENS` is filled and `seriesTokens` needs no other change.
 */

/** One or two series: `--data-1` then `--data-2` (contract §10). */
export const SERIES_TOKENS = ['--data-1', '--data-2'] as const;

/** The categorical ramp, in the order `DESIGN.md` §4 validated. Empty until the tokens exist (contract §14). */
export const CATEGORICAL_TOKENS: readonly string[] = [];

export class CategoricalChartBlocked extends Error {
  constructor(count: number) {
    super(
      `A chart of ${count} series needs the categorical ramp --c1 … --c6, which ` +
        'ref/design-system/tokens.css does not define yet (design contract §2.3 and §14). ' +
        'Use one or two series, or small multiples with one series each, until those tokens land.',
    );
    this.name = 'CategoricalChartBlocked';
  }
}

/** The token per series, in order. Three or more series throws, because the ramp is not there to draw them. */
export function seriesTokens(count: number): string[] {
  if (count <= 0) return [];
  if (count <= SERIES_TOKENS.length) return SERIES_TOKENS.slice(0, count);
  if (CATEGORICAL_TOKENS.length >= count) return CATEGORICAL_TOKENS.slice(0, count);
  throw new CategoricalChartBlocked(count);
}

/** Contract §10: a seventh category is "Other", never a generated hue. */
export const OTHER_LABEL = 'Other';

export function foldToOther<T>(
  items: readonly T[],
  limit: number,
  fold: (rest: readonly T[]) => T,
): T[] {
  if (items.length <= limit) return [...items];
  return [...items.slice(0, limit - 1), fold(items.slice(limit - 1))];
}
