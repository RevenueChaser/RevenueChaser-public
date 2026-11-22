# UW features seen in the web UI with no matching public API path

Checked on 21 Nov 2026 against `public_api_paths.txt` (241 paths of the public OpenAPI spec, copy in
`api/uw_public_api_openapi.yaml`). "No path" means no path name in that list matches; it was **not** tested by a
call. Items marked *(derived)* are computed by UW from data the API does serve, so they can be rebuilt; items
marked *(curated)* are UW's own hand-made lists.

## No path found

| Feature | Where in the UI | Folder | Kind | Matters for RevenueChaser? |
|---|---|---|---|---|
| Halts / Pause feed | Market > Halts / Pause Feed | market | data feed | Low. Nasdaq and NYSE publish halts free. |
| Holiday schedule | Calendars > Holiday Schedule | calendar | static table | No. |
| Dividend calendar (market-wide, by day) | Calendars | calendar | data | No. Per-ticker dividends exist (`/api/companies/{ticker}/dividends`). |
| Catalysts types Conference, Investor Day, Guidance, Product, Shareholder Meeting | Market > Catalysts | market | data | Low. Earnings, FDA, economic events do have paths. |
| Fed speaker impact statistics | Economic Calendar | calendar | derived | No. |
| Tourism by region charts | Economic Calendar tabs | calendar | data | No. |
| Daily report anomaly score ("Inputs of 5") | Market > Daily Reports | market | derived | Low. Inputs are in the API. |
| Sector / theme baskets in the screeners | Stock Screener | screeners | curated | Low. RevenueChaser has its own themes. |
| Investor-type tags (Activist, Tiger Cub, ...) and Investor Lists | Institutions, flow filters | market, watchlists | curated | Low. 13F board is our own. |
| Non-standard (adjusted) options table | Market | market | data | No. |
| Market stats dot plots (total OI, trades canceled, green stocks ...) | Market Monitor | market | derived | No. |
| USONAR radar: committee-to-sector conflict flags, 14-day alpha | Politics | politics | derived | No. `/api/congress/unusual-trades/stats` may be related: verify. |
| Politician portfolio backtests, estimated values | Politics | politics | derived | No. |
| Trade Finder confluence ranking | Mr. Whale > Trade Finder | mr-whale | derived | Low. Each signal is a filter over an API feed. |
| Mr. Whale chat and Automations | Mr. Whale | mr-whale | LLM product | No (the MCP connector is separate). |
| Contract "Analysis" block: probability of profit, Kelly size, trade-idea fit, "Opening trade?" | Contract Look-Up | options-flow | derived | Low. |
| Multi-leg strategy labelling | Multi-leg Flow | options-flow | derived | Medium for live-option-flow: we would need our own leg matcher. |
| Earnings "trade setup" card and "historical edge" label | Ticker > Earnings | ticker-page | derived | Low. The history behind it is `/api/earnings/{ticker}`. |
| Options chain "Trade Idea" presets (Sell premium, Sell vega, Directional, LEAPs, Cheapies) | Ticker > Options Chain | ticker-page | derived | No. |
| Risk page: beta, Sharpe, drawdown, P/L distribution | Ticker > Risk | ticker-page | derived | No. Computed from daily closes. |
| Options Profit Calculator (38 strategies) | Tools | tools | tool | No. |
| Paper Trading, Portfolio Backtesting | Tools | tools | tool | No. |
| Charting studies, drawings, Script Editor | Charting | charting | tool | No. |
| Console: the command language, presets and templates | Console | console | tool | **High.** This is avo's "unusual-command-line" item. The presets are thresholds over flow data the API serves; the command list and thresholds are in `console/commands_all-229.md` and `console/notlar.md`. |
| Data Downloads: daily files, last 8 trading days | Other > Data Downloads | data-downloads | bulk files | **High, one-off.** Cheapest way to keep reference days before 8 Dec 2026. |
| Volatility anomaly score, Volatility Character labels, Radar composite score | Volatility | volatility | derived | Low to medium. Inputs (`/api/stock/{t}/volatility/*`) are in the API. |
| Fear & Greed style gauge, Options Sentiment composite | Sentiment | sentiment | derived | Low. `/api/options-pulse/*` exists for Pulse. |
| Trump portfolio (estimated holdings) | Calendars / Politics | calendar | derived | No. `/api/potus/posts` and `/schedule` exist. |
| 52-week high/low push (the Discord `stock-updates` feed) | Preset Alerts | discord-bot | derived | **Yes.** No dedicated path; rebuild from daily prices. |

## Earlier "UI only" guesses that turned out to have a path

- FLEX trades: `/api/flex-options`, `/api/flex-options/{ticker}`, `/market`, `/chain/{chain}`.
- Watchlists: `/api/watchlists/stocks`, `/stocks/{id}`, `/add-tickers`, `/remove-tickers`, `/api/watchlists/options`, `/options/{id}`.
- Custom alerts: `/api/alerts`, `/alerts/configuration`, `/alerts/filters`, `/alerts/query/grammar`.
- Trading Journal / Portfolios: `/api/portfolio/accounts`, `/holdings`, `/trades`, `/performance`, `/edge`, `/rank`, `/catalysts`, `/ticker/{ticker}`.
- FEC and lobbying: `/api/politics/fec/candidates`, `/companies`, `/company/{ticker}/lobbying`, `/company/{ticker}/people`, `/contributions`.
- Politician portfolios: `/api/politician-portfolios/*` (5 paths).
- Flow alert detail: `/api/option-trades/flow-alerts/{id}`.
- Economic and FDA calendars: `/api/market/economic-calendar`, `/api/market/fda-calendar`; IPO: `/api/calendar/ipo`.
- Predictions: `/api/predictions/*` (10 paths).
