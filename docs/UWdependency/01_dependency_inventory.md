# Task 1 — the UW dependency inventory

Read from `main` = `b97c1a4` on 21 November 2026. This file merges and re-verifies the first pass written in
`/mnt/project-files/revenuechaser/uw-migration/01_dependency_inventory.md`; the lines below were each re-read in
the tree, and the additions over that pass are marked **(new)**.

## 1. One boundary, no streaming

All UW traffic goes through one client, `core/providers/unusual_whales.py` (1,187 lines).

| What | Where |
|---|---|
| Base URL | `BASE = os.getenv("RC_UW_BASE") or "https://api.unusualwhales.com/api"` — `:27` |
| Auth probe | `_AUTH_PROBE = "/stock/AAPL/info"` — `:30` |
| Credential | slug `unusual_whales`, env `UNUSUAL_WHALES_API_KEY` — `core/credentials.py:34-39`; its `required_for` says **"Earnings Radar, SPX Gamma, LEAPS, Sector Rotation"** |
| Retry | 3 attempts, 1 s base, `Retry-After` capped at 30 s — `:43-46` |
| Breaker | 5 consecutive final failures stop a run — `:49-51` |
| Paging | calendar 500 rows × 10 pages — `:54-55`; `/stock/{t}/option-contracts` 500 a page |
| Escape hatch | `raw_endpoint()` / `raw_endpoint_result()` — `:1110-1122`, the only free-form caller is `module_uw_interaction/engine.py:185` |
| Day cap | **none** — `rcdata/caps.py:19`: "UW has no day cap: the owner removed it (avo 2026-11-10)" **(new; an older note that assumed 100,000 calls/day is stale)** |
| Second base URL | `module_spx_gamma/config.py:13` `UW_API_BASE` (`RC_UW_BASE_ROOT`), the SPX Gamma board's own root **(new)** |

There is **no WebSocket, no Kafka, no MCP and no streaming** path in this tree: plain `httpx` REST. UW's MCP
server exists in the Claude session environment, not in the app. Everything stored is keyed by `session_date`,
so a replacement needs **no streaming parity for what is built today**.

## 2. Serving needs that name `uw` — `rcdata/needs/catalog.py`

23 needs name `uw`; **18 have no second provider**.

| Need | Table | Other providers | Line |
|---|---|---|---|
| `options.chain` | `option_eod` | — | `:270` |
| `options.strikes` | `option_strike` | — | `:272` |
| `options.expiries` | `option_expiry` | — | `:274` |
| `options.daily` | `option_daily` | — | `:276` |
| `options.prints` | `option_print` | — | `:278` |
| `options.iv` | `iv_daily` | **ibkr** | `:280` |
| `options.screener` | `option_screener_daily` | — | `:282` |
| `options.far_contracts` | `option_far_contract` | — | `:285` |
| `earnings.options` | `er_options` | — | `:287` |
| `earnings.tape` | `earnings_tape` | — | `:294` |
| `earnings.next` | `option_screener_daily` | fallback `d26_calendar` | `:187` |
| `market.spx_expiry_strike` | `spx_gamma_expiry_strike` | — | `:161` |
| `market.spx_greek_expiry_strike` | `spx_greek_expiry_strike` | — | `:165` |
| `market.economic_calendar` | `economic_event` | — | `:168` |
| `market.fda_calendar` | `fda_event` | — | `:171` |
| `fundamentals.earnings_event` | `earnings_event` | **sec** | `:196` |
| `fundamentals.earnings_reported` | `earnings_reported` | — | `:198` |
| `fundamentals.report_history` | `earnings_report_history` | **wrds** | `:202` |
| `ownership.type_holdings_13f` | `sec13f_type_holdings` | **sec** | `:252` |
| `ownership.type_sector_13f` | `sec13f_type_sector` | **sec** | `:255` |
| `ownership.type_flow_13f` | `sec13f_type_flow` | **sec** | `:257` |
| `identity.etf_holdings` | `etf_holdings` | **ssga, ishares** | `:113` |

## 3. The builder datasets that call UW **(new — the cadence view)**

Registered in `rcdata/build/__init__.py:18-70`.

