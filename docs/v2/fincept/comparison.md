# Fincept beside RevenueChaser: what is worth having

Owner, 20 Nov 2026: "Yani işimize ne yaparsa, bizim kod ile karsilastir bakalim". One row per Fincept feature or
source that could matter to us. Fincept at commit `914134d`; ours at `main` `7bfbec1`. Reading marks as in the
[README](README.md). "Worth having" is the reviewer's opinion; the owner decides.

## Interface

| Fincept has | We have | Which is better, why | Worth having in v2 |
|---|---|---|---|
| A panel grid with one panel anatomy, saved layouts `[READ]` `images/Dashboard.png` | 19 boards, each its own generated HTML page in an iframe `[READ]` `app/dashboard.py` | Theirs: one look, panels can be rearranged, a new panel costs little | **Yes.** It is the owner's chosen structure and fits decision 2 (server-described boards) |
| A symbol search and command bar over 614 entries `[READ]` run log, `CommandBar` | A ticker box inside some boards | Theirs | **Yes** |
| One research screen per symbol with 14 subject tabs `[READ]` `images/EquityResearch.png` | The facts exist per board; `/api/ticker/<t>` returns JSON, no page `[READ]` `app/dashboard.py:1578` | Theirs as a screen; ours as data (13F history, value chain, relatedness are not in theirs) | **Yes**, decision 4 |
| Source, time and delay in every panel footer `[READ]` | Freshness on the data health board `[READ]`; per panel `[NOT CHECKED]` | Theirs | **Yes**, cheap |
| Price alerts on a watch list (`WatchlistAlertService`) `[READ]` | Watch lists, no alerts | Theirs | **Yes**, it is the alert lane the owner asked for |
| Native desktop only, no web, no phone `[READ]` `ARCHITECTURE.md` section 1 | Web, reachable from the phone | Ours for the three targets | Nothing to take |
| A sign-in to their server before any screen `[READ]` run of 20 Nov 2026 | No account; tailnet only | Ours for one owner | No |

## Data and analytics

| Fincept has | We have | Which is better, why | Worth having in v2 |
|---|---|---|---|
| Quotes and history from Yahoo, fetched when a screen opens `[READ]` | Daily bars since 1984 for the whole universe, Compustat and other sources, in `prices.duckdb` `[READ]` `docs/data_architecture.md` | Ours: a record, adjusted, auditable. Theirs is live-ish but keeps nothing | Their delayed live quote, only for the alert lane |
| Fundamentals from Yahoo and SEC company facts `[READ]` | Compustat-based fundamentals and revisions, SEC forms `[READ]` `docs/data_architecture.md:62` | Ours | No |
| Option chain: Cboe delayed first, Yahoo fallback, Databento when paid `[READ]` | UW for chains, flow and gamma; Cboe for index history only `[READ]` `rcdata/build/sources/cboe.py` | Theirs is free; ours has trade direction (flow) that Cboe lacks | **Yes, as the route off UW**: Cboe chain first. Issue #418 holds the open measurements |
| Ownership tab from Yahoo holders `[INFERRED]` from the tab name and the Yahoo backing | 13F and N-PORT built from SEC filings, with history `[READ]` `rcdata/build/ownership` | Ours | No |
| Relationship map from Yahoo data `[READ]` `DATAHUB_TOPICS.md` | Value Chain from filings and profiles, Relatedness, Co-movement | Ours in depth; theirs draws it better | The drawing, not the data |
| Screener on Yahoo's screener endpoint `[READ]` | Three scored screens over our own store (Asymmetric Growth, Swing Potential, LEAPS) | Ours for our rules; theirs for free-form filters | A free-form filter over our own store, later |
| News from RSS with local sentiment and clustering `[READ]` | News board with headlines, tape and an X check `[READ]` `module_news/` | `[NOT CHECKED]` side by side | Clustering of duplicates, if ours lacks it `[NOT CHECKED]` |
| Macro: about 90 keyless and keyed connectors `[READ]` `data-sources.md` | FRED, BLS, Fed, Treasury, CFTC in the builder `[READ]` `rcdata/build/sources/` | Theirs is far wider; ours is what the boards use | Only a source a board needs. The catalogue is the menu to pick from |
| Backtesting screen wrapping existing engines `[READ]` | Hit Rate board | Theirs is wider | Later; the owner's rule puts model tuning after the open work |
| 16 brokers, live and paper trading `[READ]` | None, by rule: IBKR for market data only | Not comparable | No |
| 40+ MCP tools over its services `[READ]` | An MCP server for the News board `[READ]` `docs/data_retrieval.md:264` | Theirs is wider | One read-only tool set on the v2 door, later |

## Data layer

See [`data-layer.md`](data-layer.md). In one line each:

| Fincept has | We have | Worth having in v2 |
|---|---|---|
| One table of every topic's TTL and refresh rule | Rules in builder code | **Yes**: a generated freshness table |
| One JSON catalogue of every connector | `rcdata/caps.py` plus the needs catalogue | **Yes**: one source catalogue |
| The reply names the source that answered and the fallback reason | `[NOT CHECKED]` on boards | **Yes** |
| Push-only, coalesced topics for live feeds | None | **Yes, for the alert lane only** |
| A TTL cache, no history | Build-then-swap files, previous file kept, shrink guard | No. Ours stays |

## Sources in their catalogue that we do not call

`[INFERRED]` from `data-sources.md`, by name match only, so a source we reach under another name is missed. Of 204
connectors, the ones a US equity research store could use and that need no key:

| Source | What it gives | Could serve |
|---|---|---|
| Cboe delayed option chain (inside `deriv_market.py`, not a catalogue row) | full chain with greeks and open interest, 15 minutes delayed | SPX Gamma, Implied Probability, the route off UW |
| SEC company facts | XBRL facts per company | a check on fundamentals |
| Polymarket, Kalshi | event odds | macro context on the Welcome board |

Paid ones that would matter if a budget existed: Databento (option tape with trade side, the one thing Cboe and IBKR
do not give) and Polygon. Neither is proposed here.
