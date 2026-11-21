/** The frame's own demonstration rows. **Sample figures, and every screen that shows them says so.**
 *
 * Design contract §12: a screen that shows sample or stale data says so in a banner rather than looking live,
 * and a mock is rendered against real rows "except where there is no data behind the screen yet, which the PR
 * states". Step 8 is that case: the first board arrives at step 9 (Settings), so the frame is demonstrated with
 * the rows below and the panel carries the `sample` banner. Nothing here is a measurement, and no private datum
 * — no account id, balance or position — appears anywhere in this file (contract §12).
 */
import type { Layout } from '../board/envelope';

export const SAMPLE_BUILD = 'build 0000000';

export const SAMPLE_LAYOUT: Layout = {
  layout_version: 1,
  title: 'Frame',
  scope: 'STEP 8',
  source: 'sample',
  subsetNote: 'Sample rows, not the whole market — the first real board arrives with step 9.',
  panels: [
    {
      id: 'quotes',
      title: 'Quotes',
      scope: 'SAMPLE',
      tone: 'sky',
      description: 'One row per instrument, with the price and its change over one day and one week.',
      honestScope: 'Sample rows written into the frame, not a board: no provider was read.',
      state: 'sample',
      segmented: { options: ['1D', '1W', '1M', 'YTD'], selected: '1D' },
      body: {
        kind: 'table',
        period: 'sample',
        sort: { key: 'mcap', direction: 'desc' },
        columns: [
          { key: 'name', label: 'Name', kind: 'text', detailKey: 'exchange' },
          { key: 'quote', label: 'Price', kind: 'price', symbol: '$' },
          { key: 'mcap', label: 'Market cap', kind: 'currency', symbol: '$' },
          { key: 'volume', label: 'Volume', kind: 'number' },
          { key: 'range', label: '52-week', kind: 'text', sortable: false },
        ],
        rows: [
          {
            id: 'aapl',
            symbol: 'AAPL',
            cells: {
              name: 'Apple',
              exchange: 'NASDAQ',
              quote: { price: 184.23, d1: 0.84, w1: -1.21 },
              mcap: 2_870_000_000_000,
              volume: 54_120_000,
              range: '164 — 199',
            },
          },
          {
            id: 'msft',
            symbol: 'MSFT',
            cells: {
              name: 'Microsoft',
              exchange: 'NASDAQ',
              quote: { price: 412.06, d1: -0.32, w1: 2.04 },
              mcap: 3_060_000_000_000,
              volume: 21_880_000,
              range: '362 — 433',
            },
          },
          {
            id: 'spy',
            symbol: 'SPY',
            etf: true,
            cells: {
              name: 'SPDR S&P 500',
              exchange: 'NYSE ARCA',
              quote: { price: 551.4, d1: 0.21, w1: 0.96 },
              mcap: 540_000_000_000,
              volume: 72_400_000,
              range: '472 — 566',
            },
          },
          {
            id: 'isrg',
            symbol: 'ISRG',
            // A row with a missing value: it keeps its place and shows "—" (contract §11).
            partial: ['volume'],
            cells: {
              name: 'Intuitive Surgical',
              exchange: 'NASDAQ',
              quote: { price: 398.11, d1: 1.42, w1: null },
              mcap: 140_000_000_000,
              volume: null,
              range: '268 — 412',
            },
          },
        ],
      },
    },
    {
      id: 'figures',
      title: 'Figures',
      tone: 'neutral',
      description: 'The four tiles a board carries above its tables, each with its own comparison line.',
      honestScope: 'Sample figures; a line under a figure is data, never a description.',
      state: 'sample',
      body: {
        kind: 'tiles',
        tiles: [
          { id: 'rows', label: 'Rows', value: '4', comparison: 'in this sample layout', sparkline: [2, 3, 3, 4, 4] },
          { id: 'boards', label: 'Boards wired', value: '0', comparison: 'the first lands at step 9' },
          { id: 'states', label: 'States built', value: '10', delta: { value: 100, label: 'of the table' } },
          { id: 'widths', label: 'Widths checked', value: '2', comparison: '1187 and 1884 px, light and dark' },
        ],
      },
    },
    {
      id: 'series',
      title: 'Two series',
      tone: 'amber',
      description: 'A two-series line chart: one y-axis, a named legend, and the rule that produced it.',
      honestScope: 'Sample series. A categorical chart is blocked until --c1 … --c6 reach the token file.',
      state: 'sample',
      body: {
        kind: 'chart',
        xKind: 'value',
        yLabel: 'Index',
        axis: 'fit',
        fixedRange: [90, 130],
        method: 'Both lines are a sample ramp, drawn to show the two-series colour order and the one y-axis rule.',
        series: [
          {
            name: 'First series',
            points: [
              [0, 100],
              [1, 104],
              [2, 103],
              [3, 109],
              [4, 112],
              [5, 118],
            ],
          },
          {
            name: 'Second series',
            points: [
              [0, 100],
              [1, 99],
              [2, 102],
              [3, 101],
              [4, 106],
              [5, 104],
            ],
            partialFrom: 4,
          },
        ],
      },
    },
    {
      id: 'verdict',
      title: 'Judgement',
      tone: 'pos',
      description: 'A derived judgement: one verdict word, three metric lines, and the yardstick behind it.',
      honestScope: 'Sample judgement. No score is shown without the rule that produced it.',
      state: 'sample',
      body: {
        kind: 'judgement',
        verdict: 'READY',
        tone: 'pos',
        metrics: [
          { label: 'Components', value: '39 of 39' },
          { label: 'States', value: '10 of 10' },
          { label: 'Widths', value: '1187 · 1884' },
        ],
        rationale: 'The yardstick is design contract §9: every component of the list exists and nothing else was added.',
      },
    },
  ],
  rail: {
    items: [
      { label: 'Freshness', value: 'sample', tone: 'amber' },
      { label: 'Running jobs', value: 'none' },
      { label: "Today's alerts", value: '0' },
      { label: 'Next earnings', value: '—' },
      { label: 'Market hours', value: 'closed' },
    ],
  },
};

