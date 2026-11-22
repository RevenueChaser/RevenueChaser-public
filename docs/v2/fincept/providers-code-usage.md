# Fincept providers: where they are on homesrv, how Fincept uses them, and ETF holdings

Written 22 Nov 2026 by the homesrv thread, read-only (no network, no provider call, no secret read).
Reading marks as in [`README.md`](README.md): `[READ]` the statement is in a file that was opened on this box and
the file is named; `[INFERRED]` a conclusion; `[NOT CHECKED]` nobody looked.

## 1. Where it is — and what is not here

**Fincept's source tree is not on homesrv.** A whole-disk search by name found no checkout:
`find / -iname '*fincept*'` returns only the notes and the UI walk below. `[READ]`

| What | Path on homesrv | What it is |
|---|---|---|
| The notes read from Fincept's source | `/srv/life/apps/RevenueChaser/docs/v2/fincept/` | 8 markdown files, incl. the full 204-connector catalogue |
| The live UI walk (20 screens, UIA dumps) | `/srv/life/apps/RevenueChaser/docs/v2/fincept_walk/` | PNGs, `uia_*.txt`, `notes.md`, `widgets.csv` |
| The same walk as it arrived | `/mnt/data/inbox/fincept_walk/` | same files + `fincept_walk_2026-11-21.zip` |
| Copies in scratch clones | `/srv/tmp/work/{v2mockb,rc-docs-v2,rc-1347,...}/docs/v2/fincept/` | working copies, not the record |

So every code-level statement below comes from those notes, which were written while Fincept's source *was* open
(commit `914134d`, release 4.5.3, AGPL-3.0) and which cite its files by name and line. **A fresh read of Fincept's
own code cannot be done from this box** — it needs the repo cloned, which is a network fetch and outside the
read-only scope given.

## 2. How Fincept uses its providers, from the code

### The shape of the provider layer

- **A connector is a Python script plus a JSON row, not a class.** All 204 connectors are described in one file,
  `fincept-qt/resources/data_connectors.json`: name, script, region, key-or-not, the environment variable names,
  the commands it answers, a sample reply and a TTL. `[READ]` `data-sources.md` header. The C++ side runs the
  script as a child process; there is no per-provider adapter class to write.
- **The screen never calls a provider.** A panel subscribes to a *topic*; the DataHub fetches only if the cached
  value is stale, and one fetch serves every subscriber ("one-fetch/many-subscribers").
  `[READ]` `ARCHITECTURE.md` 7.1, via `data-layer.md`.
- **Freshness is one policy per topic, in one table**, not scattered through the fetchers: `ttl_ms`,
  `min_interval_ms`, `refresh_timeout_ms`, `push_only`, `coalesce_within_ms`.
  `[READ]` `src/datahub/TopicPolicy.h`, `fincept-qt/docs/DATAHUB_TOPICS.md`.
- **Rate limits are declared by the producer**: `max_requests_per_sec` on the producer, `min_interval_ms` on the
  topic. `[READ]` `src/datahub/Producer.h:30`. No request counter and no published-limit citation — ours
  (`rcdata/caps.py`) counts every request and cites the URL each number came from. `[READ]`
- **Cache**: a SQLite TTL key/value store in its own file, separate from the main database. It is a cache, not a
  record: there is no "what did we know on that day". `[READ]` `data-layer.md`.
- **Failure**: the hub keeps serving the **last known good** value and retries on a backoff ladder.
  `refresh_timeout_ms` clears the in-flight flag so a hung producer cannot pin a topic.
  `[READ]` `ARCHITECTURE.md` 6.3, `src/datahub/DataHub.cpp:23-47`.
- **Fallback is per script and it is named in the reply.** The option-chain script tries Cboe's public delayed feed
  first and Yahoo second, and the reply carries `source` and `fallback_reason`.
  `[READ]` `scripts/derivatives/deriv_market.py:1-25`.
- **Keys**: an encrypted local store; 22 named keys are injected per call and *every other secret-shaped variable is
  stripped from the child process*. `[READ]` `ARCHITECTURE.md` 6.4.
- **The user is told, on the panel**: every table footer says source, as-of time and delay — "as of 02:33 · delayed
  up to 20 min · Yahoo Finance screener". `[READ]` `QuoteTableWidget.cpp:164-167`.

### Which data comes from which provider

`[READ]` `source-usage.md`, built by counting the service singletons each screen calls and the hosts each service
names (`grep` at commit `914134d`).

| Need | Free, keyless, what ships | Paid / keyed upgrade |
|---|---|---|
| Quotes, history, FX, search, screener | **Yahoo via `yfinance`** — the whole equity core, 10 refs in `services/markets` | broker account, Polygon, Tiingo, Databento |
| Fundamentals | Yahoo + SEC company facts (`sec_company_facts.py`) | FMP, SimFin, Intrinio, EODHD |
| Filings | SEC EDGAR (`fincept_mcp/edgar/main.py`) | — |
| Option chain | **Cboe delayed first, Yahoo fallback** | Databento, broker (real time, depth, surface history) |
| Yield curve / futures | home.treasury.gov, Yahoo | — |
| Macro | Fed, Treasury, World Bank, IMF, DBnomics, OECD | FRED/BLS/BEA/EIA (free keys), Trading Economics |
| News | RSS (BBC, CNBC, Dow Jones, SCMP, Investing.com, FT), sentiment computed locally | NewsAPI |
| Symbol master, calendars, geopolitics, maritime | — | **Fincept's own server** behind an account, metered in credits |

`[INFERRED]` The pattern worth naming: **nothing in the open edition needs a paid key to open a screen.** Every key
is an upgrade the user plugs in, and the panel says which source answered.

## 3. ETF holdings (constituents)

