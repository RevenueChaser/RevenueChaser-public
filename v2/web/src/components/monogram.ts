/** The symbol tile's fallback, contract §9.1: offline, deterministic, and it must look finished.
 *
 * "The letters come from the ticker and the tint is a deterministic hash over the palette's data colours, so
 * every instrument — an ETF, an index, a name no logo set covers — gets one, offline, with no request."
 */

/** The tints a monogram may take. Token names, never a hex (contract §2). `--c1 … --c6` are not in the token
 * file yet (contract §2.3), so the monogram uses the two data colours and the three state hues, which are. */
export const MONOGRAM_TINTS = ['--data-1', '--data-2', '--sky', '--amber', '--pos', '--neg'] as const;

export type MonogramTint = (typeof MONOGRAM_TINTS)[number];

/** FNV-1a over the ticker: the same name gets the same tint on both surfaces and across reloads. */
export function hashTicker(ticker: string): number {
  let hash = 0x811c9dc5;
  for (const char of ticker.toUpperCase()) {
    hash ^= char.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

export function monogramTint(ticker: string): MonogramTint {
  return MONOGRAM_TINTS[hashTicker(ticker) % MONOGRAM_TINTS.length];
}

/** Two letters where the ticker gives two, one where it does not; a dot and a class suffix are dropped. */
export function monogramLetters(ticker: string): string {
  const core = ticker.toUpperCase().split(/[.\-/]/)[0] ?? '';
  const letters = core.replace(/[^A-Z0-9]/g, '');
  if (letters.length === 0) return '?';
  return letters.slice(0, 2);
}

/** Contract §9.1: a mark whose trimmed aspect ratio is wider than 2.2 : 1 is a wordmark, not a tile. */
export const MAX_MARK_ASPECT = 2.2;

export function markIsATile(width: number, height: number): boolean {
  if (!(width > 0) || !(height > 0)) return false;
  return width / height <= MAX_MARK_ASPECT;
}

/** The tile is 26 px on every row height (avo, 21 Nov 2026 16:52), and its hit area is the row's (contract §9.1). */
export const TILE_PX = 26;
