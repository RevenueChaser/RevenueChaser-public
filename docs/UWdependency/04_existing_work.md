# Task 4 — what already exists and can be reused

## 1. In this repository

| Asset | Where | Why it matters |
|---|---|---|
| **The side and package rules** | `core/option_prints.py:44-60` | layer 2, half written and measured against UW's own tags (235/241) |
| **IBKR as a second IV provider, in production** | `rcdata/build/options/ibkr_iv.py` — `OPTION_IMPLIED_VOLATILITY`, 1-year daily bars, one request a name | proves the Gateway path works for an options measure, and already fills `iv_daily` as source `ibkr` |
| **A minimal TWS client we own** | `core/providers/ibkr_tws.py:1-33` — handshake, `startApi`, `reqContractDetails`, `reqHistoricalNews`, `reqMktData` (news), `reqHistoricalData` | the socket framing is already written; a chain or tape request is a new message type on an existing client, not a new subsystem. It deliberately avoids `ib_async` because that library asks for positions on connect |
| **Gateway login state** | `core/ibkr_login.py` | the health check the new lane would reuse |
| **Cboe as a keyless source, in production** | `rcdata/build/sources/cboe.py` — index history CSVs from `cdn-api.cboe.com` | a Cboe fetch already has a home, a pacer and a raw/parquet layout |
| **The provider seam itself** | `rcdata/needs/catalog.py` `providers=`/`fallbacks=`, `core/credentials.py` | a new provider is a module plus catalogue edits; boards do not change |
| **The call-accounting layer** | `rcdata/caps.py`, `core/providers/spend.py`, `ops.provider_calls_daily` | a new provider gets limits and a counter for free |
| **The parked research** | issue [#418](https://github.com/alsanvolkan/RevenueChaser-public/issues/418) (UW cost / Cboe / IBKR, parked by avo 5 Nov to December 2026) | this migration is that issue, unparked by the 8 December deadline |

## 2. Fincept Terminal

Surveyed on 20-21 November 2026; the write-ups are in `docs/v2/fincept/` (`data-sources.md`, 204 connectors;
`source-usage.md`, which screen uses which source; `live-walk-2026-11-21.md`).

- **Option chains: Cboe delayed first, Yahoo as fallback** — `scripts/derivatives/deriv_market.py:1-8`.
- **Paid depth: Databento**; brokers feed live quotes on the F&O screen.
- **No UW connector. No flow tape. No sweep detection.** Nothing in Fincept replaces layers 1 and 2.
- Licence AGPL-3.0: structure may be copied, source may not (`v2/README.md` decision 1).

## 3. The UW Discord bot feed (plan B, and a substitute for the hard items)

avo's server carries nine UW bot channels; the survey is in `/mnt/project-files/UWdependency/discord-bot/notlar.md`.
avo's direction, 21 November 2026: **if it is used, it is wired to RevenueChaser directly, not through
idea-creator**, and it is plan B for option flow — but it is a candidate substitute for the items we cannot build.

avo's classification of the channels:

| Class | Channels |
|---|---|
| **We can build it ourselves** | `live-option-flow` (= layers 1+2 of the options track) |
| **We can learn it and build it** | `unusual-command-line` (a command/query surface over our own data) |
| **Hard — needs a substitute source, and Discord is a candidate** | `insider-trades`, `analyst-ratings`, `congress-trades-fillings`, `news-feed`, `trump-schedule`, `stock-updates`, `highest-volume-contracts` |

Three things must be answered before any of that can be planned (all unverified, all for avo):

1. **Whose server is it?** A program can read a channel only with our own bot in that server (the server admin
   adds it) or with a user token, which is against Discord's terms. On avo's own server both bots sit cleanly.
2. **Does the bot feed depend on the UW plan that renews 9 December**, or on the server owner's plan?
3. Some channels post **rendered images** (`highest-volume-contracts`), so their numbers are not machine-readable
   without OCR.

### 3.1 The hard items, checked against the code

| Item | Verdict |
|---|---|
| **insider-trades** | **already ours, in production.** `rcdata/build/ownership/form4.py` reads Form 4 and 4/A from the EDGAR daily index; the need is `ownership.insider`, provider `sec` (`rcdata/needs/catalog.py:264`). UW's own `insider` client method has **no caller** (`01_dependency_inventory.md` §5). avo's EDGAR link is the same source we already read. Nothing to migrate |
| **congress trades** | not in the catalogue at all — nothing in production depends on it; it would be new work on a free source, not a migration |
| **analyst-ratings** | **the one genuinely missing item.** No need, no table, no source in this tree. Candidates: Yahoo (what Fincept uses), UW `/screener/analysts`, or the Discord feed. New work either way |
| **news-feed** | the News board is on **IBKR headlines** already (`core/providers/ibkr_tws.py`, avo's choice 9 Nov 2026) |
| **stock-updates (52-week high/low)** | computable from the prices store (`price_bar_daily`); no provider needed |
| **highest-volume-contracts** | a scan over the chain; needs the chain source of layer 3, not UW |

### 3.2 Congress trades — measured 21 November 2026

avo: "bunu da yapabiliriz". Checked, rather than assumed:

- **House**: the Clerk publishes a bulk file per year.
  `GET https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2026FD.zip` answered **HTTP 200, 66,320
  bytes** on 21 Nov 2026 13:09 UTC; it holds `2026FD.txt` (**1,867 rows**) and `2026FD.xml`, columns
  `Prefix, Last, First, Suffix, FilingType, StateDst, Year, FilingDate, DocID`. `FilingType` `P` is a periodic
  transaction report; the `DocID` names the PDF of that filing. No key, no robots.txt (404 on
  `/robots.txt`), no sign-in.
- **Senate**: `efdsearch.senate.gov` is reachable, but its search sits behind an agreement page, so machine
  access needs a session and its terms must be read before anything is written. **Unverified.**
- **The work UW sells here is not the filings, it is the processing**: the transaction lines live inside the
  **PDF**, many of them scanned, and each has to be parsed and matched to a ticker. That is the whole cost.

Classification: **ours, with PDF/OCR parsing as the hard part.** Nothing in production depends on congress
data today (no need in `rcdata/needs/catalog.py`), so this is new work, not a migration — it only matters if
avo wants the board.
