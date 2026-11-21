# Task 2.2 + 5 — the migration plan

Deadline: every decision made **before 8 December 2026**; the UW plan renews **9 December 2026**.

## 0. The shape of the answer

Three options, and the work below is written so the choice can be made **late**, on measurements rather than on
opinion:

| Option | Monthly | What it costs us |
|---|---|---|
| **A — stay on UW** | USD 160 | nothing to build; the deadline just passes |
| **B — downgrade UW, add a free/cheap chain** | UW Options Starter USD 99 (unverified) + Cboe free | keeps the tape, drops GEX, which we then compute. **Not a one-step option**: measured usage is 148K requests in 30 days against Starter's reported 25,000 a month, so lanes A and B have to land first (`02_provider_replacement.md` §5) |
| **C — leave UW** | IBKR OPRA USD 1.50 (often waived) or ThetaData USD 80, + Cboe free | layers 1 and 2 become ours; ~5 needs have to be rebuilt |

Nothing below commits to one. **Measurements M1-M4 decide it**, and all four fit before 8 December.

## 1. Measurements first (this week)

| # | Measurement | How | Why it decides something |
|---|---|---|---|
| **M1** | Is the Cboe delayed chain reachable and complete? | from **homesrv** (not the cloud container, which got HTTP 403 Cloudflare on 21 Nov): one `_SPX` and one AAPL fetch, count contracts and expiries, compare against the same session's `option_eod` rows | the 5.7× contract gap against UW is unexplained; layer 3 rests on this |
| **M2** | Does IBKR give real-time **tick-by-tick option trades**, and at what pacing? | one bounded request on the Gateway that already runs, on an SPX 0DTE strike: count ticks, the span covered, whether bid/ask accompany each tick | decides whether IBKR alone carries layer 1, i.e. whether the whole migration costs USD 1.50 or USD 80 a month |
| **M3** | How close is our own side/sweep call to UW's? | on the **stored** `option_print` rows of a past session (no new UW call), score `core/option_prints.py` against UW's own tag, then add a draft sweep rule and score it | the acceptance test avo asked for, while UW is still live |
| ~~**M4**~~ | ~~Massive and Databento option prices~~ | **done 21 Nov 2026**: both pages rendered in Chromium | Massive Options Developer **USD 79/month** (OPRA trades + flat files, 4 years, 15-minute delayed), Advanced **USD 199** real-time; Databento Standard **USD 199/month**, no licence fees, 1 year of L1. Table in `02_provider_replacement.md` §candidates, comparison in `03_options_track.md` |

M1-M3 need no new subscription and no paid call. M4 is a browser read.

**One input to M1 and M3 expires sooner than the plan does.** UW's `Other > Data Downloads` offers five daily
files for the **last 8 trading days only** (UI survey, `ui/README.md`). Real UW chain and print files for a few
reference days would be the cheapest and cleanest thing to score our own build against, with no API call. The
terms are personal use and nothing has been downloaded; taking reference days is avo's call, and the window, not
the renewal date, is the deadline — a file from 1 December stops being offered around 11 December.

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
| **J. Keep the UW tape while we still pay for it** | `GET /api/option-trades/full-tape/{date}` gives one trading day's **complete** option tape as a zip, back to 2022-01-01 within the plan's lookback (UW's own spec, line 28490) — not the 8 days `/data/download` shows. Download a reference set now; add a daily job that takes each new day until UW is dropped in v2, then **switch the job off**. The four other daily files (Options Screener, Stock Screener, OI Changes, Dark Pool) have no download path, but their live endpoints do, so they are a snapshot job rather than a zip | 1 day for the job; the download is bandwidth and disk | avo said yes, 21 Nov 2026 17:14 Amsterdam |
| **I. Preserve avo's own UW-only data** | six stock watchlists (already exported), four custom alert rules and the Console habits (already recorded) — then decide where they live in RC: the watchlists in `watchlists.duckdb`, the alert rules as RC alert definitions | 1 day for the import; the capture is done | before 8 Dec |

Lane **I** is the only one with no fallback: it is configuration avo typed into UW, not data a provider
can return, and it is unrecoverable once the plan lapses. The capture itself is done (UI survey); what remains is
where it lands in RC.

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

4. **A re-evaluation point when v2's providers screen lands** (avo, 21 November 2026: "RC v2 geldiginde,
   providers kisminda daha fazla secenegimiz olacak, oradan da bakabiliriz"). Said plainly, so nobody waits for
   the wrong thing: **step 9's source catalogue renders the registry we already have; it does not add a
   provider by itself.** What it does give is one screen where every source, its state and its TEST result sit
   together, which is the right moment to look again at the two items with no home today —
   `highest-volume-contracts` (market-wide ranking) and analyst ratings. **If v2's screen is not up before
   8 December, the decision is made on M1-M4 and nothing waits for it.**

## 4b. The provider issues avo closed on 21 November 2026

avo, 21 November 2026 14:47 Amsterdam: the provider-dependency issues are **his** once v2 is up, and they were
closed — #100 (yfinance 401/429 across 48 files), **#418** (move the options layer to Cboe, leave the UW tier),
**#1233** (the tape measurement, then the second-source conversation), #709 (the unfiltered option screener),
#785 (the 64 symbols no provider covers). #1234 closed with the EVREN decision. They continue at v2's
provider / source-catalogue step.

Two of them are the same work as this plan's measurements: **#418 is M1** (Cboe) and **#1233 is M2** (the tape).
Said once, plainly, so nothing is assumed: the **8 December deadline and M1-M4 still stand** (coordinator's note,
same day). If the measurements do not happen before then, the renewal simply passes and the decision is
**option A, stay on UW** for another month — which is a fine outcome, as long as it is chosen rather than
arrived at.

## 5. The questions only avo can answer (one card at a time)

1. **Which option, A, B or C?** — asked once M1-M4 are in, so it is a decision on numbers.
2. **How many reference days, and where do they live?** — answered in principle (avo, 21 Nov 17:14: take them and
   automate the rest until UW is dropped); the remaining part is scope, and that is a disk measurement, not a
   question. Files land under `/mnt/data/apps/revenuechaser/uw-reference/`, personal use, out of this repository.
3. **Does the UW bot feed stop when the plan renews on 9 December?**
4. **Analyst ratings** — do we want them at all, and is a paid source acceptable?

**Lane J's end condition is written down on purpose:** the daily download exists only while UW is paid for. The
day a v2 board stops reading UW, the job is switched off in the same PR that removes the need. It is not a
permanent dependency wearing a different hat.

Answered since: **"Traders' Pub" is avo's own server**, run with friends, and the UW bot in it runs on the UW API
(avo, 21 Nov 2026 17:02 Amsterdam). The aim is to see how that bot works and whether it can be tied into RC, and
to keep a record either way. The method for walking the Discord window comes from avo; nothing there is touched
before that.

## 6. What is explicitly left alone

The old dashboard is not redesigned (avo, 21 Nov); nothing here changes a board's look. No live store write, no
paid model call, no UW API request, no delete. Every lane lands as its own PR on green CI, and the ones that
change what a dashboard job writes land alone.
