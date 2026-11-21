# Task 2 — provider replacement analysis

Each UW dependency of [`01_dependency_inventory.md`](01_dependency_inventory.md), marked **fully / partly / not**
replaceable with what we have or can verify today.

## 1. The three layers (avo, 21 November 2026)

avo's framing, which the rest of this folder follows:

1. **Raw trade tape** — the real-time OPRA prints with their NBBO context. UW's expensive part.
2. **Sweep / block / unusual detection** — rules written on top of that tape. No vendor sells UW's exact rules;
   this layer is ours to write whichever tape we buy.
3. **GEX / DEX / vanna / charm** — arithmetic over a chain with open interest and Greeks. Fully derivable.

Measured against the code, the split is favourable: layer 3 is most of what the boards read, layer 1 is one
ratio and one print table, and layer 2 is **already half-written here** (`core/option_prints.py`, see
[`04_existing_work.md`](04_existing_work.md)).

## 2. Verdict per dependency

| Dependency | Layer | Verdict | With what |
|---|---|---|---|
| `options.chain` (`option_eod`: NBBO, IV, 4 Greeks, OI, volume) | 3 | **fully replaceable** | Cboe delayed chain (free) or IBKR/ThetaData chain |
| `options.strikes`, `options.expiries`, `options.daily` | 3 | **fully replaceable** | derived from the same chain |
| `market.spx_expiry_strike`, `market.spx_greek_expiry_strike` | 3 | **fully replaceable (compute)** | chain OI × Greeks; UW serves the sum, we would sum it ourselves |
| SPX Gamma's `gex-levels`, `greek-exposure/*`, `spot-exposures/*`, `max-pain` | 3 | **fully replaceable (compute)** | same input; the formulas are standard and open |
| `options.iv`, `volatility/term-structure`, `interpolated-iv`, `iv-rank` | 3 | **partly today, fully with work** | IBKR is already a second provider for `iv_daily` (`rcdata/build/options/ibkr_iv.py`); rank and term structure are computed from a stored IV history |
| `options.prints` (`option_print`) | 1 | **not replaceable free** | needs a paid tape: ThetaData (USD 80), Massive Developer (USD 79, 15-min delayed) or Advanced/Databento (USD 199, real-time). **Not IBKR** — M2 ruled it out, see below |
| SPX Gamma's ask-side ratio, `greek-flow`, `flow-per-strike`, `flow-per-expiry` | 1 + 2 | **not replaceable free** | same tape, then our own side/aggregation rules |
| `options.screener` / `earnings.next` (the earnings calendar + screener row) | — | **partly** | the calendar has an existing fallback (`d26_calendar`); the screener's option-volume/premium columns need a chain source |
| `options.far_contracts` (LEAPS board) | 3 | **partly** | a market-wide `min_dte` sweep is a UW screener feature; from a chain source it becomes our own scan over all contracts, i.e. more data pulled |
| `earnings.options` (`er_options`), `earnings.tape` | 1 + 3 | **partly** | the options columns from a chain source; UW's own earnings tape history would be rebuilt from SEC + our own store |
| `fundamentals.earnings_reported` | — | **fully** | WRDS `rdq` + SEC; UW is the gap-filler and already second to `wrds` for `report_history` |
| `fundamentals.earnings_event` | — | **fully** | `sec` is already the first provider |
| `ownership.type_*_13f` (institution tags) | — | **fully, with a cost** | the holdings are the SEC's already; only UW's **tag vocabulary** (hedge_fund, activist, …) would be lost and would have to be kept as a stored snapshot or re-derived |
| `identity.etf_holdings` | — | **fully** | SSGA and iShares CSVs are already first |
| `market.economic_calendar`, `market.fda_calendar` | — | **partly, unverified** | no replacement is verified in this tree; candidates exist (the Fincept catalogue lists a Forex Factory economic calendar, keyless) but none was tested |
| `uw/total_float` (`/short_screener`) | — | **fully** | Yahoo's `floatShares` is already the other half of the same dataset (`rcdata/build/prices/floats.py`) |

**Summary.** Of the 23 UW needs, **9 are already second-sourced or trivially re-sourced**, **9 more are pure
computation over a chain** we can buy free or for ~$1.50/month, and **5 genuinely need a trade tape**: the prints
table, the SPX ask-side ratio, greek-flow, flow-per-strike/expiry, and the flow columns of the earnings set.

## 3. Candidate sources, and what was actually verified today

Prices read from the vendor's own page on **21 November 2026 ~13:01 UTC** unless the row says otherwise.

