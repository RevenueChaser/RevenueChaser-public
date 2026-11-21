# Custom Alerts

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 19 (kept outside the repository, see ../README.md).

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `01_feed_my-alerts_settings-popover.jpg` | https://unusualwhales.com/custom-alerts | 21.11.2026 16:25:02 |
| `02_feed_style-detailed.jpg` | https://unusualwhales.com/custom-alerts | 21.11.2026 16:25:20 |
| `03_feed_filters-menu.jpg` | https://unusualwhales.com/custom-alerts | 21.11.2026 16:25:20 |
| `04_feed_preset-alerts.jpg` | https://unusualwhales.com/custom-alerts | 21.11.2026 16:25:32 |
| `05_feed_mute-ticker-popover.jpg` | https://unusualwhales.com/custom-alerts | 21.11.2026 16:25:45 |
| `06_information-drawer.jpg` | https://unusualwhales.com/custom-alerts | 21.11.2026 16:25:45 |
| `07_active_four-alerts.jpg` | https://unusualwhales.com/custom-alerts/active | 21.11.2026 16:25:55 |
| `08_active_insider-trade_expanded.jpg` | https://unusualwhales.com/custom-alerts/active | 21.11.2026 16:26:13 |
| `09_active_unusual-options-volume_filter-details.jpg` | https://unusualwhales.com/custom-alerts/active | 21.11.2026 16:26:13 |
| `10_create_landing.jpg` | https://unusualwhales.com/custom-alerts/create | 21.11.2026 16:26:42 |
| `11_create_visual-builder_type-tree.jpg` | https://unusualwhales.com/custom-alerts/create | 21.11.2026 16:26:51 |
| `12_create_visual-builder_flow-alerts-form.jpg` | https://unusualwhales.com/custom-alerts/create | 21.11.2026 16:29:15 |
| `13_create_templates.jpg` | https://unusualwhales.com/custom-alerts/create | 21.11.2026 16:29:15 |
| `14_create_formula.jpg` | https://unusualwhales.com/custom-alerts/create | 21.11.2026 16:29:29 |
| `15_create_formula_stream-types.jpg` | https://unusualwhales.com/custom-alerts/create | 21.11.2026 16:29:40 |
| `16_create_formula_fields-drawer.jpg` | https://unusualwhales.com/custom-alerts/create | 21.11.2026 16:29:40 |
| `17_create_formula_examples.jpg` | https://unusualwhales.com/custom-alerts/create | 21.11.2026 16:30:06 |
| `18_create_formula_start-here.jpg` | https://unusualwhales.com/custom-alerts/create | 21.11.2026 16:30:06 |
| `19_create_ask-mr-whale_no-prompt.jpg` | https://unusualwhales.com/custom-alerts/create | 21.11.2026 16:30:55 |

## Other files in this folder

- `alert-types_all-29-forms.md`
- `formula-fields_option-trades.md`

## Notes (what the page shows, buttons pressed, nearest API path)


### Custom Alerts - second pass, raw notes, 21 Nov 2026 ~16:25 Amsterdam
Header: Feed | Active [4] | Create Alert | "Get push alerts on mobile" Android / iOS (external, not pressed) | (?) information drawer.
### Feed (/custom-alerts, param source=mine | preset)
- My Alerts | Preset Alerts. Category chips with counts (All [50], Stocks [50]; preset adds Macro, Other). Ticker search, filter icon, bell
  (= "Mute a ticker": ticker, 1h/4h/1d/1w/Forever, which alert, Mute - not pressed), gear, pager arrows. Each row has "Delete alert" (not pressed).
