# Task 3 — the options track

What it takes to replace UW's options products, layer by layer.

## Layer 3 — GEX / DEX / vanna / charm (the easy part)

**Input needed:** a chain with strike, expiry, right, open interest and gamma (or IV, from which gamma follows).
**Nothing else.** UW sells the sum, not the data.

The formula avo quoted is the standard one:

```
GEX (per 1% move) = ± gamma × open_interest × 100 × spot² × 0.01     (calls +, puts −)
```

Call wall, put wall and the gamma flip all fall out of that profile. The same chain gives DEX, vanna and charm.

**What this replaces here:** `market.spx_expiry_strike`, `market.spx_greek_expiry_strike`, and the SPX Gamma
board's `gex-levels`, `greek-exposure/{strike,expiry,strike-expiry}`, `spot-exposures/*`, `max-pain`,
`volatility/term-structure`, `iv-rank` — 12 of the 13 endpoints in `module_spx_gamma/snapshot.py:96-118`.

**Chain sources, cheapest first**

| Source | Delay | Greeks | OI | Cost | State |
|---|---|---|---|---|---|
| ~~Cboe `cdn.cboe.com/api/global/delayed_quotes/options/<SYM>.json`~~ | ~~15 min~~ | yes (δ γ θ ν ρ) | yes | free, no key | **ruled out (M1, 21 Nov 2026): HTTP 403 from homesrv too**, on both hosts and both symbols. It worked on 5 Nov from a cloud box; it does not work from where RC runs, nor from avo's own browser at home |
| IBKR Gateway (OPRA L1 + model Greeks) | real time | yes (IBKR's model) | yes | **USD 1.50/mo** non-pro, waived over USD 20 commissions | the Gateway already runs on homesrv |
| ThetaData Options Standard | real time | chain snapshots | yes | USD 80/mo | individual use, no redistribution |

**The one measured obstacle for IBKR as a chain source:** the Gateway's default is **100 market data lines**, and
one ticker's chain was **19,774 contracts** on our own first real run (`rcdata/build/options/tables.py:37-39`).
A whole-market chain over IBKR is therefore not practical; a **bounded** chain (SPX and the watch list, strikes
near the money) is. Cboe has no such limit, which is why Cboe is the default chain source and IBKR the live one.

**Open gap:** Cboe served AAPL 3,440 contracts against UW's 19,774 (5.7×). The cause was never explained. A
coverage comparison on one session must run **before** any board is moved onto Cboe.

## Which UW page falls on which side of the line

Measured from the UI survey, 21 Nov 2026 (`ui/README.md`, `07_ui_survey.md` §3).

| Needs a trade tape with bid/ask side | A daily chain snapshot rebuilds it |
|---|---|
| Live Options Flow | OI changes |
| Flow alerts | Max pain |
| Net Premium | GEX / vanna / charm by strike and by expiry |
| NOPE | The options grid |
| Delta flow | Highest OI |
| Bullish / bearish premium | Implied move per expiry |
| Bid/ask volume bars | "Highest volume contracts" (one table, four UW pages) |

So the tape decision below is the whole cost decision — but the right column is no longer free either: **M1 found
Cboe answering 403 from homesrv as well** (21 Nov 2026), so a chain costs at least the IBKR line's USD 1.50.

**UW is retiring DEX** (banner on its own Delta tab, seen 21 Nov 2026). It stays in the layer-3 list above as
arithmetic, but it is not worth a lane.

## Layer 1 — the raw tape

What the code actually consumes from the tape today is small (measured 5 Nov 2026, re-checked here):

- **One ratio decides anything**: `_ask_ratio = call_volume_ask_side / call_volume` within ±25 points of a wall,
  against the threshold 0.55 — `module_spx_gamma/flow_signals.py:25`, `:40-43`, `:52-58`. SPX only.
- `net_call_premium` / `net_put_premium` are rendered but **no signal reads them**
  (`module_spx_gamma/normalize.py:228-229`).
- `option_print` rows (the prints table) are stored per session for the boards that show them.

So layer 1 is needed for: `options.prints`, the SPX ask-side ratio, `greek-flow`, `flow-per-strike/expiry`, and
the flow columns of the earnings set.

**Tape sources**

| Source | What | Price (verified 21 Nov 2026) |
|---|---|---|
| IBKR OPRA L1 through the Gateway | top-of-book quotes and the trade stream | USD 1.50/mo non-pro (waived over USD 20 commissions); the streaming bundle is USD 4.50 + USD 10.00 |
| ThetaData Standard / Pro | tick level, every NBBO quote OPRA reports; Pro streams every option trade | USD 80 / USD 160 per month |
| Massive (ex-Polygon), Databento | full OPRA, developer-friendly / institutional | **prices unverified** — both pricing pages need JavaScript |
| UW full-tape (`/option-trades/full-tape`) | one zip of all prints per day, 40+ columns | inside the current UW plan; ~2.6 GB zip/day |

**The unverified point that decides IBKR.** Whether the TWS API gives **real-time tick-by-tick option trades**
(not just L1 quotes), and under what pacing. An internal note of 5 Nov says options are historical-only for
tick-by-tick, with 5 concurrent subscriptions and 1,000 ticks per historical request. The IBKR documentation
page is JavaScript-rendered and could not be read from here. **This is measurement V2 in the plan** and it is the
single fact that decides whether IBKR alone can carry layer 1.

### "Why not take OPRA directly?" — read from OPRA's own fee schedule, 21 November 2026

Because **every option below is already OPRA**, and OPRA is not something a person subscribes to. It is the
consolidated last-sale and quotation feed of the US option exchanges, published as a **binary multicast feed, not
an API**; the only entry on OPRA's own site is "BECOME A VENDOR". Taking it directly means becoming a vendor.

Read from `cdn.opraplan.com/documents/OPRA_Fee_Schedule.pdf`:

| Fee | Monthly |
|---|---|
| **Direct Access Fee** — to receive data directly from OPRA's processor | **USD 1,000** |
| **Connectivity**, 10 Gb IP + NMS Network port | **USD 12,000** (+ USD 10,000 initial) |
| Connectivity, LCN + NMS Network | USD 24,000 (+ USD 15,000 initial) |
| Redistribution Fee, if the data goes on to anyone else | USD 1,500 |
| Non-Display Use, per category | USD 2,000 |
| **Nonprofessional Subscriber Fee — payable by the vendor, per nonpro** | **USD 1.25** |

Direct access is also physically bounded: it is a port on the NMS Network, which "exists only within the Mahwah
Data Center" in New Jersey. So the floor for taking OPRA directly is about **USD 13,000 a month plus hardware in
New Jersey**.

The last row is the useful one. **USD 1.25 per non-professional subscriber, paid by the vendor, is what sits
underneath IBKR's USD 1.50 line.** We are already paying OPRA's retail rate, through the only route a
non-professional has. The choice between IBKR, ThetaData, Massive and Databento is not a choice about OPRA — it
is a choice about how completely each vendor delivers it.

**One flag, and it is an inference, not a vendor's answer:** the schedule prices "Non-Display Use" at USD 2,000
per category, and feeding a store rather than drawing a screen is what that term describes. For an individual
non-professional, vendors handle this under the nonpro agreement — but that is a reading of the tariff, not
something a vendor has confirmed in writing for our case. It goes in the same question to ThetaData as the
individual-use terms, before any subscription.

### What a tape costs, measured (M4 done, 21 Nov 2026)

| Source | Tape | History | Price | Delay |
|---|---|---|---|---|
| ~~IBKR OPRA L1~~ | **ruled out for the tape (M2, 21 Nov 2026):** IBKR's own doc says *"Real time tick-by-tick data is not available for options"* — twice on the page | — | USD 1.50/month | n/a. It stays the chain, IV and snapshot source, not the tape |
| **Massive Options Developer** | OPRA trades + flat files | 4 years | **USD 79/month** | **15 minutes** |
| **ThetaData Standard** | tick-level OPRA, every NBBO quote | 10 years | **USD 80/month** | real-time |
| **Massive Options Advanced** | OPRA trades + flat files | 5+ years | **USD 199/month** | real-time |
| **Databento Standard** | live, no licence fees | 1 year of L1 | **USD 199/month** | real-time |
| UW Whale Bundle Basic, today | the tape we have now, plus everything else | 2 years | **USD 160/month** | real-time |

Two things follow. First, **a 15-minute delay is free of charge in practice**: everything the code actually reads
from the tape (the SPX ask-side ratio, the stored prints, a sweep rule scored overnight) is not a live alert, so
Massive Developer at USD 79 is half of UW. A live flow alert is the only thing that needs USD 199 or IBKR.
Second, none of these carries a chain's Greeks and the calendars and the 13F tags and the earnings tape; UW's
USD 160 is one bill for several things, which is why `05_migration_plan.md` option C is not simply "buy a tape".

### The historical tape is already ours to keep, while the plan is alive

`GET /api/option-trades/full-tape/{date}` returns **every option transaction of one trading day** as a zip
(UW's own spec, `api/uw_public_api_openapi.yaml` line 28490; the spec's own example uses `wget` with the bearer
key). Its reach is **the plan's historical lookback window, back to 2022-01-01** — not the 8 trading days the
`/data/download` page offers. So reference days can be taken by API, in bulk, for as long as the subscription
lasts, and they are the exact answer M3 scores our own side and sweep rules against. See lane J in
`05_migration_plan.md`.

## Layer 2 — sweep / block / side / multi-leg

UW's exact rules are closed. Ours would be:

- **side**: price against the NBBO midpoint — **already written and tuned here**, `core/option_prints.py:44-55`.
  Measured on 300 real prints (2026-10-28): the nearer-side rule agreed with UW's own tag on **235 of 241**
  prints that had a quote; the strict rule agreed on only 123 of 300.
- **package / multi-leg**: OPRA trade condition codes — **already written**, `core/option_prints.py:56-60`,
  `PACKAGE_CODES` (`mlet`, `mesl`, `tasl`, `sprd`, `stdl`, `bwrt`, `cmbo`, …).
- **sweep**: several prints on one contract inside a short window (~500 ms) across exchanges — **not written**.
- **block**: large size on one exchange, or its condition code — **not written**.

So layer 2 is **about half built**, and the two missing rules are ordinary code over a tape we hold.

## The validation step avo asked for (21 Nov 2026)

While the UW subscription is still live, our own detection can be scored against UW's. Design, kept small so no
quota is burned:

1. Pick **one session and 2-3 contracts** (one SPX 0DTE, one liquid single name).
2. Store that window's prints from the new tape (IBKR or ThetaData trial) **and** UW's own alerts for the same
   window — UW's side already arrives in the stored `option_print` rows, so most of the comparison needs **no new
   UW call at all**.
3. Report: agreement rate on side, how many of UW's sweeps our rule finds, how many we call that UW does not.
4. Acceptance: side agreement at or above the 235/241 the stored sample already shows; the SPX ask-side ratio
   within a band that does not move the 0.55 threshold's verdict on that day.

**This has to happen before 8 December**, because after the renewal date the reference may be gone.

## Fincept Terminal

Fincept's derivatives screen uses **Cboe's delayed chain first with Yahoo as the fallback**
(`scripts/derivatives/deriv_market.py:1-8`, quoted in `docs/v2/fincept/source-usage.md`), and its paid depth is
**Databento**. It has **no UW connector, no flow tape and no sweep detection**. So Fincept confirms the choice of
Cboe for layer 3 and offers nothing for layers 1 and 2. It is AGPL-3.0: structure may be copied, source may not
(`v2/README.md`, decision 1).
