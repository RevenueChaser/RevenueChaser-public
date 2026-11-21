/** The envelope the door serves, and the `layout` description the generic renderers read.
 *
 * `v2/schemas/envelope.schema.json` left `layout` as "null until step 8". This module is that shape: a board
 * says **what to draw** and the renderers here decide **how**, so a board never ships a React component.
 *
 * It is **not** a second JSON Schema file: `v2/tests/test_v2_schemas.py` pins `v2/schemas/` to one schema per
 * board plus the envelope's own, so a `layout.schema.json` there would fail that check. This module is the
 * contract, and the envelope schema's `layout` description points at it.
 *
 * Contract: `v2/design/CONTRACT.md` §7 (the panel's four parts), §10 (the chart contract), §11 (tables).
 */

/** A cell's value. `null` is a missing value and prints "—" in its own place (contract §11). */
export type Value = string | number | null;

/** How a column is read, which decides its alignment and its sort (contract §11). */
export type ColumnKind = 'text' | 'number' | 'percent' | 'currency' | 'date' | 'price';

export type ColumnSpec = {
  key: string;
  /** The header label. A price column's header carries `Price` over `1D | 1W`; that is the renderer's job. */
  label: string;
  kind: ColumnKind;
  /** false for a column nobody would rank by (contract §11: every column a reader would rank by is sortable). */
  sortable?: boolean;
  /** The currency symbol for a `currency` column, said once in the header (contract §3). */
  symbol?: string;
  /** Decimal places for a number, percent or price. */
  precision?: number;
  /** A muted second line under the figure, for a long value written `figure · detail` (contract §11). */
  detailKey?: string;
  /** A mixed-currency column prints its code on every cell (contract §3). */
  codeKey?: string;
  /** Marks this column's cells as partial or stale wherever the row says so. */
  partialKey?: string;
};

/** A price cell: the price, then `1D` and `1W` under it, split by the column's centre line (contract §3). */
export type PriceCell = { price: number | null; d1: number | null; w1: number | null };

/** A row of a table. `_symbol` and `_etf` make the row carry a symbol tile (contract §9.1). */
export type Row = {
  id: string;
  /** A cell is a plain value, or a `PriceCell` where the column stacks the price with `1D` and `1W` (§3). */
  cells: Record<string, Value | PriceCell>;
  symbol?: string;
  etf?: boolean;
  /** Per-cell marks: the key of a cell whose value is partial or stale (contract §8). */
  partial?: string[];
};

export type TableBody = {
  kind: 'table';
  columns: ColumnSpec[];
  rows: Row[];
  /** The period this table is pinned to. Contract §11: one table, one period. */
  period?: string;
  /** The default sort, which the URL may override. */
  sort?: { key: string; direction: SortDirection };
};

export type TileSpec = {
  id: string;
  label: string;
  value: string;
  delta?: { value: number; label?: string };
  comparison?: string;
  sparkline?: number[];
};

export type TileBody = { kind: 'tiles'; tiles: TileSpec[] };

export type SeriesSpec = {
  /** The legend names every series in words (contract §10). */
  name: string;
  points: Array<[number, number | null]>;
  /** A partial series is drawn as partial, never as a finished line (contract §10). */
  partialFrom?: number;
};

export type ChartBody = {
  kind: 'chart';
  /** 'time' draws the as-of rule on the chart; 'value' puts `data_asof` in the method line (contract §10). */
  xKind: 'time' | 'value';
  yLabel: string;
  series: SeriesSpec[];
  /** The full sentence naming the rule that produced the line (contract §10). */
  method: string;
  /** A fixed-axis line chart offers `Fixed | Fit` (contract §10). */
  axis?: 'fixed' | 'fit';
  fixedRange?: [number, number];
};

export type JudgementBody = {
  kind: 'judgement';
  /** One big verdict word. No score without its rule (contract §9). */
  verdict: string;
  tone: Tone;
  metrics: Array<{ label: string; value: string }>;
  /** The rationale names the yardstick. */
  rationale: string;
};

export type PanelBody = TableBody | TileBody | ChartBody | JudgementBody;

export type SegmentedSpec = {
  /** Exclusive, and never a dropdown at five or fewer choices (contract §7). */
  options: string[];
  selected: string;
};

export type PanelSpec = {
  id: string;
  title: string;
  /** Printed after a dot in the header strip: `MARKET INDICES · UNITED STATES` (contract §7). */
  scope?: string;
  tone?: Tone;
  /** The one-sentence description and the honest scope every panel carries (contract §7). */
  description: string;
  honestScope: string;
  segmented?: SegmentedSpec;
  body: PanelBody;
  /** Overrides the board's footer where this panel has its own source or as-of. */
  footer?: Partial<FooterSpec>;
  /** The state this panel is in; `ready` draws its body (contract §8). */
  state?: PanelStateName;
};

export type FooterSpec = {
  /** `source · as of <HH:MM Amsterdam> · <age> · <delay or build id>` (contract §7). */
  source: string;
  asof: string | null;
  /** Milliseconds, so the age is computed here and not written by a board. */
  nowMs: number;
  build: string;
};

export type RailSpec = {
  /** The one fixed rail per board: freshness, running jobs, today's alerts, next earnings, market hours (§6). */
  items: Array<{ label: string; value: string; tone?: Tone }>;
};

export type Layout = {
  layout_version: 1;
  title: string;
  scope: string;
  source: string;
  /** The sentence a board shows above a table when it draws a subset (contract §7). */
  subsetNote?: string;
  panels: PanelSpec[];
  rail?: RailSpec;
};

export type Envelope = {
  schema_version: 1;
  board: string;
  run_id: string;
  data_asof: string | null;
  built_at: string;
  private: boolean;
  renderer: 'generic' | 'bespoke';
  layout: Layout | null;
  data: Record<string, unknown>;
};

export type SortDirection = 'asc' | 'desc';

/** The colour a value carries. A tone is never a hex: it names the token the component reaches for. */
export type Tone = 'neutral' | 'pos' | 'neg' | 'amber' | 'sky';

/** Contract §8's ten rows, by name. `ready` is the eleventh: the body is drawn. */
export type PanelStateName =
  | 'ready'
  | 'loading'
  | 'loading-partial'
  | 'unconfigured'
  | 'no-data'
  | 'sample'
  | 'stale'
  | 'upstream-down'
  | 'gated'
  | 'unsaved'
  | 'refused';
