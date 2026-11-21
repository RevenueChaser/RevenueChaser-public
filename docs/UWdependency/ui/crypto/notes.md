# Crypto

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 8.

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `01_price-charts_majors_1h.jpg` | https://unusualwhales.com/crypto | 21.11.2026 16:38:47 |
| `02_price-charts_all-52_1d.jpg` | https://unusualwhales.com/crypto | 21.11.2026 16:38:47 |
| `03_spot-whales_top.jpg` | https://unusualwhales.com/crypto?section=whales | 21.11.2026 16:38:47 |
| `04_spot-whales_trade-table.jpg` | https://unusualwhales.com/crypto?section=whales | 21.11.2026 16:38:47 |
| `05_options-vol_overview.jpg` | https://unusualwhales.com/crypto?section=advanced-options | 21.11.2026 16:38:47 |
| `06_options-vol_volatility-details.jpg` | https://unusualwhales.com/crypto?section=advanced-options | 21.11.2026 16:38:47 |
| `07_options-vol_time-series_loading.jpg` | https://unusualwhales.com/crypto?section=advanced-options | 21.11.2026 16:38:47 |
| `08_options-vol_options-chain.jpg` | https://unusualwhales.com/crypto?section=advanced-options&tab=options-chain | 21.11.2026 16:38:47 |

## Notes (what the page shows, buttons pressed, nearest API path)

### /crypto — second pass 21 Nov 2026
Top tabs: Dashboard (back to /dashboard) | Price Charts (/crypto) | Crypto SPOT Whales (?section=whales) | Crypto Options & Volatility (?section=advanced-options).
- Price Charts: line chart cards per pair, timeframe 5m/15m/30m/1h/4h/1d, "Show All (52)" / "Show Major (4)" toggle. Majors: BTC, ETH, SOL, XRP. 52 pairs, all -USD.
- SPOT Whales: four pies (Buy v Sell, Symbol Breakdown, Pair Breakdown, Exchange Breakdown = binance 100%), Crypto Timeline scatter (btc/eth/doge/bnb), then a searchable table of large trades: Symbol, Pair, Exchange, Price, Size, Total, Side, Time. Only Binance USDT pairs.
- Options & Volatility: Instrument select BTC/ETH/SOL; views Overview (Market Summary tiles: price, 24h volume, open interest, ATM IV; Volatility Metrics table: DVOL, ATM vol, skew, term structure, updated; Quick Access), Volatility Details (historical vol metrics chart with date range, today's volatility, IV surface by DTE/strike, term structure), Time Series (5m/30m/1h/4h; stayed on "Loading time series data..." when visited), Options Chain (Expiry, Strike, Call bid/ask/IV, Put bid/ask/IV; row click = chain history). DVOL naming indicates Deribit as source.
- Relevance for RevenueChaser: none (no crypto board).

