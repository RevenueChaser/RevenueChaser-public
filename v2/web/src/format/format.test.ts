import { describe, expect, it } from 'vitest';

import {
  age,
  amsterdamTime,
  caretFor,
  clampPart,
  compact,
  compareValues,
  currencyLabel,
  currencySymbol,
  footerLine,
  isMissing,
  MISSING,
  nextSort,
  num,
  pct,
  price,
  signTone,
} from './format';

describe('currency (contract §3: a currency is its symbol, not its code)', () => {
  it('gives the symbol, said once', () => {
    expect(currencySymbol('USD')).toBe('$');
    expect(currencySymbol('EUR')).toBe('€');
    expect(currencySymbol('GBP')).toBe('£');
    expect(currencySymbol('JPY')).toBe('¥');
    expect(currencySymbol('TRY')).toBe('₺');
  });

  it('adds a code only where two currencies share one symbol in the same view', () => {
    expect(currencyLabel('USD')).toBe('$');
    expect(currencyLabel('USD', ['EUR'])).toBe('$');
    expect(currencyLabel('USD', ['CAD'])).toBe('US$');
    expect(currencyLabel('CAD', ['USD'])).toBe('C$');
  });
});

describe('missing values (contract §11: a missing value shows "—", never a zero)', () => {
  it('names every shape of missing', () => {
    expect(isMissing(null)).toBe(true);
    expect(isMissing('')).toBe(true);
    expect(isMissing(Number.NaN)).toBe(true);
    expect(isMissing(0)).toBe(false);
  });

  it('prints the em dash and not a zero', () => {
    expect(num(null)).toBe(MISSING);
    expect(pct(null)).toBe(MISSING);
    expect(price(null, '$')).toBe(MISSING);
    expect(compact(null, '$')).toBe(MISSING);
    expect(num(0)).toBe('0');
    expect(pct(0)).toBe('0.00%');
  });
});

describe('figures', () => {
  it('writes a compact total with the symbol before it, once', () => {
    expect(compact(1_234_567_890, '$')).toBe('$1.2B');
    expect(compact(2_870_000_000_000, '$')).toBe('$2.9T');
    expect(compact(-54_120_000, '$')).toBe('-$54.1M');
    expect(compact(812, '$')).toBe('$812');
  });

  it('signs a change and keeps two places', () => {
    expect(pct(0.84)).toBe('+0.84%');
    expect(pct(-1.21)).toBe('-1.21%');
  });

  it('keeps the precision a market quotes: four places under 1, two above', () => {
    expect(price(184.236, '$')).toBe('$184.24');
    expect(price(0.4821, '$')).toBe('$0.4821');
    expect(price(184.2, '$', 1)).toBe('$184.2');
  });

  it('takes a tone from the sign alone', () => {
    expect(signTone(1)).toBe('pos');
    expect(signTone(-1)).toBe('neg');
    expect(signTone(0)).toBe('neutral');
    expect(signTone(null)).toBe('neutral');
  });
});

describe('the panel footer (contract §7: source · as of · age · delay/build, in that order)', () => {
  const asof = '2026-11-21T22:36:00Z'; // 23:36 Amsterdam
  const now = Date.parse('2026-11-21T23:20:00Z');

  it('prints the four parts in the contract order', () => {
    expect(footerLine({ source: 'WRDS', asof, nowMs: now, build: 'build 1f2c9ab' })).toBe(
      'WRDS · as of 23:36 · 44m ago · build 1f2c9ab',
    );
  });

  it('says the as-of is unknown rather than inventing one', () => {
    expect(footerLine({ source: 'sample', asof: null, nowMs: now, build: 'build 0000000' })).toBe(
      'sample · as of unknown · as-of unknown · build 0000000',
    );
  });

  it('writes an age in English and in the units a reader uses', () => {
    expect(age(now - 30_000, now)).toBe('just now');
    expect(age(now - 44 * 60_000, now)).toBe('44m ago');
    expect(age(now - 5 * 3_600_000, now)).toBe('5h ago');
    expect(age(now - 3 * 86_400_000, now)).toBe('3d ago');
    expect(age(null, now)).toBe('as-of unknown');
  });

  it('shows the Amsterdam clock, not UTC', () => {
    expect(amsterdamTime(Date.parse('2026-11-21T22:36:00Z'))).toBe('23:36');
    // Summer time: the same UTC hour reads two hours later in Amsterdam.
    expect(amsterdamTime(Date.parse('2026-07-21T22:36:00Z'))).toBe('00:36');
  });
});

describe('cells and sorting (contract §11)', () => {
  it('writes a long value as `figure · detail`, at most 15 characters a part', () => {
    expect(clampPart('Intuitive Surgical')).toBe('Intuitive Surg…');
    expect(clampPart('Apple')).toBe('Apple');
  });

  it('sinks a missing value to the bottom whichever way the column points', () => {
    expect(compareValues(null, 5, 'desc')).toBeGreaterThan(0);
    expect(compareValues(null, 5, 'asc')).toBeGreaterThan(0);
    expect(compareValues(5, null, 'desc')).toBeLessThan(0);
    expect(compareValues(5, null, 'asc')).toBeLessThan(0);
    expect(compareValues(null, null, 'asc')).toBe(0);
  });

  it('orders numbers and text the way the direction says', () => {
    expect(compareValues(1, 2, 'asc')).toBeLessThan(0);
    expect(compareValues(1, 2, 'desc')).toBeGreaterThan(0);
    expect(compareValues('Apple', 'Microsoft', 'asc')).toBeLessThan(0);
  });

  it('sorts descending on the first tap and reverses on the second', () => {
    const first = nextSort(null, 'mcap');
    expect(first).toEqual({ key: 'mcap', direction: 'desc' });
    expect(nextSort(first, 'mcap')).toEqual({ key: 'mcap', direction: 'asc' });
    expect(nextSort({ key: 'mcap', direction: 'asc' }, 'mcap')).toEqual({ key: 'mcap', direction: 'desc' });
    // A different column starts again at descending, it does not inherit the direction.
    expect(nextSort({ key: 'mcap', direction: 'asc' }, 'volume')).toEqual({ key: 'volume', direction: 'desc' });
  });

  it('gives a caret to the active column only, pointing the way the values run', () => {
    const sort = { key: 'mcap', direction: 'desc' } as const;
    expect(caretFor(sort, 'mcap')).toBe('▾');
    expect(caretFor({ key: 'mcap', direction: 'asc' }, 'mcap')).toBe('▴');
    expect(caretFor(sort, 'volume')).toBe('');
    expect(caretFor(null, 'mcap')).toBe('');
  });
});
