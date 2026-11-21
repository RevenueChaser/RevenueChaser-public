import { describe, expect, it } from 'vitest';

import { hashTicker, markIsATile, MAX_MARK_ASPECT, monogramLetters, monogramTint, MONOGRAM_TINTS, TILE_PX } from './monogram';

/** Contract §9.1: the monogram is the fallback and it must look finished — offline, deterministic, no request. */
describe('the symbol tile fallback', () => {
  it('is 26 px at every row height, as avo set it', () => {
    expect(TILE_PX).toBe(26);
  });

  it('gives the same tint for the same ticker, every time', () => {
    expect(monogramTint('AAPL')).toBe(monogramTint('AAPL'));
    expect(hashTicker('AAPL')).toBe(hashTicker('aapl'));
    expect(MONOGRAM_TINTS).toContain(monogramTint('AAPL'));
  });

  it('names only tokens the token file defines, because --c1 … --c6 are not there yet (contract §2.3)', () => {
    expect(MONOGRAM_TINTS.some((token) => /^--c[1-6]$/.test(token))).toBe(false);
  });

  it('spreads instruments over the tints rather than giving everything one', () => {
    const tickers = ['AAPL', 'MSFT', 'SPY', 'ISRG', 'CDNS', 'QQQ', 'XLK', 'IWM', 'NVDA', 'TSLA', 'AMZN', 'META'];
    expect(new Set(tickers.map(monogramTint)).size).toBeGreaterThanOrEqual(3);
  });

  it('takes its letters from the ticker and drops a class suffix', () => {
    expect(monogramLetters('AAPL')).toBe('AA');
    expect(monogramLetters('BRK.B')).toBe('BR');
    expect(monogramLetters('F')).toBe('F');
    expect(monogramLetters('')).toBe('?');
    expect(monogramLetters('---')).toBe('?');
  });
});

/** Contract §9.1: "A mark whose trimmed aspect ratio is wider than 2.2 : 1 is rejected and the row falls back
 * to its monogram, rather than printing a smear." The three wordmarks were measured on 21 Nov 2026. */
describe('a wordmark is not a tile', () => {
  it('rejects the measured wordmarks', () => {
    // ISRG, CDNS and SPY came back as horizontal wordmarks, 96 × 19 px after trimming.
    expect(markIsATile(96, 19)).toBe(false);
  });

  it('accepts a square or near-square mark', () => {
    expect(markIsATile(128, 128)).toBe(true);
    expect(markIsATile(200, 100)).toBe(true);
  });

  it('cuts exactly at the ratio the contract states', () => {
    expect(MAX_MARK_ASPECT).toBe(2.2);
    expect(markIsATile(22, 10)).toBe(true);
    expect(markIsATile(23, 10)).toBe(false);
  });

  it('rejects a mark with no size rather than dividing by zero', () => {
    expect(markIsATile(0, 0)).toBe(false);
    expect(markIsATile(96, 0)).toBe(false);
  });
});
