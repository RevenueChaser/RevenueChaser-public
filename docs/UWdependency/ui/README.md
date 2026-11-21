# UWdependency — Unusual Whales web UI survey (Task 2.1)

Done 21 Nov 2026 in avo's logged-in Chrome (account plan shown in the UI: "Whale Bundle Basic - Monthly").
UW plan ends 8 Dec 2026. This folder is the record of what the web UI shows, for the thread
"Plan migration away from Unusual Whales".

## How it was done

- Second, full pass ("bastan basla"): every page in the left navigation was opened, scrolled to its end, and every
  tab, view switch, dropdown, filter panel, column menu and detail panel was pressed and recorded.
- **Not pressed, on purpose:** delete buttons, save/create in dialogs, share/publish, CSV and file downloads,
  account, subscription and payment pages, API key reveal/copy/regenerate, broker or Discord linking, watchlist and
  favourite toggles, Mr. Whale prompts (they spend credit), the chat widget.
- **Left behind:** one "STM" bookmark row in Options Watchlist (UW's auto-bookmark; removal was not possible for me).
  Crypto "Show All (52)" left expanded (view state only). Nothing else was created or changed.
- 681 screenshots from the second pass, 62 older ones from the first pass in `_ilk-tur/` (kept, superseded).

## Where the screenshots are

**Not in this repository.** This tree is code only, and the survey's 681 screenshots, avo's exported stock
watchlists and his alert rules are data and personal configuration. They live beside the thread at
`/mnt/project-files/UWdependency/`, in the folders listed below, each with its own `notlar.md`
(file, full URL, capture time). What this folder carries is the index, the UI-only feature list, the navigation
map and the public API path list. The part that changes the migration plan is `../07_ui_survey.md`.

## Files at the top level

| File | What |
|---|---|
| `README.md` (this file) | the survey index, as written by the survey thread |
| `UI-only-features.md` | features seen in the UI with no matching public API path, and earlier guesses that were wrong |
| `manifest.tsv` | every second-pass screenshot: folder, file, full URL, capture time (UTC) — **in the project folder, not here** |
| `nav-links.md` | the left navigation as read from the page, with paths |
| `public_api_paths.txt` | the 241 paths of the public API |
| `api/uw_public_api_openapi.yaml` | the full public OpenAPI spec (fetched 21 Nov 2026) — **in the project folder** |

Each folder has a `notlar.md`: a table of its screenshots (file, full URL, time in Amsterdam time), then what the
page shows, which buttons were pressed and what they did, and the nearest API path.

## Folders

| Folder | UI area | Shots | Relevance to the migration |
|---|---|---|---|
| `dashboard/` | Dashboard widgets, flow table columns and filter panel | 21 | Medium: the full column and filter list of the flow table |
| `options-flow/` | Live Options Flow, Contract Look-Up, Net Flow, OI Explorer, Flow Alerts, Interval Flow, 0DTE, Multi-leg | 85 | **High**: this is "live-option-flow". Flow-alert rule thresholds are recorded |
| `console/` | Console command line, settings, templates | 10 | **High**: "unusual-command-line". All 229 commands in `commands_all-229.md`, preset thresholds in the notes |
| `custom-alerts/` | Custom Alerts, all 29 alert types, formula fields | 19 | **High**: avo's four alert rules, `alert-types_all-29-forms.md`, `formula-fields_option-trades.md` |
| `watchlists/` | Option and Stock Watchlists, Investor Lists | 19 | **High**: avo's six stock lists exist only in UW; exported to `avo_stock_watchlists.json` |
| `data-downloads/` | Daily bulk files, last 8 trading days | 2 | **High, one-off**: reference days for testing an own build; nothing was downloaded |
| `ticker-page/` | One ticker (NVDA), all 23 sub-pages | 71 | **High** for Insiders (Form 4 build), Net Premium, NOPE (most active chains), Options Chain, OI Changes; low for the rest |
| `screeners/` | Options Screener, Stock Screener (224 fields), presets | 41 | Medium: preset parameters recorded; "highest-volume-contracts" is a screener sort |
| `market/` | Daily Reports, Catalysts, Market Tide, Heatmaps, Institutions, Halts, Futures, Market Monitor, analysts, insiders feed | 95 | Medium: Market Tide formula, analyst ratings view, insider feed |
| `dark-pool/` | Dark Pool / Lit tape | 8 | Medium: 7-day history and $100K floor in the UI |
| `periscope/` | GEX and True GEX | 34 | Medium: GEX rebuilds from a chain; Periscope (dealer positioning) does not |
| `volatility/` | Volatility Hub, Radar, Character | 15 | Low to medium |
| `sentiment/` | Options Sentiment, Options Pulse | 18 | Low |
| `calendar/` | Earnings, Economic, Holiday, FDA, Trading calendars | 43 | Low: earnings calendar is the used part |
| `mr-whale/` | Chat, Trade Finder, Automations | 47 | Low: Trade Finder signal definitions recorded |
| `politics/` | Congress trades, politicians, FEC, lobbying, USONAR | 40 | Low |
| `charting/` | Charting tool | 16 | None |
| `trading-journal/` | Trading Journal, Portfolios | 14 | None (avo has nothing linked) |
| `predictions/` | Prediction markets | 35 | None |
| `crypto/` | Crypto pages | 8 | None |
| `tools/` | Options Calculator, News Feed, Paper Trading, Portfolio Backtesting | 21 | None |
| `api/` | API dashboard page, public spec | 9 | Reference. No key is shown in any screenshot |
| `shell/` | Header settings, account menu, alert and watchlist sidebars, Saved Flows | 5 | Low: avo's alert sidebar shows his live Insider Trade alerts |
| `discord-bot/` | UW bot in avo's server "Traders' Pub" | 5 | Plan B. From avo's screenshots only; the browser pass is still to do, after avo explains how |

## What the plan thread should take from this

1. **Three things exist only inside UW and are avo's own:** six stock watchlists (exported), four custom alert
   rules (recorded), and the Console habits (commands recorded). Saved Flows is empty and no backtest or linked
   brokerage account exists.
2. **"highest-volume-contracts" is the same table in four places:** Console `/moso`, ticker Overview, ticker NOPE
   page ("Most Active Chains"), and the options screener sorted by volume. One chain snapshot with volume gives it.
3. **What needs a trade tape with bid/ask side** (so IBKR or Cboe trades, not a chain snapshot): Live Flow, flow
   alerts, Net Premium, NOPE, delta flow, bullish/bearish premium, bid/ask volume bars.
4. **What a daily chain snapshot rebuilds:** OI changes, max pain, GEX/vanna/charm by strike and expiry, options
   grid, highest OI, implied move per expiry.
5. **Free public sources behind UW pages:** Form 4 (insiders, with the 10b5-1 flag and stake change), 13F
   (institutions), FINRA short volume, SEC fails-to-deliver, House/Senate disclosures, FEC.
6. **UW is retiring DEX** (banner on the Delta tab). Do not rebuild it.
7. **Before 8 Dec:** Data Downloads offers the last 8 trading days of five daily files. Taking a few reference
   days is avo's call (personal-use terms); I downloaded nothing.

## Open

- Discord bot: browser pass in avo's Discord window, method to come from avo. avo (21 Nov 17:02 Amsterdam):
  Traders' Pub is his and his friends' server, the UW bot there runs on the UW API; the aim is to see how the bot
  works and whether it can be tied into his system, and to keep a record of it either way.
- "No path" in `UI-only-features.md` is a name match against the spec, not a tested call.
- Ticker > Volatility has no screenshot (the capture timed out twice); the Volatility Hub shots cover the same component.

## Public API surface, by prefix (for the UI-only comparison)

stock 63, market 13, crypto 13, predictions 10, private-markets 9, portfolio 8,
option-trades 8, futures 8, congress 8, watchlists 6, shorts 6, politics 6,
institution 6, companies 6, politician-portfolios 5, etfs 5, volatility 4,
seasonality 4, screener 4, option-contract 4, insider 4, flex-options 4, alerts 4,
options-pulse 3, forex 3, earnings 3, darkpool 3, potus 2, lit-flow 2, institutions 2,
group-flow 2, digital-currencies 2, analytics 2, and one each for stock-directory,
short_screener, sec-filings, option-activity, news, net-flow, economy, commodities, calendar.
