# UWdependency — Unusual Whales UI survey (Task 2.1)

Thread: "Explore UW dashboard and screenshot it" (account A, 21 Nov 2026).
Scope: UI exploration + screenshots only. Code/provider analysis lives in the thread
"Plan migration away from Unusual Whales".

## Status

| Part | State |
|---|---|
| Public API path list | done — `public_api_paths.txt` (241 paths, `GET https://api.unusualwhales.com/api/openapi`, fetched 2026-11-21 12:59 UTC) |
| Browser survey of unusualwhales.com | BLOCKED — no Chrome browser connected to this thread; needs avo's logged-in Chrome on the Dell |
| Per-feature folders + notlar.md | pending browser |
| UI-only feature list | pending browser (compared against `public_api_paths.txt`) |

## Planned folder layout

`UWdependency/<feature>/` with `notlar.md` (full URL + timestamp per screenshot) in each:
flow/, alerts/, screener/, gex/, dark-pool/, congress/, market-map/, options-chain/,
volatility/, plus whatever else the live nav shows.

## Public API surface, by prefix (for the UI-only comparison)

stock 63, market 13, crypto 13, predictions 10, private-markets 9, portfolio 8,
option-trades 8, futures 8, congress 8, watchlists 6, shorts 6, politics 6,
institution 6, companies 6, politician-portfolios 5, etfs 5, volatility 4,
seasonality 4, screener 4, option-contract 4, insider 4, flex-options 4, alerts 4,
options-pulse 3, forex 3, earnings 3, darkpool 3, potus 2, lit-flow 2, institutions 2,
group-flow 2, digital-currencies 2, analytics 2, and one each for stock-directory,
short_screener, sec-filings, option-activity, news, net-flow, economy, commodities, calendar.
