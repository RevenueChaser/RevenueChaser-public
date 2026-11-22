# spine.duckdb: the open issues, the order they land in, and the decisions

Written 2026-11-22 (times are Europe/Amsterdam). A planning note: **no code was written, no PR built and no live
store read for it.** The code was read at `main` `400073a` and the citations below were re-checked at `ba49037`.
Nothing here has started; each live step waits for the owner's word.

How to read the marks:

- **[M]** a number measured on the live store on 21 Nov 2026 by the audit behind the issues. Not re-measured here.
- **[C]** confirmed in the code, with `file:line`.
- **[I]** an inference. Not verified.

Tracking: the umbrella is **store_spine #1389**; the audit's spine items are in #1418, the identity items in
#1334, ETF holdings in #354 and #1365. Indirect effects sit under store_prices #1390, store_ownership #1395 and
store_fundamentals #1392. The audit's item names (K-A … K-H, G-11) are kept because the issues use them.

## 1. What already changed (the issue texts are older)

- **Tier rule v4 is merged** (#1352): where the SEC file names no exchange, Compustat's `exchg` stands in
  (`rcdata/build/spine/tier.py:79` `COMPUSTAT_LISTED`, `tier.py:90-91`, `VERSION = 4` at `tier.py:53`) [C].
  This closes the audit's K-D in code. Whether it is live is not known: the live file was at schema 9 [M].
- **Country columns are in code** (#1297): `security.country`, `country_source`
  (`rcdata/build/spine/security.py:92`), spine schema 10 (`rcdata/serving_versions.py:10`) [C]. Live was 9 [M].
- **TickerInside reads 28 ETFs' holdings instead of UW** (#1366, merged 22 Nov): `TI_FUNDS`,
  `rcdata/build/spine/etf_holdings.py:173` [C].
- **The WRDS `attended` gate** is the reason `wrds/sec_idhist`, `wrds/co_hgic` and `wrds/idxcst_his` never run on
  their own: `cadence = "monthly"` but `attended` (`rcdata/build/spine/wrds.py:417-418`) [C]. #1361 / PR #1362
  changes that line. `idxcst_his` not having been fetched since 28 Oct [M] is most likely this gate [I].

## 2. The items

| # | Item | What is wrong | Spine tables | Who depends on it | Risk |
|---|---|---|---|---|---|
| 1 | Schema 10 + tier v4 live | Code is at 10 and v4, the live file at 9 [M]: no country, and CFR, IBOC, TXCP still Tier D | `security` (two columns, tier), `my_universe` | every screener (tier), Asymmetric Growth (country) | Low. Ids do not move [I]: the link is the same, only tier and country change |
| 2 | WRDS gate (#1361) | see section 1 | indirectly `security`, `gics_history`, `security_history`, `index_membership` | K-F's `idxcst_his` freshness, K-G | Medium: it changes a job the dashboard runs, so its own PR. The first unattended monthly snapshot may change many spine rows at once |
| 3 | K-B: 304 Tier A names typed `unknown` [M] | The type comes from OpenFIGI; with no FIGI it stays `unknown`, and an unknown type on a listed exchange is Tier A (`tier.py:94-95`). `TPCI_TYPES` knows three codes (`tier.py:104`) [C] | `security` (type, tier), `my_universe` | every screener, the prices universe | Medium: a real company typed wrongly drops to Tier B and leaves the screens |
| 4 | K-C: the link needs CIK equality | `link()` goes SEC CIK → Compustat gvkeys → ticker match, else `only_security` (`security.py:317-329`) [C]. Of 188 unlinked Tier A names, 172 have an active Compustat security with the same ticker; its CIK is empty for 159 and different for 13 [M] | `security` (gvkey, iid, cusip, isin, figi, gics, sic, country), `security_history`, `gics_history`, `index_membership` | **the prices id** (`prices/__init__.py:72-79`) [C] | **High**: a wrong link is a wrong CUSIP and a wrong price series |
| 5 | K-G: delisted names in Tier A | ARI, BWMN, ROKU are inactive in Compustat but Tier A [M]. `secstat` and `dldtei` are staged; the tier rule does not read them [C] | `security` (tier) | `my_universe`, screeners | Low to medium. Only meaningful once the monthly snapshot is fresh (item 2) |
| 6 | K-A: ETF identity | 5,785 of 6,314 `etf` rows have no `security` row [M]; `etf` has no gvkey, CUSIP or FIGI column (`etf.py:43-54`) [C]. Prices links on its own (`prices/wrds_history.py:730` `GVKEY_ALIAS`; a member the spine does not hold becomes `sym:`, `prices/__init__.py:181`) [C] | `etf` gains identity columns: **schema 10 → 11** | prices ids, options (IWM, QQQ, SPX), G-11 | **High**: an id change moves bars |
| 7 | K-H: `etf` gaps | `expense_ratio` is always NULL (`etf.py:256`), `asset_class` only ever `commodity` (`etf.py:249`) [C]; `series_id` 33 % and CIK 29 % empty [M] | `etf` | the `my_universe` ETF rule (AUM) | Low |
| 8 | K-F: index membership files | Three Vanguard files and `nasdaq-NDX` fail every day [M] (`rcdata/build/spine/funds.py:238-246`). DIA is fetched but no `dow` membership is written: `INDEXES` (`funds.py:50`) leaves it out, `funds.py:248` [C] | `index_membership`, the `index_constituents` view | every index filter | Medium: membership is a vote, "held by more than half the files" (`security.py:421`), so adding or removing a file changes the denominator |
| 9 | OpenFIGI error queue | A job that answers `error` becomes `None`, is written nowhere and is asked again every run (`rcdata/build/spine/openfigi_map.py:240-246`, `251-261`, `354-358`) [C]. The queue grew 2,937 → 3,635 [M] | `security` FIGI fields, indirectly | K-B (the type comes from the FIGI) | Low |
| 10 | `my_universe` churn | 151 names entered and left more than once in two weeks [M]. Entry and exit use the same number (`my_universe_rules.json:12-13`) [C] | `my_universe`, `my_universe_changes` | the prices universe, every screener | Low. The rules file is the owner's |
| 11 | `member_not_in_sec` noise | Cash and futures lines of the fund files are written as issues (`security.py:759-767`) [C] | none (ops issues only) | the Data health counters | Very low |
| 12 | 17 universe names not Tier A | `my_universe_rules.json:7` admits Tier D on purpose [C]. Most of the 17 may be empty-exchange Tier D names that item 1 turns into A [I] | `my_universe.tier` | — | Possibly no code: re-count after item 1 |
| 13 | K-E: renames do not reach other stores | CIK-keyed tables hold 14-29 old keys, ticker-keyed ones 25-48 [M] | none in the spine [I]; the source is `security_history` | fundamentals, ownership, estimates builds | Medium: the work is in the reading stores |
| 14 | G-11: 13F does not map ETF CUSIPs | 12,540 CUSIPs, 9.5 tn USD unmapped [M]. `sec13f_cusip_map` joins the spine's `security` only (`rcdata/build/ownership/serve.py:876-902`) [C] | none; needs K-A's CUSIPs | the 13F board | Last |

No other open issue writes under `rcdata/build/spine/` (43 open issues scanned on 22 Nov).

### Files more than one item touches

| File | Items | Rule |
|---|---|---|
| `spine/security.py`, `spine/tier.py` | K-B, K-C, K-G | one PR, one tier version step (4 → 5) |
| `spine/etf.py` | K-A, K-H | one schema step (11): identity columns and the K-H fill together |
| `spine/my_universe.py` + rules file | hysteresis, K-A | hysteresis first |
| `rcdata/tests/spine_fixture.py` | every identity PR | branch from `main` after #1366 (it changed the fixture) |
| `spine/wrds.py` | #1362 | anything else touching it waits for #1362 |

## 3. The owner's decisions (22 Nov 2026)

Each is a direction, **not** a word to start. Quotes are avo's own.

| Time | Question | Decision |
|---|---|---|
| 12:57 | K-A: one owner for ETF identity? | "bu mantikli" — the spine owns it: `etf` gains gvkey, iid, CUSIP, FIGI and prices reads them from there |
| 12:59 | ETF holdings model | "gunluk okunan TickerInside, sonra ceyreklik N-PORT ile final duzeltme ve lock" — daily layer from TickerInside (the 93 narrow funds with no daily source included), and once a quarter closes SEC N-PORT is its final record |
| 13:00 | what "lock" means | "aynen oyle N-PORT artik final set olmali" — a closed quarter's rows are never overwritten again |
| 13:01 | Vanguard and `nasdaq-NDX` files | "Onarılsın" — repaired, not removed. Read the failing status code first, then fix the URL or the parser |
| 13:03 | `dow` membership | "Tabi yazilsin" — written from the DIA file; one file, no vote |
| 13:04 | `my_universe` exit floor | "cok dogru, bu kadar sapmalar" — exit 20 % under entry: AUM 100 M in / 80 M out, 20-day dollar volume 10 M in / 8 M out |
| 13:34 | K-H | "evet doldur" — `etf.expense_ratio` and `etf.asset_class` are filled from TickerInside's fund file, in the same schema step as K-A |
| 13:35 | G-11 | "Evet bu istedigimiz bir sey" — the 13F board shows ETF positions too. The spine's part is K-A; the board side is #1376 |

UW is not used for ETF holdings at all (#354 D3).

## 4. What TickerInside can and cannot supply

Measured 22 Nov with one request each (keyless, CC BY 4.0, a snapshot not a history; the figure must carry an
attribution link where it is shown). `identifiers.json`, `read_on` 2026-11-20, 10,945 rows:

| | rows | composite FIGI | CIK | SEC series id | class id |
|---|---|---|---|---|---|
| ETF | 5,918 | 5,831 | 4,892 | 5,520 | 4,744 |
| ETN | 15 | 15 | 15 | — | — |
| stock | 5,012 | 4,998 | 5,006 | — | — |

It is assembled from OpenFIGI, the SEC ticker files and Nasdaq Trader, so it is a ready-made join, **not an
independent second source**. It is keyed by ticker (`BRK.B`, ours is `BRK-B`), and a ticker can change hands.

| | TickerInside file | Use in the spine | Step |
|---|---|---|---|
| T-1 | `identifiers.json` | `etf` FIGI, CIK, `series_id`. **No CUSIP and no gvkey anywhere**: those still come from Compustat | 7 |
| T-2 | `funds.json` | `expense_ratio` (96.8 % filled), `net_assets` (82.0 %), category (100 %). There is no `asset_class` field: derive it from the category's facet | 7 |
| T-3 | `fund/<ticker>.json` | daily holdings for all 133 narrow funds (76 from the issuer's file, 56 from the newest N-PORT): `TI_FUNDS` 28 → 133 | 4 |
| T-4 | `funds.json` layer and `report_date` | which layer and date each fund's list came from; the quarter-lock rule counts the difference against it | 9 |
| T-5 | `manifest.json` | sha256 per file: fetch only what changed | 4 |
| T-6 | `status.json` | funds that were not refreshed, by name: written as a build issue | 4 |
| T-7 | `ownership.json` | the share of a stock held by ETFs. **Changes nothing in the spine and does not solve G-11** (no CUSIP) | — |

What it does not help with:

- **K-B.** BIPH, SAX, GECCG, PRH, TMUSI and AGLT are not in the file; it holds only what ETFs hold, and its type
  field is only `etf` / `etn` / `stock`.
- **The OpenFIGI error queue.** The queue is CUSIP jobs; the file has no CUSIP. OpenFIGI stays.
- **History.** `history/*`, `quarterly/*` and `flows*` may not be collected on a schedule under the licence. The
  history and the lock come from our own SEC files.

## 5. The order

This is the order after the decisions. Steps 3, 4 and 5 are independent of each other; step 6's code does not
wait for step 1.

| Step | Work | PR | Schema | Live write | Waits on |
|---|---|---|---|---|---|
| 1 | Spine live at schema 10 (country) + tier v4 | none, the code is on `main` | 9 → 10 | a spine build (seconds, per `docs/data_architecture.md`; not timed here) | the owner's word |
| 2 | #1362 (WRDS gate) merged; #1366 is merged | existing | none | turning the TickerInside dataset on | #1362's CI |
| 3 | Small PR A: OpenFIGI error queue + `member_not_in_sec` noise | new | none | none | nothing |
| 4 | Small PR B: TickerInside 28 → 133 funds (T-3), manifest (T-5), stale-fund issue (T-6) | new | none | none | nothing (#1366 is in) |
| 5 | Small PR C: repair Vanguard and `nasdaq-NDX`, write `dow`, exit floors 80 M / 8 M | new | none (`dow` rows go into the existing table) | none | the failing status codes read on the server |
| 6 | Identity PR 1 (tier v5): K-B + K-C + K-G, with a mutation check | new | none | in step 8 | nothing |
| 7 | Identity PR 2: ETF identity in `etf` (K-A, T-1) + expense ratio and asset class (K-H, T-2) + the lock's columns (T-4) | new, its own PR | 10 → 11 | in step 8 | step 6 |
| 8 | **One live window**: spine build, then a prices whole build. The split fixes of #1413 ride the same build if ready | — | — | **yes** | the owner's word; steps 6 and 7 merged |
| 9 | Quarter lock: a quarter N-PORT has reported is final; the daily difference is counted and written | new | ownership side, decided then | ownership build | steps 4 and 8 |
| 10 | K-E: old CIKs and tickers translated in the fundamentals, ownership and estimates stores | one per store | none in the spine | per store | step 8 |
| 11 | 13F ETFs: the mapping (the spine's part is ready after 7-8); the board is #1376 | — | — | ownership build | steps 8 and 9 |

Acceptance for step 6: Tier A `unknown` under 30; a GICS gap under 5 % for each type; no index member in Tier D.
Acceptance for step 8 (K-A): for every `my_universe` name the spine's id equals the id of its bars, difference 0;
bars per id before and after; IWM and QQQ present in the options tables.

Step 1's checks: `security` row count unchanged; the tier distribution before and after; the share of `country`
filled; CFR, IBOC and TXCP are A; the `member_not_tier_a` count; item 12's 17 names re-counted. No prices build
should be needed [I]; verify on the box that the id difference is 0.

## 6. The gates of a live write

Every live step carries all four, and none is skipped for a "small" build:

1. A fresh, verified backup of each file the step writes.
2. An idle dashboard job queue (`/api/jobs`): the dashboard holds the DuckDB writer, so a build is started
   through it and never by a second writer.
3. A named rollback and its trigger. The swap keeps the previous file as `serving_prev/<kind>.prev.duckdb`
   (`rcdata/serving.py:289-297`); a copy taken before the build is the second line. Trigger for step 8: an id
   difference above 0, or a table that shrank with no explanation.
4. Counts before and after, **per id** for anything that touches identity.

The build is tried on the rented box first; its result is moved to the server only through the gates above.

What the swap guard does and does not catch: a table that loses more than 1 % of its rows refuses the swap
(`MAX_SHRINK`, `rcdata/serving.py:55`); a smaller loss swaps in and leaves one open `build_issues` row
(`serving.py:569`). `my_universe` and `etf_class` are in `SHRINKS_BY_CHOICE` and are not guarded at all. So a
wrong link that moves a few hundred `index_membership` rows passes the guard: that is why step 8 compares per id
and does not lean on the total.

## 7. Open risks, and what was not measured

- **Step 8 rests on an unmeasured assumption.** `prices/incremental.py:222-236` diffs the identity the live file
  was built with against the new one and reloads the securities whose universe, alias or link row changed [C];
  the identity issue says a whole build is needed. Which is enough has not been measured. Until it is, the plan
  counts a whole build: 2,257 s and 6.0 GB RSS in total [M], of which `prices/serving` alone is 1,694 s.
  **Measure this on the box before identity PR 1 is written**, because it decides whether steps 6 and 7 can go
  live separately.
- **K-C has no bound on false matches.** The second link path (ticker plus a CUSIP or name check) has to be
  measured on an old snapshot first. The 13 names whose Compustat CIK is *different* (AGLT, XTLB among them) are
  the risky group and should stay unlinked unless a second identifier agrees. Every name linked by the new path
  gets its own `link_source` value and its own issue kind, so it stays visible.
- **ETF identity joins two sources by ticker** (TickerInside and Compustat). `etf.py` already chooses one SEC
  series per ticker; the new columns have to use that same choice, or a ticker that changed hands links the old
  fund's CUSIP to the new fund.
- **The first unattended WRDS snapshot** after #1362 may move many spine rows in one build. Read the build's
  counts that day before step 6's numbers are taken as a baseline.
- **Removing or repairing an index file changes the vote's denominator** (`security.py:421`). Compare
  `index_membership` per index before and after step 5.
- **Not measured here:** the live spine's schema version and build state today; the spine build's duration; the
  real tier of item 12's 17 names; whether #1362's first run closes K-F's `idxcst_his` line.

## 8. Second review

The plan was given to the cross-model review (one round) on 22 Nov with eight criteria: order and dependencies,
identity safety, a single ETF identity owner, the live-write gates, the tier and type rules, hysteresis, the
TickerInside + N-PORT lock, and what the plan missed. **Its findings are not in this note yet**; they are added
here when the run returns, and section 7 already carries the three findings of the author's own review.
