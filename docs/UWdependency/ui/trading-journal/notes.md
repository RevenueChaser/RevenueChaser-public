# Trading Journal / Portfolios

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 14.

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `01_overview_empty-state_top.jpg` | https://unusualwhales.com/trading-journal | 21.11.2026 16:12:56 |
| `02_overview_scroll1_feature-cards.jpg` | https://unusualwhales.com/trading-journal | 21.11.2026 16:13:04 |
| `03_overview_scroll2_feature-cards.jpg` | https://unusualwhales.com/trading-journal | 21.11.2026 16:13:04 |
| `04_overview_scroll3_brokers-list.jpg` | https://unusualwhales.com/trading-journal | 21.11.2026 16:13:04 |
| `05_holdings_empty-state.jpg` | https://unusualwhales.com/trading-journal/holdings | 21.11.2026 16:13:46 |
| `06_risk_empty-state.jpg` | https://unusualwhales.com/trading-journal/risk | 21.11.2026 16:13:46 |
| `07_asset-breakdown_empty-state.jpg` | https://unusualwhales.com/trading-journal/trades | 21.11.2026 16:13:46 |
| `08_trade-analytics_empty-state.jpg` | https://unusualwhales.com/trading-journal/analytics | 21.11.2026 16:13:46 |
| `09_trade-rank_empty-state.jpg` | https://unusualwhales.com/trading-journal/profile | 21.11.2026 16:14:14 |
| `10_alerts_empty-state.jpg` | https://unusualwhales.com/trading-journal/alerts | 21.11.2026 16:14:14 |
| `11_accounts_connect-broker.jpg` | https://unusualwhales.com/trading-journal/accounts | 21.11.2026 16:14:14 |
| `12_accounts_settings-tab_streamer-mode.jpg` | https://unusualwhales.com/trading-journal/accounts | 21.11.2026 16:14:29 |
| `13_discover_leaderboard.jpg` | https://unusualwhales.com/trading-journal/discover | 21.11.2026 16:14:47 |
| `14_following_empty.jpg` | https://unusualwhales.com/trading-journal/following | 21.11.2026 16:14:47 |

## Notes (what the page shows, buttons pressed, nearest API path)

### Trading Journal (BETA, nav group tagged "New") - raw notes, 21 Nov 2026 ~16:13 Amsterdam
Nav group (expandable, no own link): Overview /trading-journal, Holdings /trading-journal/holdings, Risk /trading-journal/risk,
Asset Breakdown /trading-journal/trades, Trade Analytics /trading-journal/analytics, Trade Rank /trading-journal/profile,
Alerts /trading-journal/alerts, Your Accounts /trading-journal/accounts.
State on avo's account: no broker linked -> every page is the empty state "Link your first account".
Buttons seen: "How it works" (video), "Link an account" (NOT pressed: account linking), "Browse traders", "Find a ticker" search.
What the product is (from the page's own cards): broker-linked read-only journal. Trades/holdings/history sync; returns vs SPY/QQQ/IWM on
the same deposits; wheel campaigns and rolls; rule monitor (caps per line/name/theme, 30% gap test, breaches in 90 days); P&L calendar;
expected path with sigma bands and CUSUM alarm; crash scenarios with options repriced, margin, max loss; win rate/profit factor/expectancy by
ticker/strategy/holding period/time of day; Trade Rank after 90 days; public profile, leaderboard "Discover", followers get alerts;
alerts on held tickers (earnings, unusual flow, big option trades, insider buys, news); dividend tracking; cash ready to invest.
Brokers: Interactive Brokers, Fidelity, Webull, Robinhood, Schwab, E*Trade, Vanguard, Chase, Wells Fargo, Zerodha, BUX, CommSec, Public,
Stake, Trading 212, Upstox, Wealthsimple "and 19 more"; or file import (IBKR activity statement, Robinhood activity, NinjaTrader, Tradovate).
Migration relevance: NOT used by RevenueChaser (nothing linked). UI-only; the MCP server exposes get_my_* tools for it, public REST API: check.
Sub-pages visited: holdings, risk, trades, analytics, profile, alerts all show the same "Link your first account" empty state (only the first
feature card differs). /trading-journal/accounts: tabs Accounts | Settings. Accounts = "Connect a broker" (8 shown, "Show all 35 brokers",
search, "Import a file"); Connect / Import NOT pressed. Settings tab = Privacy: Streamer mode with Hide account names / Hide P&L / Hide balances
toggles (not toggled).
/trading-journal/profile has tabs Trade Rank | Discover (/trading-journal/discover) | Following (/trading-journal/following).
Discover: public leaderboard of broker-verified portfolios ranked by Sharpe; needs 90 days history and $5,000 average balance; nightly update.
Controls: 3M/YTD/1Y, Sort (Risk-adjusted, Return, Size-weighted, Win rate, Followers), filter (All/Options/Stock traders, $250k+, $1M+ ...),
search @handle; columns # / Trader / Trend / Return / Sharpe / Max drawdown / Win rate; "Follow" NOT pressed. Only 1 trader listed.
Following: empty ("You're not following anyone yet"), "Browse the leaderboard", "Discover traders".

