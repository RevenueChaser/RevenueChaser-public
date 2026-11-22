# GEX and True GEX (Periscope)

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 34.

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `delta-flow_interval-menu.png` | https://unusualwhales.com/periscope/delta-flow | 21.11.2026 16:05:55 |
| `delta-flow_top.jpg` | https://unusualwhales.com/periscope/delta-flow | 21.11.2026 16:05:39 |
| `gex_about-dialog.jpg` | https://unusualwhales.com/periscope/gex | 21.11.2026 16:08:00 |
| `gex_chart-type-menu.png` | https://unusualwhales.com/periscope/gex | 21.11.2026 16:06:56 |
| `gex_compare-ticker-menu.png` | https://unusualwhales.com/periscope/gex | 21.11.2026 16:08:12 |
| `gex_data-menu.png` | https://unusualwhales.com/periscope/gex | 21.11.2026 16:06:56 |
| `gex_display-menu.png` | https://unusualwhales.com/periscope/gex | 21.11.2026 16:06:56 |
| `gex_expiries-menu.png` | https://unusualwhales.com/periscope/gex | 21.11.2026 16:06:56 |
| `gex_heatmap.jpg` | https://unusualwhales.com/periscope/gex | 21.11.2026 16:06:42 |
| `gex_ticker-menu.png` | https://unusualwhales.com/periscope/gex | 21.11.2026 16:08:12 |
| `gex_unit-menu.png` | https://unusualwhales.com/periscope/gex | 21.11.2026 16:06:56 |
| `gex_view-chart.jpg` | https://unusualwhales.com/periscope/gex (chart=chart) | 21.11.2026 16:07:07 |
| `gex_view-expiry.jpg` | https://unusualwhales.com/periscope/gex (chart=expiry) | 21.11.2026 16:07:40 |
| `gex_view-intraday.jpg` | https://unusualwhales.com/periscope/gex (chart=intraday) | 21.11.2026 16:07:18 |
| `gex_view-strike-dte.jpg` | https://unusualwhales.com/periscope/gex (chart=strike_dte) | 21.11.2026 16:07:40 |
| `gex_view-strike.jpg` | https://unusualwhales.com/periscope/gex (chart=strike) | 21.11.2026 16:07:40 |
| `heatmap_date-picker.png` | https://unusualwhales.com/periscope/market-exposures-table | 21.11.2026 16:04:26 |
| `heatmap_display-options.jpg` | https://unusualwhales.com/periscope/market-exposures-table | 21.11.2026 16:03:59 |
| `heatmap_exposure-menu.png` | https://unusualwhales.com/periscope/market-exposures-table | 21.11.2026 16:03:59 |
| `heatmap_gamma.jpg` | https://unusualwhales.com/periscope/market-exposures-table | 21.11.2026 16:03:45 |
| `heatmap_summary-panel.jpg` | https://unusualwhales.com/periscope/market-exposures-table | 21.11.2026 16:04:08 |
| `heatmap_time-picker.png` | https://unusualwhales.com/periscope/market-exposures-table | 21.11.2026 16:04:26 |
| `mm-exposures_filters.jpg` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:04:33 |
| `mm-exposures_highlight-rules.png` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:04:40 |
| `mm-exposures_info-drawer.jpg` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:04:58 |
| `mm-exposures_scroll-2.jpg` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:05:17 |
| `mm-exposures_scroll-end.jpg` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:05:17 |
| `mm-exposures_settings.jpg` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:04:47 |
| `mm-exposures_show-charts.jpg` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:04:58 |
| `mm-exposures_straddle-menu.png` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:04:40 |
| `mm-exposures_top.jpg` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:04:26 |
| `mm-extended_greek-menu.png` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:05:27 |
| `mm-positions_dte-filter.png` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:05:27 |
| `mm-positions_expiry-menu.png` | https://unusualwhales.com/periscope/market-exposure | 21.11.2026 16:05:27 |

## Notes (what the page shows, buttons pressed, nearest API path)

### Periscope True GEX (raw notes, second pass) — 2026-11-21 ~15:04-15:07Z

Periscope is a paid ADD-ON (its own Info text says so, also for lifetime subscribers) and covers SPX only. It shows ACTUAL net Market Maker positions and greek exposure, updated every 10 minutes, "beyond the modeling assumptions used elsewhere on Unusual Whales". Delta Flow shows the net of all non-Market Maker participants (retail and professional customers, broker dealers, firms) and separates opening trades. That participant split is not derivable from OPRA trades/quotes; it needs an exchange open-close style feed. => Not reproducible with IBKR data alone; check the public API for periscope paths before the plan assumes it.

