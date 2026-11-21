/** The components of design contract §9, by the names `v2/parity.json` holds. Step 8 builds this list.
 *
 * `v2/web/src/components/parity.test.ts` reads `v2/parity.json` and fails a component the contract names that
 * this barrel does not export, and a row whose `web_status` says `built` without an export here. That is the
 * rule over source behaviour, not over a list kept inside the test.
 */
export { Shell, AppBar, CommandBox, BoardTabs, BoardMenu, DocumentTabs, ScreenToolbar, StatusLine, DetailRail, TOOLBAR_ACTIONS } from './shell';
export { Panel, PanelFooter, Tile, JudgementCard, Legend, FilterBar } from './panel';
export { DataTable, RowCard, cellText, sortValue } from './table';
export { SortableHeader, SymbolTile, WatchListMenu, PriceStack, RangeBar, HeatCell, Sparkline } from './cells';
export { ChartBlock } from './chart';
export {
  Chip,
  Badge,
  DeltaChip,
  Notice,
  Banner,
  SkeletonRows,
  NextStepCard,
  Dialog,
  UnsavedDialog,
  EstimateGate,
  SegmentedControl,
  AskBubble,
} from './primitives';
export { ThemeSwitch } from './theme-switch';
export { WidgetCatalogue, SettingsRail, FormatPreview } from './catalogue';
export { monogramLetters, monogramTint, markIsATile, hashTicker, MAX_MARK_ASPECT, TILE_PX } from './monogram';
export { seriesTokens, foldToOther, CategoricalChartBlocked, SERIES_TOKENS, CATEGORICAL_TOKENS, OTHER_LABEL } from './series';
