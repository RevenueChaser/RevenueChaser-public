# Console (command line)

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 10 (kept outside the repository, see ../README.md).

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `01_console_feed_and_a-z-preview.jpg` | https://unusualwhales.com/console | 21.11.2026 16:45:54 |
| `02_commands-faq_all-229.jpg` | https://unusualwhales.com/console | 21.11.2026 16:45:54 |
| `03_settings_general.jpg` | https://unusualwhales.com/console | 21.11.2026 16:47:48 |
| `04_settings_filters_alerts-and-watchlists.jpg` | https://unusualwhales.com/console | 21.11.2026 16:47:48 |
| `05_settings_templates_field-tokens.jpg` | https://unusualwhales.com/console | 21.11.2026 16:47:48 |
| `06_settings_trade-alert-import.jpg` | https://unusualwhales.com/console | 21.11.2026 16:47:48 |
| `07_cmd_moso_most-active-options.jpg` | https://unusualwhales.com/console | 21.11.2026 16:47:48 |
| `08_cmd_top-equity_tape.jpg` | https://unusualwhales.com/console | 21.11.2026 16:47:48 |
| `09_cmd_unbu_unusually-bullish.jpg` | https://unusualwhales.com/console | 21.11.2026 16:47:48 |
| `10_ticker-menu_NVDA.jpg` | https://unusualwhales.com/console | 21.11.2026 16:47:48 |

## Other files in this folder

- `commands_all-229.md`

## Notes (what the page shows, buttons pressed, nearest API path)

### /console — second pass 21 Nov 2026
Layout: left = live alert tape of avo's own custom alerts (on 21 Nov only "Insider Trade" rows: time, INSIDER, ticker, person, bought/sold, shares @ price, ($ value), STAKE %, alert name chip; each row has a "Delete alert" control at the right edge, never pressed). Right = detail pane. Bottom = command box. Header: Live indicator, Settings, Filter, Reload, Clear, Hide, Pop out (Clear and Pop out not pressed).

### Commands
- Full list in `commands_all-229.md` (229 commands in 15 groups, read from the Commands / FAQ pane).
- Ran three read-only commands:
  - `/moso` -> "Most Active Options" grid: Last (time), Ticker, Contract (strike, put/call, expiry), DTE, Stock, %OTM, Avg, Low-High bar, Last, Chg %, Daily %, Vol, OI, OI +/-, OI +/- %, Prem, IV, IV Chg, % Total ..., Sector, days to earnings. 118 rows, "Open in options screener" link. This is the Discord bot's highest-volume-contracts data.
  - `/top @equity` -> "Top Trades & Sweeps": Tape / Grid toggle, Sort select (Premium ...), Scope select (@EQUITY Stocks & ADRs ...), Investor lists, Filters, Download (not pressed), Open full tape. Tape row = size, ticker, expiry, strike, Puts/Calls, trade price, time to the ms, OPENING tag, quote, venue, stock ref, delta, Delta$, IV, Vega, Gamma, TV, Edge, Est impact (shares), detail link. Multi-leg rows carry structure name (Call Spread, MultiLeg), Ask/Bid, LONG/SHORT, FLOOR/AUCTION, net debit/credit, legs count.
  - `/unbu` -> "Unusually Bullish" grid (same columns as /moso), 54 rows; definition "OTM call buyers, $500K+ premium".
- Typing a ticker (`NVDA`) opens the Ticker Menu: 1 Top Trades and Sweeps, 2 Most Active Stock Options, 3 Top OI Changes, 4 Top OI Positions, 5 Option Bucket Report, 6 Put/Call Sentiment, 7 Option Volume Breakdown, 8 Recent Trades, 9 Color, 10 News, 11 Spreads, 12 Historical Range Data, 13 13f Option Holders, 14 Underlying Blocks, 15 Top Strategies, 16 Ratings; "+ PIN".
- Not run: anything that writes (/presets, /del, /mute, /basket, /pin, /import, /template, option triggers such as `googl 1000`).

### Settings pane
- General: Single pane, Newest at bottom, Text size Small/Default/Large, Monospace feed, Color calls and puts, Mute incoming alerts. Nothing changed.
- Filters: which of avo's alerts stream (Politician trades 1, Insider trades 1, Stock 1, Chat 1 = his 4 rules) and watchlist scoping (his 6 stock watchlists with ticker counts 45/48/46/49/49/49, option watchlist Bookmarks 1 contract).
- Templates: "Trade-Alert style prints" toggle; per-alert subject/body templates with colour tags and field tokens: {contract} {root} {strike} {put_call} {pc} {expiry} {expiry_ddmmmyy} {dte} {size} {price} {avg_fill} {premium} {volume} {open_int} {vol_oi} {otm} {multi} {ask_vol} {bid_vol} {side} {side_color_conditional} {ba} {ba_text} {spot} {delta} {gamma} {theta} {vega} {rho} {theo} {iv} {iv_pct} {iv_change} {iv_chg} {oi_change} {oi_change_pct} {hedge_shares} {hedge_usd} {hedge_dir} {exchange} {flags} {cond} {hilo} {opening} {closing} {sweep} {cross} {floor} {auction} {late} {extended_hours} {odd_lot} {exdiv} {arbitrage} {volatility} {china} {sentiment} {earnings_soon} {etf} {index} {rule} {nbbo_bid} {nbbo_ask} {nbbo_bid_size} {nbbo_ask_size} {bexch} {aexch} {prev_iv} {type} {custom_alert_tag} {custom_alert_name} {symbol} {watchlists} {investor_list} {date} {time} {multi_vol} {multi_leg_vol_ratio} {executed_at} {next_earnings} {rv21} {rv42} {rv84} {rv21_pct} {rv42_pct} {rv84_pct} {underlying_symbol} {iv_high} {iv_low} {close} {report_flags} {spot_chg} {spot_chg_pct}. This token list is the field dictionary of one option-trade alert row.
- Trade Alert: paste Trade Alert's /list output to import rules as custom alerts (not used).

### Migration relevance
- HIGH for avo's "unusual-command-line" item: the Console is UW's command line. What it adds over the pages is (a) the per-print greeks ranking (vega, dollar gamma, gross notional, Edge vs theoretical value), (b) preset thresholds stated in plain words, (c) the alert row field dictionary above.
- Inputs it needs that a self-build must source: OPRA trade prints with condition codes and venue, NBBO at trade time, per-contract IV/greeks, OI; "TV/Edge" needs a fitted smile per expiry.