/** The boards the frame offers. The real list follows the board list v2 ends with (contract §14), so these are
 * the groups avo fixed for the phone's bottom bar (§5.2) and nothing is claimed to be built. */
export const SAMPLE_BOARDS = [
  { key: 'welcome', name: 'Welcome' },
  { key: 'watchlists', name: 'Watch lists' },
  { key: 'news', name: 'News', group: 'Research' },
  { key: 'earnings-radar', name: 'Earnings Radar', group: 'Research' },
  { key: 'spx-gamma', name: 'SPX Gamma', group: 'Research' },
  { key: 'implied-probability', name: 'Implied Probability', group: 'Research' },
  { key: 'financials', name: 'Financials', group: 'Research' },
  { key: 'sector-rotation', name: 'Sector Rotation', group: 'Screeners' },
  { key: 'asymmetric-growth', name: 'Asymmetric Growth', group: 'Screeners' },
  { key: 'swing-potential', name: 'Swing Potential', group: 'Screeners' },
  { key: 'fundamentals', name: 'Fundamentals', group: 'Screeners' },
  { key: 'hit-rate', name: 'Hit Rate', group: 'Screeners' },
  { key: 'classification', name: 'Classification', group: 'More' },
  { key: 'ownership', name: 'Ownership', group: 'More' },
  { key: 'ops', name: 'Ops', group: 'More' },
] as const;

export const SAMPLE_WIDGETS = [
  {
    id: 'quotes',
    name: 'Quotes',
    category: 'Market',
    description: 'One row per instrument, with the price and its change over one day and one week.',
    honestScope: 'Hourly data: the price is the last hourly read, not a live quote.',
  },
  {
    id: 'figures',
    name: 'Figures',
    category: 'Market',
    description: 'Four tiles above a board, each with its own comparison line.',
    honestScope: 'Each tile states its own period; none of them is a composite score.',
  },
  {
    id: 'series',
    name: 'Two series',
    category: 'Charts',
    description: 'A two-series line chart on one y-axis, with a named legend.',
    honestScope: 'Two series only — the categorical ramp is not in the token file yet.',
  },
  {
    id: 'verdict',
    name: 'Judgement',
    category: 'Judgements',
    description: 'One verdict word over three metric lines, with its yardstick named.',
    honestScope: 'A judgement appears only when every input it names is in.',
  },
];

export const SAMPLE_WATCH_LISTS = [
  { id: 'core', name: 'Core', holds: true },
  { id: 'options', name: 'Options watch list', holds: false },
  { id: 'biotech', name: 'Biotech', holds: false },
];

export const SETTINGS_GROUPS = [
  {
    name: 'Shell' as const,
    items: [
      { id: 'theme', label: 'Theme' },
      { id: 'density', label: 'Density' },
      { id: 'boards', label: 'Boards and order' },
    ],
  },
  {
    name: 'Data' as const,
    items: [
      { id: 'formats', label: 'Numbers and currencies' },
      { id: 'sources', label: 'Sources and freshness' },
      { id: 'jobs', label: 'Jobs and schedules' },
    ],
  },
];
