# Fincept: which screen uses which source

How this was built: for each screen folder under `fincept-qt/src/screens/` the service singletons it calls were
counted, and for each service folder under `fincept-qt/src/services/` the Python scripts and hosts it names were
listed (`grep`, commit `914134d`). `[READ]` rows quote those names. Nothing was run with data.

## The short answer

- **The whole equity core runs on Yahoo Finance through `yfinance`, with no key.** `[READ]` Quotes, history, FX,
  watch-list alerts and symbol search all go through `yfinance_data.py` (`services/markets`, 10 references);
  fundamentals, peers and company news add `equity_research_data.py`; the screener posts to Yahoo's own screener
  endpoint (`scripts/screener_data.py:3`, "yfinance is used only for its Yahoo session handling").
- **SEC EDGAR is the second free pillar**: filings (`fincept_mcp/edgar/main.py`) and company facts
  (`sec_company_facts.py`). `[READ]`
- **Option chains are free and delayed: Cboe first, Yahoo as the fallback.** `[READ]`
  `scripts/derivatives/deriv_market.py:1-8`: "Primary source: Cboe's public delayed-quote feed (cdn.cboe.com, about 15
  minutes delayed, no key); fallback: Yahoo Finance". The Treasury yield curve comes from home.treasury.gov and
  futures curves from Yahoo, in the same script.
- **The paid sources buy what the free ones cannot give**: real-time and tick-level data. `[READ]` Databento
  (`services/databento`, `databento_provider.py`, `databento_fno_chain.py`) feeds Surface Analytics and the F&O
  screen; broker accounts feed live quotes, positions and orders (16 brokers, `trading/brokers/`).
- **News is RSS**, free: BBC, CNBC, Dow Jones, SCMP, Investing.com, FT and others are named in `services/news`.
  `[READ]` Sentiment is computed locally (`vaderSentiment.py`). NewsAPI appears once in `services/equity`. `[READ]`
- **Fincept's own server (`api.fincept.in`) sits behind the account**: symbol master, macro calendar, geopolitics and
  maritime data, the last two metered in "credits" (`docs/DATAHUB_TOPICS.md`, geopolitics and maritime tables).
  `[READ]` Without a sign-in the log shows `HTTP 401` on `/symbols/changes`. `[READ]`, run log of 20 Nov 2026.

## Screen by screen

| Fincept screen | Services it calls most `[READ]` | Sources behind them `[READ]` | Key |
|---|---|---|---|
| Dashboard | `PortfolioService`, `RiskCompositeService`, `OptionChainService`, `ScreenerService` | Yahoo, Cboe, FRED (`fred_data.py`), Polymarket | FRED key only |
| Markets | `MarketDataService` | Yahoo (`yfinance_data.py`) | no |
| Equity Research | `EquityResearchService` (35 calls), `FxRateService`, `FinceptDataService`, `SecFilingsService` | Yahoo, SEC EDGAR, company news scripts, exchange filing sites | no |
| Equity Screener | `ScreenerService` | Yahoo's screener endpoint | no |
| News | `NewsService`, `NewsMonitorService`, `NewsNlpService` | RSS feeds, local sentiment | no |
| Portfolio | `PortfolioService`, `PortfolioAnalyticsService`, `BacktestingService` | Yahoo prices, FRED (risk-free rate), local analytics (`ffn`, `quantstats`) | FRED key |
| Watchlist | `WatchlistAlertService`, `FxRateService` | Yahoo | no |
| Derivatives | `CurveDataService`, `FreeOptionChainService` | Cboe delayed chain, Yahoo fallback, Treasury curve | no |
| Surface Analytics | `DatabentoService` | Databento | **yes, paid** |
| F&O | `OptionChainService`, `InstrumentService` | broker feeds, Databento | **yes** |
| Relationship Map | `RelationshipMapService` | Yahoo (`relationship_map.py`; "yfinance-backed corporate relationship snapshot") | no |
| Economics | `EconomicsService`, `FinceptMacroService` | Fed, FRED, BLS, EIA, WTO, NBER and the catalogue's macro connectors | some |
| Backtesting | `BacktestingService` | local engines over Yahoo history | no |
| Calendars | `FinceptDataService` | Fincept's own server | account |

## What the free and the paid sources are used for

| Need | Free source Fincept uses | Paid source Fincept uses | What the paid one adds |
|---|---|---|---|
| Stock quotes and history | Yahoo | broker account, Polygon, Tiingo, Databento | real time instead of delayed; tick data |
| Fundamentals | Yahoo, SEC company facts | FMP, SimFin, Intrinio, EODHD | cleaner history, estimates |
| Option chain | Cboe delayed, Yahoo | Databento, broker | real time, full depth, history of the surface |
| Macro | Fed, Treasury, World Bank, IMF, DBnomics, OECD | FRED, BLS, BEA, EIA (free keys), Trading Economics (paid) | a key raises rate limits; Trading Economics adds a calendar |
| News | RSS | NewsAPI | search by company |
| Crypto | CoinGecko, exchange websockets | CoinGlass, Glassnode, Messari | derivatives and on-chain analytics |

`[INFERRED]` The pattern: Fincept ships working screens on keyless sources and treats every key as an upgrade the
user plugs in. Nothing in the open edition depends on a paid source to open.
