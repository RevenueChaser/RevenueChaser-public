# Options Sentiment / Options Pulse

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 18 (kept outside the repository, see ../README.md).

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `options-pulse_sectors_page-bottom.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:56:04 |
| `options-pulse_sectors_table-scroll-2.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:56:15 |
| `options-pulse_sectors_table-scroll-3-bottom.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:56:15 |
| `options-pulse_sectors_top.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:56:04 |
| `options-pulse_symbols_most-bearish.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:55:48 |
| `options-pulse_symbols_page-bottom.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:55:10 |
| `options-pulse_symbols_table-scroll-2.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:55:23 |
| `options-pulse_symbols_table-scroll-3.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:55:23 |
| `options-pulse_symbols_table-scroll-4.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:55:23 |
| `options-pulse_symbols_table-scroll-5-bottom.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:55:23 |
| `options-pulse_symbols_top.jpg` | https://unusualwhales.com/options-pulse | 21.11.2026 14:55:10 |
| `options-sentiment_all.jpg` | https://unusualwhales.com/options-sentiment | 21.11.2026 14:54:22 |
| `options-sentiment_all_limit-200.jpg` | https://unusualwhales.com/options-sentiment | 21.11.2026 14:54:22 |
| `options-sentiment_bearish.jpg` | https://unusualwhales.com/options-sentiment | 21.11.2026 14:54:22 |
| `options-sentiment_bullish_scroll-2.jpg` | https://unusualwhales.com/options-sentiment | 21.11.2026 14:54:03 |
| `options-sentiment_bullish_scroll-3.jpg` | https://unusualwhales.com/options-sentiment | 21.11.2026 14:54:03 |
| `options-sentiment_bullish_scroll-4-bottom.jpg` | https://unusualwhales.com/options-sentiment | 21.11.2026 14:54:22 |
| `options-sentiment_bullish_top.jpg` | https://unusualwhales.com/options-sentiment | 21.11.2026 14:54:03 |

## Notes (what the page shows, buttons pressed, nearest API path)

### /options-sentiment "Volatility Hub / Options Sentiment" (2026-11-21 14:54 Amsterdam)
Tabs: Bullish, Bearish, All. Limit: 25 / 50 / 100 / 200. Columns: Ticker, Score (sortable, -100..100), Dir, VWKS, AVAR, Contracts.
Footnote: "Options positioning sentiment blends VWKS (volume-weighted strike-spot 'center of volume mass' - where option volume sits vs spot) and AVAR (call vs put IV asymmetry). Positive score = bullish positioning, negative = bearish. Distinct from flow (net premium) and vol level."
Ticker links go to the ticker page. No filters, no export. Left as found (Bullish, 50).

### /options-pulse "Options / Pulse" (2026-11-21 14:55 Amsterdam)
Top tiles: MARKET SENTIMENT (128.77, as of 16:20 ET), CALLS transactions, PUTS transactions, CALL/PUT ratio, BREADTH bullish/bearish. Chart: Market Sentiment Trend (intraday 09:40-16:20).
Tab Symbols: "Sentiment Scanner": Most bullish / Most bearish, Limit 25/50/100/200, ticker filter box, Sentiment min-max, Txns >= (default 100), Clear. Columns: Ticker, Sentiment (-1..1), Interval, Calls, Puts, Txns, Put/Call, As of (ET).
Tab Sectors: "Sector & Industry Pulse": Category (sector/industry), Classification, Sentiment, Calls, Puts (~40 rows).
Footnote: "Nasdaq Options Pulse aggregates opening-buy option flow (customer vs professional) across Nasdaq's options exchanges into a sentiment score. Positive is bullish, negative bearish. Times are ET. Updated intraday."
Source is a Nasdaq data product (customer/professional opening buys) -> not derivable from OPRA tape alone. Left as found (Symbols, Most bullish, 50).