**In Fincept's catalogue, only two rows name it, and both need a key:** `[READ]` `data-sources.md:154,144`

| Connector | Key | What the row says |
|---|---|---|
| OpenBB (`openbb_data.py`) | `OPENBB_API_KEY` | "stocks, macro, alternatives, **ETF holdings**, economic calendar" |
| Financial Modeling Prep (`fmp_data.py`) | `FMP_API_KEY` | "quotes, profiles, price history, financial statements and ratios, **ETFs**, crypto, ne…" |

Near misses, for completeness: Cboe gives **index** constituents, not ETF holdings (`data-sources.md:137`); FMP's
second row gives **institutional** holdings (13F-shaped, `:143`); Twelve Data gives ETF **OHLCV** only (`:165`).
`[READ]`

**RevenueChaser already has this, and from a better source.** Our ETF holdings come from SEC **N-PORT**, free and
keyless, with history: `rcdata/build/ownership/nport.py`, `rcdata/build/spine/funds.py`,
`rcdata/build/spine/etf_class.py`, tested by `rcdata/tests/test_spine_etf_holdings_sweep.py` and
`test_ownership_nport.py`. `[READ]` So on ETF constituents Fincept has nothing to add — it buys with a key what we
file-read for free. `[INFERRED]`

## 4. All 204 providers — where the list is

The full list already exists on this box and is not repeated here:
**[`data-sources.md`](data-sources.md)** — one row per connector, grouped in 11 categories, each row giving name,
script, region, key-or-not, the key variable names, the command count, and whether RevenueChaser calls the same
source. Generated from `data_connectors.json` at commit `914134d`.

Totals `[READ]`: **204 connectors — 145 keyless, 59 keyed, 4 marked `broken`.**

| Category (= the data-type grouping) | Connectors | No key | Key |
|---|---|---|---|
| Macro & Central Banks | 45 | 41 | 4 |
| Government & Statistics | 48 | 40 | 8 |
| Markets & Equities | 34 | 17 | 17 |
| Crypto & DeFi | 12 | 6 | 6 |
| China & Asia | 5 | 4 | 1 |
| Energy, Commodities & Climate | 28 | 15 | 13 |
| Shipping | 3 | 0 | 3 |
| Geospatial & Geopolitics | 14 | 10 | 4 |
| News & Alternative Data | 6 | 5 | 1 |
| Academic & Research | 8 | 6 | 2 |
| Other | 1 | 1 | 0 |

### The 10 sources we already call

`[READ]` the catalogue's own last column — 11 rows, 10 distinct sources:
Federal Reserve → `rcdata/build/sources/fed.py` · FRED (2 rows) → `fred.py` · BLS → `bls.py` ·
US Treasury Fiscal Data → `treasury.py` · Alpha Vantage (2 rows) → `rcdata/caps.py`, day cap 25 ·
Cboe (2 rows) → `cboe.py` (index history only) · CFTC COT → `cftc.py` · OpenFIGI → `core/providers/openfigi.py` ·
SEC EDGAR (2 rows) → `core/providers/sec_edgar.py`, `rcdata/build/sec_forms` ·
Yahoo → `rcdata/build/sources/yahoo.py`, `core/providers/yfinance.py`.

Everything else in the 204 is a source we do not call today. `comparison.md` already picks out the keyless ones a US
equity research store could use: the **Cboe delayed option chain** (the route off UW, issue #418), **SEC company
facts** as a fundamentals check, and **Polymarket / Kalshi** event odds for macro context.

### What this list cannot tell you

- The catalogue's "what it is" column is **truncated at about 110 characters in 116 of the 204 rows** `[READ]`, so a
  capability named late in a long description is invisible here. The ETF scan in §3 is a scan of those truncated
  descriptions, not of the providers' real APIs: yfinance, EODHD and Twelve Data all expose fund-holdings endpoints
  that this file does not mention. `[INFERRED]`
- `data_connectors.json` itself — the authoritative file, with each row's TTL and sample reply — **is not on this
  box.** Re-deriving anything per row needs the repo.
- The catalogue says *whether* a key is needed, never what it costs. "Key" means an account, free tier or paid.
  Free-vs-paid per provider is `[NOT CHECKED]`.

## 5. For RevenueChaser v2's provider layer

Ordered by cost to us, cheapest first. The first four are already in
[`data-layer.md`](data-layer.md) §"What to take"; they are repeated because they are the provider-layer ones.

1. **Name the source on the panel.** Source, as-of time, delay in the footer of every table the number sits in. The
   v2 board payload already carries `as_of` and provenance — this only makes it visible.
2. **Name the fallback when one answered, and why.** Fincept's `source` + `fallback_reason` fields, in our payload
   and on the panel. Matters the day the Cboe chain stands in for UW.
3. **One machine-readable source catalogue.** Today `rcdata/caps.py` (limits, with citations) and the needs
   catalogue are two halves of it. One file — what it gives, key or not, published limit and its URL, which datasets
   and boards depend on it — also answers "what breaks if we drop UW" by lookup.
4. **One generated freshness table**, dataset × producer × how often × how stale it may be, like their
   `DATAHUB_TOPICS.md`, checked against the code the way `core/tests/test_doc_constants.py` already checks other
   constants.
5. **Strip every unlisted secret from a child process.** Their rule is an allowlist of 22 named keys injected per
   call and everything else secret-shaped removed. Cheap, and it fits the `life-with-keys` boundary we already have.
6. **Topics with a policy — for the alert lane only.** Push-only, coalesced, last-value-kept, one fetch for many
   listeners. The boards do not need it; a live alert lane does.

**What not to take**: a TTL cache as the store of record, fetching inside the screen's request (the cause of the
stalls our own GUI review found), Yahoo as the single pillar, and their account-gated server.
