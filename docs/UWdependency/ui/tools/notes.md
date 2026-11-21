# Tools (Options Calculator, News Feed, Paper Trading, Portfolio Backtesting)

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 21 (kept outside the repository, see ../README.md).

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `backtest_01_list_top.jpg` | https://unusualwhales.com/backtesting/portfolios | 21.11.2026 16:42:28 |
| `backtest_02_list_bottom_no-own-backtests.jpg` | https://unusualwhales.com/backtesting/portfolios | 21.11.2026 16:42:28 |
| `backtest_03_detail_historical-performance.jpg` | https://unusualwhales.com/backtesting/portfolios/<id> | 21.11.2026 16:42:28 |
| `backtest_04_detail_assets-table.jpg` | https://unusualwhales.com/backtesting/portfolios/<id> | 21.11.2026 16:42:28 |
| `backtest_05_detail_drawdown_annual-returns.jpg` | https://unusualwhales.com/backtesting/portfolios/<id> | 21.11.2026 16:42:28 |
| `backtest_06_detail_yearly-high-low_monthly-returns.jpg` | https://unusualwhales.com/backtesting/portfolios/<id> | 21.11.2026 16:42:28 |
| `backtest_07_detail_monthly-chart_ai-review.jpg` | https://unusualwhales.com/backtesting/portfolios/<id> | 21.11.2026 16:42:28 |
| `backtest_08_new-backtest-form.jpg` | https://unusualwhales.com/backtesting/new | 21.11.2026 16:42:28 |
| `calc_01_empty_strategy-picker.jpg` | https://unusualwhales.com/options-profit-calculator | 21.11.2026 16:40:05 |
| `calc_02_getting-started-panel.jpg` | https://unusualwhales.com/options-profit-calculator | 21.11.2026 16:40:05 |
| `calc_03_long-call_chart.jpg` | https://unusualwhales.com/options-profit-calculator/long_call/STM/STM261204C00040000 | 21.11.2026 16:40:05 |
| `calc_04_long-call_table.jpg` | https://unusualwhales.com/options-profit-calculator/long_call/STM/STM261204C00040000 | 21.11.2026 16:40:05 |
| `calc_05_long-call_breakeven.jpg` | https://unusualwhales.com/options-profit-calculator/long_call/STM/STM261204C00040000 | 21.11.2026 16:40:05 |
| `calc_06_long-call_positions-greeks.jpg` | https://unusualwhales.com/options-profit-calculator/long_call/STM/STM261204C00040000 | 21.11.2026 16:40:05 |
| `calc_07_transform-dialog.jpg` | https://unusualwhales.com/options-profit-calculator/long_call/STM/STM261204C00040000 | 21.11.2026 16:40:05 |
| `news_01_news-feed.jpg` | https://unusualwhales.com/news-feed | 21.11.2026 16:40:41 |
| `news_02_news-feed_major-only.jpg` | https://unusualwhales.com/news-feed?major_only=true | 21.11.2026 16:40:41 |
| `news_03_featured-news.jpg` | https://unusualwhales.com/news | 21.11.2026 16:40:41 |
| `paper_01_home_options-form.jpg` | https://unusualwhales.com/trade | 21.11.2026 16:41:13 |
| `paper_02_stocks-form_worst-performing_most-liked.jpg` | https://unusualwhales.com/trade | 21.11.2026 16:41:13 |
| `paper_03_recent-trades-filter.jpg` | https://unusualwhales.com/trade | 21.11.2026 16:41:13 |

## Notes (what the page shows, buttons pressed, nearest API path)

### Tools — second pass 21 Nov 2026