| Dataset | Endpoint(s) | Cadence | Serving tables |
|---|---|---|---|
| `uw/option_list` | `expiry-breakdown`, `option-contracts`, `greeks`, `spot-exposures/strike`, `greek-exposure/strike`, `greek-exposure/expiry`, `flow-per-expiry`, `volatility/term-structure`, `gex-levels`, `options-volume`, `interpolated-iv`, `iv-rank`, `flow-recent` — `rcdata/build/options/uw_list.py:1-17` | per session | `option_eod`, `option_strike`, `option_expiry`, `option_daily`, `iv_daily`, `option_print` |
| `uw/option_screener` | `/earnings/premarket`, `/earnings/afterhours`, `/screener/stocks` — `rcdata/build/options/uw_screener.py:4-12` | per session | `option_screener_daily`, `er_options`, `earnings_tape` |
| `uw/far_contracts` | `/screener/option-contracts`, `/market/oi-change` — `rcdata/build/options/uw_far_contracts.py:7-16` | per session | `option_far_contract` |
| `uw/spot_expiry_strike` | `/stock/SPX/spot-exposures/expiry-strike` — `rcdata/build/uw_spot_expiry_strike.py:37` | per session | `spx_gamma_expiry_strike` |
| `uw/greek_expiry_strike` | `/stock/SPX/greek-exposure/strike-expiry`, `/greek-exposure/expiry` — `rcdata/build/uw_greek_expiry_strike.py:53-54` | per session | `spx_greek_expiry_strike` |
| `uw/economic_calendar` | `/market/economic-calendar` — `rcdata/build/uw_economic_calendar.py:45` | **hourly** (`:116`) | `economic_event` |
| `uw/fda_calendar` | `/market/fda-calendar` — `rcdata/build/uw_fda_calendar.py:42` | **hourly** (`:145`) | `fda_event` |
| `uw/total_float` **(new)** | `/short_screener`, 100 names a request — `rcdata/build/prices/floats.py:14-16`, `:217`, `:251-252` | **daily** (`:220`) | the float beside Yahoo's |
| `uw/earnings` | `/stock/{t}/earnings` — `rcdata/build/fundamentals/uw_earnings.py:10` | weekly (`:148`) | `earnings_reported` |
| `uw/institutions` | `/institutions` — `rcdata/build/ownership/uw_institutions.py:54` | quarterly (`:267`) | the 13F type slices |
| `spine/etf_holdings` | `/etfs/{etf}/holdings`, after the SSGA and iShares CSVs | per session | `etf_holdings` |

**Call volume, as the code models it** (`rcdata/build/options/__init__.py:18-43`): a list name costs
`LIST_CALLS = 11` plus 2 per expiry plus a call per extra page; the measured run of the plan took **207 UW calls**
(AAPL 57, NVDA 61, SPX 64, screener 25), and `uw/far_contracts` adds **about 420-435 calls a session** of its own
(`:13`). The true count is `provider_calls_daily`, per request.

## 4. The board surfaces

| Board | How it reaches UW |
|---|---|
| **SPX Gamma** | the widest single surface: `module_spx_gamma/snapshot.py:96-118` names 12 endpoints in one snapshot (`gex-levels` ×2 sources, `greek-exposure/expiry`, `greek-exposure/strike`, `interpolated-iv`, `max-pain`, `iv-rank`, `options-volume`, `volatility/term-structure`, `volatility/variance-risk-premium`, `volatility/realized`, `greek-flow`, `/market/economic-calendar`) plus the VIX book at `:115-118`, and `flow-per-strike` through `normalize.py:137`, `raw_day.py:35` |
| **Earnings Radar** | `READS` = `earnings.next`, `earnings.options`, `earnings.tape`, `options.screener`, `market.economic_calendar`, … (`module_earnings_radar/__init__.py:1-4`), plus live client calls |
| **Swing Potential** | `module_swing_potential/flow.py:19-26` — `flow_recent`, `aggregate_flow`, `spot_exposures_by_strike` |
| **LEAPS** | `READS = ("options.far_contracts",)` — `module_leaps/__init__.py:1` |
| **News** | `market.economic_calendar`, `market.fda_calendar` — `module_news/__init__.py:14` |
| **OIPD** | `module_oipd/uw_chain.py:1-8` maps `/option-contracts` + `/expiry-breakdown` rows into the chain |
| **Sector Rotation** | ETF holdings, third after SSGA and iShares |
| **SEC 13F** | the UW institution tags only; the holdings are the SEC's |
| **UW Interaction (lab)** | 42 endpoints in `module_uw_interaction/catalog.py`, live-only, writes `.cache/` not `.store/` (`config.py:1-9`) — a lab, nothing depends on it |

## 5. Dead surface

21 client methods have **no non-test caller**: `calendar_day`, `calendar_range`, `earnings_rows`, `fundamentals`,
`financials`, `income_statements`, `balance_sheets`, `cash_flows`, `dark_pool`, `dark_pool_net`, `greeks`,
`greek_exposure`, `greek_exposure_by_strike`, `greek_exposure_by_expiry`, `flow_alerts`, `expiry_breakdown`,
`insider`, `economic_calendar`, `ohlc_daily`, `etf_flow`, `screener_stocks`. They are deleted, not ported.

## 6. What the inventory says

1. **This is an options migration.** Every UW-only need is options, Greeks, IV, flow or the earnings tape. Every
   non-options UW need already names `sec`, `wrds`, `ssga`/`ishares` or a fallback.
2. **One file to re-point**, plus `providers=(...)` in the catalogue — no board calls UW outside the client.
3. **Nothing streams**, so a daily batch replacement is enough for every table that exists today. The streaming
   question only appears if we build a live flow alert (`05_migration_plan.md`, lane C).
4. **Dark pool, congress, insider and prediction markets are not used in production** — they exist only in the
   lab's catalogue. Nothing has to be replaced for them.
