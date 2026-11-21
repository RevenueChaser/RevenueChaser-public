/** Every string a v2 screen prints, from contract §3 and §7. Pure functions, so the rules are testable.
 *
 * English, every string (contract §3). Turkish is only what Claude writes to avo, never what a screen shows.
 */
import type { SortDirection, Value } from '../board/envelope';

/** A currency is its symbol, not its code, and it is said once (contract §3). */
export const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  TRY: '₺',
  // The other dollars carry the same glyph. They are here so that `currencyLabel` can see the clash at all:
  // without them a CAD column would print the bare code and the `US$` / `C$` rule would never fire.
  CAD: '$',
  AUD: '$',
  NZD: '$',
  HKD: '$',
  SGD: '$',
};

/** Two currencies sharing one symbol in one view need their code (contract §3): `US$` / `C$`. */
const SHARED_SYMBOL: Record<string, string[]> = { $: ['USD', 'CAD', 'AUD', 'NZD', 'HKD', 'SGD'] };

export function currencySymbol(code: string): string {
  return CURRENCY_SYMBOLS[code.toUpperCase()] ?? code.toUpperCase();
}

/** The label for a currency in a view: its symbol alone, or a disambiguated code where two share one. */
export function currencyLabel(code: string, alsoInView: readonly string[] = []): string {
  const upper = code.toUpperCase();
  const symbol = currencySymbol(upper);
  const sharers = SHARED_SYMBOL[symbol] ?? [];
  const clash = alsoInView.some((other) => other.toUpperCase() !== upper && sharers.includes(other.toUpperCase()));
  if (!clash) return symbol;
  return upper === 'USD' ? 'US$' : `${upper.slice(0, 1)}${symbol}`;
}

/** A missing value leaves its cell empty and shows "—"; it never becomes a zero (contract §11). */
export const MISSING = '—';

export function isMissing(value: unknown): boolean {
  return value === null || value === undefined || value === '' || (typeof value === 'number' && !Number.isFinite(value));
}

/** A plain number with the precision the column asks for, grouped, tabular everywhere by CSS. */
export function num(value: Value, precision = 0): string {
  if (isMissing(value)) return MISSING;
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return MISSING;
  return n.toLocaleString('en-US', { minimumFractionDigits: precision, maximumFractionDigits: precision });
}

/** A compact figure: `$1.2B`. The symbol comes before the figure, once (contract §3). */
export function compact(value: Value, symbol = ''): string {
  if (isMissing(value)) return MISSING;
  const n = Number(value);
  if (!Number.isFinite(n)) return MISSING;
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  const units: Array<[number, string]> = [
    [1e12, 'T'],
    [1e9, 'B'],
    [1e6, 'M'],
    [1e3, 'K'],
  ];
  for (const [size, suffix] of units) {
    if (abs >= size) {
      const scaled = abs / size;
      const digits = scaled >= 100 ? 0 : 1;
      return `${sign}${symbol}${scaled.toFixed(digits)}${suffix}`;
    }
  }
  return `${sign}${symbol}${abs.toFixed(abs >= 100 ? 0 : 2)}`;
}

/** A signed percentage, which is how every change is written. */
export function pct(value: Value, precision = 2): string {
  if (isMissing(value)) return MISSING;
  const n = Number(value);
  if (!Number.isFinite(n)) return MISSING;
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(precision)}%`;
}

/** A price keeps the precision its market quotes (contract §3): under 1 is four places, otherwise two. */
export function price(value: Value, symbol = '', precision?: number): string {
  if (isMissing(value)) return MISSING;
  const n = Number(value);
  if (!Number.isFinite(n)) return MISSING;
  const digits = precision ?? (Math.abs(n) < 1 ? 4 : 2);
  return `${symbol}${n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

/** The sign a value carries, which is the only thing that picks `--pos` or `--neg`. */
export function signTone(value: Value): 'pos' | 'neg' | 'neutral' {
  if (isMissing(value)) return 'neutral';
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return 'neutral';
  return n > 0 ? 'pos' : 'neg';
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** `44m ago`, in English, for the panel footer and the freshness dot (contract §3, §7). */
export function age(asofMs: number | null, nowMs: number): string {
  if (asofMs === null || !Number.isFinite(asofMs)) return 'as-of unknown';
  const delta = nowMs - asofMs;
  if (delta < 0) return 'just now';
  if (delta < MINUTE) return 'just now';
  if (delta < HOUR) return `${Math.floor(delta / MINUTE)}m ago`;
  if (delta < DAY) return `${Math.floor(delta / HOUR)}h ago`;
  return `${Math.floor(delta / DAY)}d ago`;
}

/** Amsterdam is the one clock a v2 screen shows (contract §7). */
export function amsterdamTime(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return 'unknown';
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Amsterdam',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(ms));
}

export function parseAsof(asof: string | null): number | null {
  if (!asof) return null;
  const ms = Date.parse(asof);
  return Number.isFinite(ms) ? ms : null;
}

/** `source · as of 23:36 · 44m ago · build 1f2c9ab` — contract §7, in that exact order. */
export function footerLine(spec: { source: string; asof: string | null; nowMs: number; build: string }): string {
  const ms = parseAsof(spec.asof);
  return [
    spec.source,
    `as of ${amsterdamTime(ms)}`,
    age(ms, spec.nowMs),
    spec.build,
  ].join(' · ');
}

/** A long value is written `figure · detail`, at most 15 characters per part (contract §11). */
export const PART_LIMIT = 15;

export function clampPart(text: string, limit = PART_LIMIT): string {
  return text.length <= limit ? text : `${text.slice(0, limit - 1)}…`;
}

/** A row whose value in the sorted column is missing sinks to the bottom whichever way it points (§11). */
export function compareValues(a: Value, b: Value, direction: SortDirection): number {
  const aMissing = isMissing(a);
  const bMissing = isMissing(b);
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;
  const an = typeof a === 'number' ? a : Number(a);
  const bn = typeof b === 'number' ? b : Number(b);
  const numeric = Number.isFinite(an) && Number.isFinite(bn);
  const order = numeric ? Math.sign(an - bn) : String(a).localeCompare(String(b), 'en');
  return direction === 'asc' ? order : -order;
}

/** The first tap sorts descending, the second reverses (contract §11). */
export function nextSort(
  current: { key: string; direction: SortDirection } | null,
  key: string,
): { key: string; direction: SortDirection } {
  if (!current || current.key !== key) return { key, direction: 'desc' };
  return { key, direction: current.direction === 'desc' ? 'asc' : 'desc' };
}

/** Only the active column carries a caret, pointing the way the values run (contract §11). */
export function caretFor(
  current: { key: string; direction: SortDirection } | null,
  key: string,
): '▾' | '▴' | '' {
  if (!current || current.key !== key) return '';
  return current.direction === 'desc' ? '▾' : '▴';
}