### /options-profit-calculator (OPC)
- Opens on the last viewed ticker (STM). Left: Saved Trades sidebar ("No saved trades"). Header icons: sidebar toggle, Load, (after a build) bookmark = save trade, share; not pressed (save/share change or publish data). "Getting started" opens a help drawer (Intro, Basics, Reposition, Transform, Save & Delete). The three-dot menu: "<ticker> Options Flow", "Analyst Page", "Company Profile".
- 38 prebuilt strategies with payoff sketch, net debit/credit, max loss, max profit, search box and sort: Long Call, Short Call, Long Put, Short Put, Call Credit Spread, Call Debit Spread, Put Credit Spread, Put Debit Spread, Strangle, Short Strangle, Straddle, Short Straddle, Iron Condor, Short Iron Condor, PUT Condor, Short PUT Condor, CALL Condor, Short CALL Condor, Guts, Short Guts, Call Butterfly, Put Butterfly, Short Call Butterfly, Short Put Butterfly, Short Put Ladder, Short Call Ladder, Put Ladder, Call Ladder, Call Ratio Spread, Put Ratio Spread, Call Backspread, Put Backspread, Strap, Strip, Jade Lizard, Synthetic Call, Calendar Call Spread, Calendar Put Spread.
- Clicking a strategy builds it at "a target mid price" (Long Call -> STM 40C 4 Dec 2026) and the URL becomes /options-profit-calculator/<strategy>/<ticker>/<OCC symbol>.
- Built view: views Table (price x date grid of P/L %), Chart (payoff), Breakeven (price history + breakeven line + profit zone); value modes % Entry Cost, % Max Loss / IC, Profit / (loss), Gross value. Summary row: Net debit/credit, Max Loss, Max Profit, Total Delta, Total Theta, Monthly Premium Decay, Daily Decay, Buying Power Reduction ($100k portfolio), CVaR (estimated), Expected Monthly ROC, Expected Monthly Account Return, Beta-weighted SPY Delta. Warnings line (wide bid-ask spread, low open interest).
- Controls: Date Slider, Target Price, Price Range, Volatility (IV offset; current weighted-average IV), Reposition; Positions table per leg: Strike, Mark, Gain, IV, Vega, Theta, Delta, Gamma, Rho, +1% vol, +1 day, +1% price, Volume, Open Int, Bid, Ask; quantity +/-; Quantity Sync; Entry Price mark/expensive; Add Call, Add Put, Flip, Transform (dialog "Transform Current Trade": included types/versions/bet types, sort, Reposition button).
- Not in the public API (it is a calculator on top of chain quotes + greeks). Any options pricing library plus a chain snapshot reproduces it.

### /news-feed and /news ("The Blubber")
- News Feed: headline list (time, age in minutes, headline, ticker chips, source tag MKT or UW, and UW rows have MORE / TRUMP links), Filter headlines box, "Major only" toggle (URL major_only=true), reset filters, chime toggle (not pressed). limit=100 per page.
- UW-tagged rows are UW's own generated events ("Donald J Trump has just disclosed new stock trades ... + 95 more"). MKT rows are a wire/aggregated headline feed.
- Featured News (/news): UW's own article list (title + timestamp), editorial.
- API: /api/news/headlines exists in the public API (headline feed); the "major" flag is a field there.

### /trade (Paper Trading)
- A social paper-trading app: account box ("Anonymous Whale", account select "Primary", cash $10,000,000, stocks, options, total), "Take a new position" form (Options: ticker, Call/Put, expiration, number of contracts, Buy/Sell, due diligence text; Stocks: ticker, number of shares, Buy/Short, due diligence; Submit), public feed "Recent Trades" of all users (cost basis, returns, initial/current/exit price, opened/closed, likes, comments), filter popover (symbol, sentiment All/Bull/Bear, Reset/Apply), Rankings (Leaders / Worst Performing), Activity (Most Discussed / Most Liked).
- Header icons: home /trade, notifications /trade/notifications, settings /trade/pages/settings (not opened: profile/account page).
- No position was submitted: a paper trade is published to the public feed. avo has no paper positions.
- Relevance: none.

### /backtesting/portfolios (Portfolio Backtesting)
- List shows five sample backtests as cards with a holdings treemap (Cooke Bieler LP, Two Sigma Advisers LP, JPMorgan Chase Co, BlackRock Inc, nancy-pelosi) and the tile "You haven't created any backtests yet. CREATE A BACKTEST PORTFOLIO". avo has none of his own.
- Detail (/backtesting/portfolios/<uuid>, nancy-pelosi opened): BACK, CLONE (not pressed: creates a portfolio), notice about adjusted start date; Historical Performance chart (portfolio vs benchmark); Stats (start/end value, total % return, avg/max/min yearly % return, avg yearly/monthly cash return, total cash return, rebalancing, operation dates, periodic deposits); Composition treemap by sector; Assets table (ticker, % return, value change, start value, cash return, cash deposits, value gain, end value, start/end share price, shares quantity, % allocation start -> end, sector); Asset Performance bars; Cashflow bars; Drawdown vs SPY; Annual Returns table (+benchmark value / % / cash change); Seasonality; Yearly High/Low; Monthly Returns table and chart; "AI Review" paragraph (generated commentary on concentration and diversification).
- New Backtest form (/backtesting/new): portfolio name, duration 1y/2y/5y/10y/15y/20y, benchmark ticker (default SPY), periodic deposits None/Monthly/Quarterly/Yearly, rebalance portfolio, assets rows (ticker, allocation type value/quantity/percentage, start value), use even distribution, + ADD ASSET, CREATE PORTFOLIO ("We'll process your portfolio and email you when it's done"). Not submitted.
- This is a buy-and-hold portfolio backtest on daily prices, unrelated to options flow. RevenueChaser's own backtest work (#1250, #1257) does not depend on it.