- Gear popover: FEED STYLE Condensed | Tape | Detailed (tried, restored to Condensed); Mobile Alerts toggle (off, untouched); Notification Sound.
- Filter menu: "Today's alerts only" toggle; one checkbox group per alert type (Politician trades 1, Insider trades 1, Stock 1, Chat 1); Reset.
- Row shape, insider: time, INSIDER tag, ticker, person, bought/sold, shares @ price, ($ value), STAKE % change, alert name chip.
- Preset feed also carries POTUS schedule rows (location, coverage; "TRUMP NEWS + SCHEDULE") and NEWS rows ("Donald J Trump has just disclosed
  new stock trades..."). "Preset Alerts are delayed for non-subscribers."
### Information drawer (text read in full)
- Four ways to create: Templates, Formula Builder (filter language like the Options Flow sidebar, e.g. "type = 'call' and prem > 25000",
  "side = 'ask' and dte < 7 and ivol > 0.5", "delta between 0.4 and 0.6 and vol / oi > 2"; target stream chosen in the status bar: Option
  Trades, Flow Alerts, ...), Visual Builder (trigger type Options, Stocks, Macro...; "For" = all tickers / one ticker / a watchlist / portfolio),
  Mr. Whale (plain English). Drafts are kept in the browser. Links: Custom Alerts Primer and three help articles (external, not opened).
### Active (/custom-alerts/active) - avo's four rules (also read through the UW connector, get_custom_alerts)
| name | type | rule | created | fired per day 16-20 Nov |
| Politician Trade | politician_trades | @all | 5 Nov 2026 | 20, 12, 0, 13, 23 |
| Insider Trade | insider_trades | premium >= 500000 | 5 Nov 2026 | 24, 90, 106, 67, 55 |
| Unusual Options Volume | stock | Common Stock + ADR, min 30D avg option volume 5000, min market cap 100M, option volume / 30D avg >= 3 | 5 Nov 2026 | 10, 11, 8, 15, 13 |
| Chat Mentioned | chat | self_mentioned | 16 May 2026 | 0 |
  None sends email; all "active".
- Row controls: checkbox, expand (shows that rule's fired rows), fired count + mini bars, type, status dot, Filter details (dialog with the
  rule's fields, Edit / Duplicate / Delete, and a share link), Share, Edit, Delete. Pressed only expand and Filter details.
- "Type" control filters the list: All types, Chat, Insider trades, Politician trades, Stock alert.
- Migration relevance: Insider Trade and Politician Trade rules can be rebuilt from Form 4 and the congressional disclosures; "Unusual
  Options Volume" needs per-ticker option volume against a 30-day average (IBKR/Cboe). These three rules are what avo actually receives.
### Create (/custom-alerts/create; params mode=templates, noti_type=<type>)
- Four cards: Templates ("Start from curated presets"), Visual Builder ("Build from scratch, no code"), Formula ("Write advanced logic by
  hand"), Ask Mr Whale ("Describe it in plain language"; no prompt sent).
- Visual Builder: type tree Options (7) / Stocks (14) / Macro & Other (7) / Predictions (1) = 29 types. Every form was opened and its fields
  read: see alert-types_all-29-forms.md. "Stock Talk" says "Subscribe to unlock". No Create pressed.
- Templates (13): Hot Contract - Bid Side / Ask Side (Contract alert), Interval (5 min) - Ask Side / Bid Side (ask- or bid-side vol > OI inside
  5 minutes), Analyst Rating ($25B+ market cap), Unusual Options Volume (stock/ADR, $10M+ cap, 5000 daily option volume, 3x normal),
  Unusual Stock Volume ($10M+ cap, $1+ price, 10000 daily volume, 3x normal), Insider Trade ($500,000+), Market Tide Cross (net call and put
  premium lines cross), Fed Speakers, Trump Headline, Follow Nancy, Politician Trade. "+" loads one into the builder (not pressed).
  avo's Insider Trade, Politician Trade and Unusual Options Volume rules are these templates (the last one with a $100M cap floor).
- Formula: TYPE dropdown = Option Trades, Option Contracts, Interval Flow, Flow Alert, Multi-leg Trade, FLEX Consolidations, Stock Prints,
  Ticker Flow, News, Trading Halts; name box; rule box; Create (not pressed); "Help & Examples" / FIELDS drawer with tabs Start here | Fields |
  Examples. Full field dictionary for Option Trades: formula-fields_option-trades.md.

