# Charting

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 16.

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `charting_alerts-menu.png` | https://unusualwhales.com/charting | 21.11.2026 16:09:47 |
| `charting_crosshair-menu.png` | https://unusualwhales.com/charting | 21.11.2026 16:09:38 |
| `charting_group-menu.png` | https://unusualwhales.com/charting | 21.11.2026 16:10:45 |
| `charting_interval-menu.png` | https://unusualwhales.com/charting | 21.11.2026 16:08:58 |
| `charting_line-type-menu.png` | https://unusualwhales.com/charting | 21.11.2026 16:08:58 |
| `charting_markers-menu.png` | https://unusualwhales.com/charting | 21.11.2026 16:09:38 |
| `charting_mode-menu.png` | https://unusualwhales.com/charting | 21.11.2026 16:08:58 |
| `charting_script-editor.jpg` | https://unusualwhales.com/charting | 21.11.2026 16:10:31 |
| `charting_settings-panel.jpg` | https://unusualwhales.com/charting | 21.11.2026 16:09:47 |
| `charting_side-panel.jpg` | https://unusualwhales.com/charting | 21.11.2026 16:09:56 |
| `charting_studies-dialog.jpg` | https://unusualwhales.com/charting | 21.11.2026 16:08:58 |
| `charting_tab-contract-demo.jpg` | https://unusualwhales.com/charting | 21.11.2026 16:10:22 |
| `charting_tab-order-flow-demo.jpg` | https://unusualwhales.com/charting | 21.11.2026 16:10:22 |
| `charting_tab-studies-demo.jpg` | https://unusualwhales.com/charting | 21.11.2026 16:10:22 |
| `charting_top.jpg` | https://unusualwhales.com/charting | 21.11.2026 16:08:42 |
| `charting_views-menu.png` | https://unusualwhales.com/charting | 21.11.2026 16:09:38 |

## Other files in this folder

- `studies-list.md`

## Notes (what the page shows, buttons pressed, nearest API path)

### Charting (/charting) raw notes, second pass — 2026-11-21 ~15:09-15:11Z

- Multi-tab chart workspace. avo's tabs: "AAPL unnamed", "SPY stock demo", "AAPL studies demo", "SPY order flow demo", "SPY contract demo" (Group 1, 5 tabs). "+" new tab and tab X were NOT pressed. Group menu: Group 1 (rename pencil), "+ New group" (not pressed). Back/Forward arrows (ticker & chart mode history).
- Top toolbar: ticker search, Compare (+), Draw, Drawing Filters, Chart tour (i, not started), MODE (Stock Chart, Options Flow, Footprint Chart, TPO Chart), interval (1M 2M 3M 5M 10M 15M 30M 1H 4H 1D 1W 1MO), Line Type (None, Line, Line Solid, Candles, Candles Hollow, Candles Hollow Plain, Candles Solid Plain, Bollinger Bars, Area, Bars, Bars Solid, Dots, Dots Solid, Volume Dots, Volume Dots Solid, ...), Studies (fx), Markers, Views (only "+ Save", not pressed), Crosshair & Info Panels, Alerts, Settings, Side panel.
- Left rail: drawing tools (cursor, line, horizontal, ruler, rectangle, fib, pattern, position, text, colour), undo, delete, Hide Drawings, Lock Drawings. Bottom: Script Editor, Share (NOT pressed), ranges 1D 2D 1W 1M 3M 6M YTD 1Y 5Y, range brush.
- Studies dialog: see studies-list.md (about 235 studies; roughly 100 of them need UW data: GEX family, net premium/flow, dark pool, insiders, 13F, analyst, short interest/FTD/borrow fee, fundamentals growth, events).
- Markers menu toggles: Info Tooltips (on), Truth Social Posts, POTUS Schedule, Insider Trades, Analyst Ratings, FTD Spikes, 13F Filing Waves, Earnings Reports, SEC Filings (10-Q/10-K), Dividends, Stock Splits, Trading Halts, ... (all off; none toggled).
- Crosshair menu: Show, Tooltip, Sticky, Price Level; Info panels Placement (Left), Price Display, OHLCV Display, Timer.
- Alerts menu: "+ New alert" (not pressed), Show on chart; "No alerts for AAPL. They fire while this chart is open, with a chime and a notice." => chart alerts are client-side only.
- Settings panel: DATA (Extended Hours, Extended Hour Highlights, Fill Empty Candles, Show Order Feed, Brush), THEME (Whale Classic, + New Custom Theme), GRID LINES (Horizontal, Vertical, Dense), Y-AXIS (Log Scale, Invert), X-AXIS (Session Markers, ...). Nothing toggled.
- Side panel tabs: Profile (returns 1W..1Y, vitals market cap / avg volume / shares out / beta / next earnings, analysts consensus + recent rating list), Watchlists, Screener. Opened and collapsed again.
- Demo tabs: order flow demo (Options Flow mode: "flow footprint: no options flow in view (intraday data, last session)" + GEX heatmap side pane with Gamma / OI / Shares toggles), contract demo (option-contract trade markers on the SPY chart), studies demo (Analyst Targets lines, GEX heatmap pane, Short Volume Ratio sub-pane).
- Script Editor: accepts Pine Script ("Paste a Pine Script indicator or strategy here"), file list, Docs, Save, Add to chart, tabs Problems / Console / Strategy tester. Opening it showed an unsaved draft "My Script" (EMA sample). I did not press Save, Add to chart or Discard; the unsaved draft may remain listed. Active tab restored to "AAPL unnamed".