### Heatmap (/periscope/market-exposures-table)
- Grid strike x expiry (53 expiries, first column "Sum <= 1855d"), cell = "Gamma x Net Contracts x Shares per Contract", row Net at the bottom, spot line, markers call wall / put wall / move high / move low, "Implied move ±2.2% by Nov 23".
- Controls: Live; date nav + date picker (calendar shows each day's SPX % move); time nav + picker (HOUR / MIN lists, Jump to Open 15:30 / Noon 18:00 / Close 22:00 CET, arrows step 1m 5m 10m 15m 1h) => intraday history replay is available; Gamma | Vanna | Charm; unit select Dollars | Exposure; HORIZON slider (max 1855 days); Display options (Shade per expiry off, Implied move on, Density Compact | Wide, Markers Full | Short, Units Thousands (K) | Compact (K, M, B) | Full number).
- SUMMARY side panel: LARGEST LEVELS (strikes with gamma and % from spot, implied-move bounds), "Volatility ->" link, GAMMA BY EXPIRY bars ("10.3% gone tonight", "Front expiry holds 10% and expires tonight. 22/53 long gamma."), HEDGE SCENARIOS table (market maker shares to buy/sell for spot +1% / flat / -1% x IV -1pt / flat / +1pt, with IV30).
- Pressed: Vanna, Charm (restored Gamma), menus opened and closed. Nothing saved.

### Market Maker Exposures (/periscope/market-exposure)
- Three charts (Show Charts checklist): "Market Maker Exposures" (SPX hourly candles + per-strike profile bars with dots = value 10 min earlier), "SPX Market Maker Positions" (calls / puts per strike, dots for positions 10/20/30 min ago), "SPX Market Maker Exposures Extended" (Greek select Gamma / Vanna / Charm).
- Toolbar per chart: date nav, time nav (skip 10 min), LIVE, Expiry tree (Multi | Single, year > month > date), DTE filter (Min/Max DTE), candle interval (1h), zoom buttons (show more / fewer strikes), filters.
- FILTERS panel: Charts Gamma / Vanna / Charm / Positions; Straddle None / Cone / Breakeven; Highlight rules per greek (MM Flips toggle, MM Unit Changes > than, MM Pct Changes > than, Clear, Apply to all); Mode Absolute | Change; Lookbacks 1m 5m 10m 15m 20m 30m (3 of 6 selected) with Apply.
- Top right: Chime (sound toggle, not pressed), Show Charts, Settings (Dock Tooltip), Info.
- Info drawer, summarized: bars = net MM gamma per strike (negative left, positive right); orange bar = sign flipped since the previous 10-minute slice; purple = change beyond the highlight threshold; dots = previous slice; straddle lines = theoretical 0DTE ATM straddle breakevens computed at 9:31 ET (None / Cone / Breakeven). Net negative gamma means MMs are net short options at that strike (customers net bought, calls or puts alike); it is not a bullish/bearish signal.

### Delta Flow (/periscope/delta-flow)
- SPX candles + two bar panels: net delta per period, and positive/negative deltas split by expiration. OPEN | ALL switch (opening deltas only vs opening + closing), interval 1 min / 5 min / 10 min, chart-type icon (menu Candle / Close seen), Info drawer. "Data through 20 Nov, 22:00 CET".
- Positive bar = non-MM participants net added deltas (call buying + put selling exceeded put buying + call selling).

### GEX (/periscope/gex) — modeled GEX for any ticker, 2026-11-21 ~15:07Z
- Header: ticker with price (dropdown search "Ticker or company" with LAST / CHG / YTD), "+ Add ticker" ("COMPARE SPY WITH" search; not selected), DATE nav, DATA Live | Premarket, CHART TYPE Heatmap | Chart | Intraday | Strike | Expiry | Strike + DTE (URL chart=...), GREEK Gamma | Charm | Vanna, INFO.
- Second row: basis toggle VOLUME (-5,524,349) | OPEN INTEREST (-20,044,795); "Shares Hedged per 1% Price Change" unit select Shares | Dollars | Exposure; expiry window Today / This week / Two weeks / 30 days / 60 days / 90 days / 6 months / All expiries; Display (Shade per expiry, Walls & flip, Implied move, Density Compact | Wide, Markers Full | Short, Units Thousands | Compact | Full number). Related tickers SPX XSP QQQ IWM NVDA. HORIZON slider. SUMMARY panel as in Periscope.
- Views:
  - Heatmap: strike x expiry grid, Sum column, Net row, markers call wall / move high / spot / flip / put wall / move low.
  - Chart: full charting widget (candles + "Daily GEX" sub-pane, gamma level lines), DISPLAY MODE select (Zones), Open Charts, Draw, Studies, Script Editor, ranges 1D..5Y.
  - Intraday: Spot, Exposure (Volume and Open interest lines), IV30 panes; "SINCE OPEN -1,803,987 shares", "LAST HOUR +91,574 shares"; shaded positive/negative gamma regimes; text "Net gamma negative since 12:05 PM (3h 54m) - increased volatility".
  - Strike: bars per strike, Net | Calls vs puts, toggles Volume / Open interest / Flip & walls / Implied move.
  - Expiry: bars per expiry.
  - Strike + DTE: stacked by DTE bucket 0-7, 8-30, 31-60, 61-120, 121+.
- METHOD (About GEX dialog, summarized): GEX assumes dealers take the other side of every trade; positive = dealers long gamma. Volume basis = dealer side of today's trades (a trade near the ask counts as dealers selling, near the bid as dealers buying). Open-interest basis assumes large institutions hold most OI and mostly sell calls and buy puts, so dealers are long calls and short puts. Each contract adds gamma x dealer net contracts x shares per contract, summed by strike and expiry. Flip = cumulative net gamma from the lowest strike, where it crosses zero (nearest crossing to spot). Call wall = strike above spot with the largest positive gamma; put wall = strike below spot with the largest positive gamma (as written there). After the open the Data dropdown offers a premarket snapshot.
  => This page is reproducible from our own chain (OI, greeks) plus trade-side classification; Periscope True GEX is not.
- Pressed and restored: every chart type (back to Heatmap), Open Interest basis (back to Volume). URL back to /periscope/gex without parameters.

