# Fincept's visual structure, for RevenueChaser v2

Owner, 20 Nov 2026: "Fincept terminalleri hosuma gitti, bizim gosterimiz icin de yarica uygun" and "Renkleri cok
gosuma gitmedi onu degistiriz ama gorsel yapisinii bire bir alalim derim". So: **the structure is taken one to one,
the colours are not.** v2 keeps the shared theme of `docs/dashboard_ui.md` until the owner changes it.

Read from `images/Dashboard.png` and `images/EquityResearch.png` (1920 px wide) and from `docs/ARCHITECTURE.md` at
commit `914134d`. The live screens could not be opened without an account (see the [README](README.md)).

## The frame, top to bottom `[READ]` the two screenshots

1. **Title row.** Menus (File, Navigate, View, Help), a **symbol search box**, the product name, a LIVE dot, a
   "drag any symbol here to pin" strip, the clock, account buttons.
2. **Screen tabs.** One row of the main screens in capitals: DASHBOARD, MARKETS, CRYPTO, EQUITY, PORTFOLIO, NEWS ...
   The active one is a filled block.
3. **Open-document tabs.** A second, thinner row of the tabs open in this window (dockable; `CDockManager`).
4. **Screen toolbar.** The screen's name, its state (LIVE, time), a count ("11 WIDGETS"), then on the right the
   scope selector (country), LAYOUTS, a density switch (COMPACT), REFRESH, ADD, SAVE, RESET.
5. **Ticker tape.** One line of index quotes scrolling across the full width.
6. **The work area.** A grid of panels, three across on a wide screen, plus a fixed narrow rail on the right
   ("Market Pulse") that stays while the grid scrolls.
7. **Status bar.** Version, session time, layout state, API state, memory, latency, a READY dot, alerts.

## The panel `[READ]`

Every panel has the same anatomy, and this is what makes the screen read as one system:

- a **header strip**: a coloured tick, the title in small capitals, then the scope after a dot
  ("MARKET INDICES · UNITED STATES"), and on the right three small buttons: settings, refresh, close;
- an optional **segmented control** under the header (1D / 1W / 1M / YTD; GAINERS / LOSERS / MOST ACTIVE);
- the **body**: a dense table (monospaced figures, right-aligned numbers, green and red changes, a small range bar
  per row), a treemap, a gauge with a reading table under it, or a chart;
- a **footer line** in small grey type that states source, time and delay.

## The research screen `[READ]` `images/EquityResearch.png`

One symbol, many views: a header with the symbol box and actions (BACKTEST, CSV, WATCHLIST, OPEN IN), a quote line,
then a **first tab row** by subject (OVERVIEW, FINANCIALS, FILINGS, ANALYSIS, TECHNICALS, PEERS, NEWS, SENTIMENT,
VALUATION, DIVIDENDS, EARNINGS, OPTIONS, ANALYST, OWNERSHIP) and a **second tab row** inside the subject (OVERVIEW,
INCOME STATEMENT, BALANCE SHEET, CASH FLOW, RATIOS). Under it a **strip of twelve small metric tiles**, each with the
value, the change against last year and a sparkline, and then chart panels three across.

This is the model for the per-ticker page the owner approved (GUI review, decision 4).

## What carries over to a web v2, and how

| Fincept element | v2 on the web | Phone (412 px) |
|---|---|---|
| Screen tab row | the same row | becomes a menu; one screen at a time |
| Dockable panel grid, saved layouts | a draggable grid with saved layouts | one column, panels stacked full width |
| Right rail | fixed rail | folds into the top of the column |
| Panel anatomy (header, control, body, footer) | identical; it is the generic renderer the owner chose (decision 2) | identical |
| Symbol search and command bar | one box: a ticker or a board name | the same box, full width |
| Ticker tape | optional, off by default: our data is hourly, not live | off |
| Metric tile strip | the same strip | two tiles across |
| Status bar | data freshness, running jobs, alerts | a single line |

`[INFERRED]` The density (about nine rows of a table in a 180 px tall panel) depends on a monospaced face and a small
size. `docs/dashboard_ui.md` sets our minimum sizes and the 44 px touch target; where the two disagree the phone
rule wins on a phone and Fincept's density is for the desktop widths only.

## Their screens against our boards

| Fincept screen | Our board |
|---|---|
| Dashboard | Welcome |
| Markets | Sector Rotation |
| Equity Research | the per-ticker page (Financials, Fundamentals, SEC 13F) |
| News | News |
| Equity Screener | Asymmetric Growth, Swing Potential, LEAPS |
| Relationship Map | Value Chain, Relatedness, Co-movement |
| Derivatives, Surface Analytics | SPX Gamma, Implied Probability |
| Portfolio, Watchlist | Watch lists |
| Backtesting | Hit Rate |

No counterpart on our side and none planned: Equity Trading, Algo Trading, AI Chat, Node Editor, Code Editor,
Geopolitics, M&A Analytics, QuantLib, Economics. Ours with no counterpart there: Earnings Radar, Settings and data
health.