| Source | What it gives | Price | State |
|---|---|---|---|
| **Cboe delayed quotes** `cdn.cboe.com/api/global/delayed_quotes/options/<SYM>.json` | full chain: bid/ask/sizes, IV, OI, volume, **delta, gamma, theta, vega, rho**, `iv30`; ~15 min delayed, no key | free | **measured working 5 Nov 2026** (SPX 29,576 contracts, AAPL 3,440). **Re-check 21 Nov from this cloud container: HTTP 403, Cloudflare** — must be re-measured from homesrv before anything is planned on it |
| **IBKR OPRA (L1)** | top-of-book quotes + trade stream for US option exchanges, through the Gateway we already run | **USD 1.50/month non-professional**, USD 32.75 professional; **waived** when monthly commissions exceed USD 20 | verified on interactivebrokers.com market-data pricing page |
| IBKR "US Equity and Options Add-On Streaming Bundle" | streaming NBBO incl. OPRA | USD 4.50 non-pro (needs the USD 10.00 Snapshot bundle); USD 125.00 pro | same page |
| **ThetaData Options Standard** | tick-level OPRA, **every NBBO quote**, 15K trade streams, option-chain snapshots, 10 years of history | **USD 80/month** (Value 40, Pro 160 — Pro streams *every* option trade, 14 years) | verified on thetadata.net/pricing; **individual use, no redistribution** |
| **Massive (ex-Polygon)** Options Developer | OPRA **trades**, quotes, real-time Greeks and IV, daily OI, flat files, websockets, second aggregates; **15-minute delayed**; 4 years of history | **USD 79/month** | **measured 21 Nov 2026** (M4), `massive.com/pricing?product=options` rendered in Chromium; `polygon.io` now redirects there. Marked "Individual use" |
| **Massive** Options Advanced | the same, **real-time**, 5+ years of history | **USD 199/month** | same read. The two tiers below it — Starter USD 29 and Basic USD 0 — carry **no Trades**, so they are chain-only |
| **Databento** Standard | live data, **no licence fees**, 16+ years L0, **1 year of L1 history**, 1 month L2/L3 | **USD 199/month**, monthly, no annual contract | **measured 21 Nov 2026** (M4), `databento.com/pricing` rendered in Chromium. Plus is USD 1,750/month **plus** OPRA licence fees passed through, Unlimited USD 4,500/month plus fees, both annual; a monthly/annual toggle also showed USD 1,500 / 4,000. Usage-based (USD/GB) is historical only |
| **Tradier** | chain + some quotes inside a brokerage plan | **unverified** — not checked | |
| **UW Discord bot channels** (9, in avo's server: `live-option-flow`, `highest-volume-contracts`, …) | UW's own alerts as messages | inside the existing UW subscription | **plan B** (avo, 21 Nov): only if we cannot build our own flow alert. Not followed today |

**The cost frame.** UW is **USD 160/month** (Whale Bundle Basic, avo 5 Nov 2026). IBKR OPRA at USD 1.50, or
ThetaData Standard at USD 80, against USD 160 — the saving is real but the deciding question is not price, it is
whether layer 2 can be rebuilt (see [`03_options_track.md`](03_options_track.md)).

## 4. What is blocked on V2

**There is no separate "V2 provider list".** The provider list *is* `rcdata/needs/catalog.py` (`providers=` per
need) plus `core/credentials.py`, and the capability matrix *is* that catalogue plus `rcdata/caps.py`. The v2 run
plan (`/mnt/project-files/gui_redesign/revenuechaser_v2_run_plan.md`, 21 Nov 2026) adds **no new market-data
provider**: its only source steps are step 15 (Kalshi and Polymarket, free) and step 9's Settings "source
catalogue with state and TEST", which *renders* the same registry. So this migration is **not blocked on V2**;
see [`05_migration_plan.md`](05_migration_plan.md) §4 for the three real sync points.

## 5. What we actually spend at UW — read from the API dashboard, 21 November 2026 14:56 Amsterdam

Read off `unusualwhales.com/dashboard/api` by the UI thread (screenshots in
`/mnt/project-files/UWdependency/api/`; the key was not revealed).

- Plan **"Whale Bundle Basic"**, active. **Unlimited requests a day** (the page prints 100M included, 1,312 used
  that day), **2-year lookback**, and **websockets are NOT in this plan** ("Upgrade to bundle Pro").
- **Usage, past 30 days: 148K requests in total, 5K a day on average, 35K on the peak day**, 0 days over 80%.
- Request health, past 24 h: **no 429, no 404, no 403**, 9 other errors.

**Busiest endpoints, past 30 days** — and what each one costs us to replace:

| Endpoint | Requests | Share | Replacement |
|---|---|---|---|
| `/stock/:ticker/greek-exposure/strike-expiry` | 36,893 | 22.9% | **layer 3** — compute from a chain (`uw/greek_expiry_strike`, one call per expiry) |
| `/shorts/:ticker/interest-float/v2` | 35,806 | 22.2% | FINRA short interest is already a need of its own (`ownership.short_interest`); the float half has Yahoo beside it |
| `/stock/:ticker/option-contracts` | 19,423 | 12.0% | **layer 3** — Cboe or another chain source |
| `/stock/:ticker/ohlc/:candle_size` | 17,870 | 11.1% | Alpaca already serves the prices store's bars |
| `/stock/:ticker/earnings` | 11,229 | 7.0% | SEC + WRDS (`fundamentals.report_history` already names `wrds` first) |

**So roughly 75% of what we spend at UW is not the tape at all** — it is chain arithmetic, short interest,
bars and earnings, each of which has a source we either hold or can reach free. That sharpens the whole plan:
the expensive thing we buy UW for is used least.

**One consequence for option B.** A note of 5 November put UW's Options Starter tier at 99 USD with
**25,000 requests per billing month** (unverified, from a screenshot of UW's API pricing page). Against the
measured **148K requests in 30 days**, Starter would not fit without first moving the four non-tape endpoints
above off UW. So "just downgrade" is not a one-step option; it is lane A + lane B first, then a downgrade.
