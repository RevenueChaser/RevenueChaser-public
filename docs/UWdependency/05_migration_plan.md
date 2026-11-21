# Task 2.2 + 5 — the migration plan

Deadline: every decision made **before 8 December 2026**; the UW plan renews **9 December 2026**.

## 0. The shape of the answer

Three options, and the work below is written so the choice can be made **late**, on measurements rather than on
opinion:

| Option | Monthly | What it costs us |
|---|---|---|
| **A — stay on UW** | USD 160 | nothing to build; the deadline just passes |
| **B — downgrade UW, add a free/cheap chain** | UW Options Starter USD 99 (unverified today) + Cboe free | keeps the tape, drops GEX, which we then compute |
| **C — leave UW** | IBKR OPRA USD 1.50 (often waived) or ThetaData USD 80, + Cboe free | layers 1 and 2 become ours; ~5 needs have to be rebuilt |

Nothing below commits to one. **Measurements M1-M4 decide it**, and all four fit before 8 December.

## 1. Measurements first (this week)

| # | Measurement | How | Why it decides something |
|---|---|---|---|
| **M1** | Is the Cboe delayed chain reachable and complete? | from **homesrv** (not the cloud container, which got HTTP 403 Cloudflare on 21 Nov): one `_SPX` and one AAPL fetch, count contracts and expiries, compare against the same session's `option_eod` rows | the 5.7× contract gap against UW is unexplained; layer 3 rests on this |
| **M2** | Does IBKR give real-time **tick-by-tick option trades**, and at what pacing? | one bounded request on the Gateway that already runs, on an SPX 0DTE strike: count ticks, the span covered, whether bid/ask accompany each tick | decides whether IBKR alone carries layer 1, i.e. whether the whole migration costs USD 1.50 or USD 80 a month |
| **M3** | How close is our own side/sweep call to UW's? | on the **stored** `option_print` rows of a past session (no new UW call), score `core/option_prints.py` against UW's own tag, then add a draft sweep rule and score it | the acceptance test avo asked for, while UW is still live |
| **M4** | Massive and Databento option prices | read both pricing pages in a browser (they are JavaScript) | the two candidate prices nobody has verified |

M1-M3 need no new subscription and no paid call. M4 is a browser read.

## 2. The lanes, if we go to B or C

Each lane is one issue and one PR, in this order.

| Lane | Work | Effort | Depends on |
|---|---|---|---|
| **A. Compute GEX ourselves** | a `core/gex.py` that takes a chain (strike, expiry, right, OI, gamma, spot) and returns the exposure profile, call/put wall and flip; tested against a stored UW `gex-levels` answer of the same session, so "same numbers" is a test, not a hope | 2-3 days | M1 |
| **B. A Cboe chain provider** | `core/providers/cboe_chain.py` + `rcdata/build/options/cboe_chain.py`, writing the same `option_eod` columns; `providers=("uw", "cboe")` on the chain needs, UW still first | 3-4 days | M1 |
| **C. An IBKR options tape lane** | a new message type on `core/providers/ibkr_tws.py` for OPRA L1 / trades, bounded to SPX and the watch list; the prints land in `option_print` with source `ibkr` | 1 week | M2 |
| **D. Sweep and block rules** | the two missing rules beside the side and package rules already in `core/option_prints.py` | 2-3 days | C, M3 |
| **E. The 13F tag snapshot** | freeze UW's institution tags into our own table so the SEC-based slices survive without UW | 1 day | — |
| **F. Calendars** | find and verify a replacement for `/market/economic-calendar` and `/market/fda-calendar`, or accept losing them | 2 days | — |
| **G1. Congress trades (optional, new)** | House Clerk bulk ZIP (verified 21 Nov: 1,867 rows for 2026) + Senate eFD; the cost is parsing the PTR **PDFs** and matching tickers | 1 week, mostly parsing | avo's word |
| **G. Analyst ratings** | the one item with no source here at all; new work, not a migration | unscoped | avo's word |
| **H. Delete the dead surface** | the 21 uncalled client methods and the lab endpoints we never use | half a day | — |

Lanes A, E, F and H are worth doing **whatever is decided** — A because it removes a UW dependency for free,
E because it makes a board independent, H because it shrinks what must ever be ported.

## 3. Schema mapping, where it is already known

| UW field (`option_eod`) | Cboe field | Note |
|---|---|---|
| `nbbo_bid` / `nbbo_ask` | `bid` / `ask` | Cboe also gives `bid_size` / `ask_size` |
| `implied_volatility` | `iv` | |
| `delta`, `gamma`, `theta`, `vega` | same names | Cboe adds `rho` |
| `open_interest`, `volume` | same names | |
| contract id | `option` (`SPX261120C00400000`) | same OCC layout |
| `iv30d`, `iv30d_1d` (screener) | `iv30`, `iv30_change` | |
| per-trade side (`*_volume_ask_side`) | **absent** | Cboe is aggregate volume only — this is exactly layer 1 |

## 4. The three places this must sync with v2

There is **no separate v2 provider list**; the registry is `rcdata/needs/catalog.py` + `core/credentials.py`, and
the v2 run plan adds no market-data provider (only Kalshi/Polymarket at step 15). The real sync points:

1. **v2 step 9 — the Settings source catalogue** (state + TEST per source). A new provider must appear there, so
   lanes B and C each add their row. *Not blocking: the catalogue reads the registry.*
2. **v2 step 17 — the alert lane, "source-neutral option fields".** Our own flow alert (lanes C + D) is the first
   real consumer. If UW is dropped, step 17's fields must come from our own tape. **This is the one place where
   waiting is right**: the field list should be agreed once, with step 17.
3. **v2 step 20 — backtest and the volatility surface.** It needs **history depth**: ThetaData Standard carries
   10 years, UW Basic 2, Cboe none (snapshots only). If backtesting matters, that argues for ThetaData over
   IBKR. Marked **blocked on v2 step 20's scope**.

## 5. The questions only avo can answer (one card at a time)

1. **Which option, A, B or C?** — asked once M1-M4 are in, so it is a decision on numbers.
2. **Whose Discord server is "Traders' Pub"**, and may a reader bot be added? (Decides whether the Discord route
   exists at all.)
3. **Does the UW bot feed stop when the plan renews on 9 December?**
4. **Analyst ratings** — do we want them at all, and is a paid source acceptable?

## 6. What is explicitly left alone

The old dashboard is not redesigned (avo, 21 Nov); nothing here changes a board's look. No live store write, no
paid model call, no UW API request, no delete. Every lane lands as its own PR on green CI, and the ones that
change what a dashboard job writes land alone.
