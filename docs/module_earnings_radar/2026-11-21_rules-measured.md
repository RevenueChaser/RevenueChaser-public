# Earnings Radar — 8 rules, measured (read-only)

Measured 2026-11-21 ~00:30 Amsterdam on homesrv, read-only. No deploy, no push, no job, no POST,
no paid LLM call, no timer change, no DuckDB write (every handle `read_only=True`, `RC_STORE_AUTO_ENSURE=0`,
no pytest). Scripts in the session scratchpad, not in a repo.

## Where the board files actually are

`RC_CACHE_DIR=/mnt/data/apps/revenuechaser/data/cache` (`/etc/life/rc-paths.env`).

- There is **no `earnings/` subdirectory** on this box, so **0 files match `revenue_chaser_<ts>.html`**
  (`module_earnings_radar/report.py:1776` writes that name; the history is not kept here).
- The only Earnings Radar board file is **`/mnt/data/apps/revenuechaser/data/cache/earnings_radar_latest.html`**
  (`app/runners.py:149`), 523 354 bytes, mtime **10 Nov 2026 12:59**, mode 600 owner `life`.
  It holds `DECISION_DATA`, so it was measured. Everything below is that one file — **11 days old**,
  one board run, not a distribution over runs.

## Newest (only) board file: 35 cards

- actions: `NO_TRADE` 8, `WATCH` 14, `SHARES_BULL` 5, `DIRECTIONAL_WATCH` 6, `SHARES_BEAR` 2
- bias: `BULLISH_LEAN` 11, `NEUTRAL` 19, `BEARISH_LEAN` 5
- direction: n=35 min=-20.0 p25=-6.2 med=2.2 p75=15.4 max=26.2 mean=3.7
- vol_edge: n=35 min=0.0 p25=0.0 med=10.0 p75=18.0 max=55.0 mean=12.1
- confidence: n=35 min=50.5 p25=64.6 med=70.2 p75=87.7 max=87.7 mean=74.3

| rule | role | available | avail% | score n | mean | median | pos | neg | zero | mean cov |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| R1 | logged (0%) | 35 | 100% | 35 | -5.8 | 0.0 | 17 | 16 | 2 | 1.00 |
| R2 | direction 20% | 34 | 97% | 34 | -9.6 | 0.0 | 9 | 13 | 12 | 0.74 |
| R3 | direction 20% | 33 | 94% | 33 | 9.1 | 15.0 | 20 | 12 | 1 | 0.80 |
| R4 | vehicle 0% | 35 | 100% | 35 | 12.1 | 10.0 | 25 | 0 | 10 | 0.99 |
| R5 | tag (no vote) | 35 | 100% | 0 | - | - | 0 | 0 | 0 | 0.64 |
| R6 | veto 0% | 35 | 100% | 35 | -6.0 | 0.0 | 0 | 14 | 21 | 1.00 |
| R7 | direction 15% | 28 | 80% | 28 | 17.1 | 20.0 | 26 | 2 | 0 | 1.00 |
| R8 | momentum 10% | 35 | 100% | 35 | 4.0 | 0.0 | 7 | 0 | 28 | 1.00 |

R5 score is null by design (tag, no vote). R4 never scores negative (25 pos / 10 zero / 0 neg);
R6 never scores positive (14 neg / 21 zero); R7 is almost all positive (26/28) and its median is 20.0,
i.e. the full weight. R8 fires on 7 of 35 and is 0 on the other 28.

### Top reason lines per rule (count, first 70 chars)

R1: `EPS estimate +0.0% over 30 days` 8 · `30-day revisions 0 up / 0 down` 7 · `1 up / 0 down` 5 ·
`0 up / 1 down` 5 · `2 up / 3 down` 3 · `2 up / 0 down` 3
R2: `mixed guidance quality` 9 · `high beat rate (75%)` 2 · `high beat rate (88%)` 2 ·
`consistent miss (-17.3%)` 1 · `consistent miss (-6.0%)` 1 · `strong beat history (14.0% recency-wtd)` 1
R3: `op. margin stable vs YoY` 3 · `franchise margin broke — GM fell with op. margin` 2 ·
`GM elasticity 0.6` 2 · `revenue growth 60%` 1 · `strong energy margins 58%` 1 ·
`op. margin vote skipped: pre-revenue (last-4 revenue $13.4M)` 1
R4: `long gamma (volume book: EM band net gamma green)` 10 · `short gamma (… red)` 3 ·
`IV/RV elevated (1.6) — vol rich, not cheap` 3 · `IV/RV elevated (1.3)` 3 · `IV/RV low (1.0)` 3 ·
`elevated EM (10.6%)` 2
R5: `neutral positioning` 21 · `institutional bearish lean` 4 · `institutional bullish lean` 4 ·
`thin institutional lean` 2 · `package-risk: multi-leg premium left out of the lean` 2 ·
`no squeeze pressure · FINRA settled 15 Oct` 1
R6: `rate event (FOMC/CPI) overlaps earnings — macro veto` 8 ·
`rate event overlap but duration not extreme — no veto` 2 · `extreme rate sensitivity (-10.1x)` 2 ·
`(-15.7x)` 2 · `(6.4x)` 2 · `(16.7x)` 1
R7: `low accruals (-1.69%)` 2 · `low accruals (-0.59%)` 1 · `cash well above earnings (-5.68%)` 1 ·
`low accruals (-3.73%)` 1 · `low accruals (-1.06%)` 1 · `low accruals (0.24%)` 1
R8: `retail share not extreme` 28 · `extreme retail call buying (78%)` 2 · `(83%)` 1 · `(82%)` 1 ·
`(80%)` 1 · `(100%)` 1

### R6 printed multiples (tail only, from the reason text)

n=33 min=2.5 med=14.1 max=47.4 —
2.5, 2.8, 3.1, 3.3, 3.5, 3.8, 6.2, 6.4, 6.4, 6.6, 7.4, 7.6, 8.3, 10.1, 10.1, 12.6, 14.1, 15.7, 15.7,
16.0, 16.7, 16.8, 16.8, 17.9, 21.6, 22.4, 22.9, 23.4, 24.4, 25.8, 27.3, 33.6, 47.4

Board tickers (35): ALC, AMBQ, AMPX, ANGX, BRSL, BTDR, CRWV, EC, ETOR, EXK, FLY, FOSL, HSAI, INO,
KOPN, KURA, LEGN, LPTH, LQDA, LWLG, NN, NRGV, ONON, PBR, QBTS, RGTI, SATL, SE, SRRK, STUB, TDG,
VELO, VG, WIX, WYFI

## Task 2 — R8 / #1214 step 1: EX-99.1 coverage

`sec_submissions` is a **view**, not a board table: it lives in the market layer file
`/srv/life/data/apps/revenuechaser/market/fundamentals.duckdb`
(`rcdata/build/fundamentals/tables.py:595` — one row per `cik, accession` over `filing_item` where
`kind='item'`, items as a comma-separated text). 3 499 788 rows, of which 495 150 are form `8-K`.
Ticker → cik comes from `security_master` in `/srv/life/data/apps/revenuechaser/market/spine.duckdb`.
The board DB `store/boards/fundamentals.duckdb` has only 3 tables and holds neither.

**`sec_submissions` stores no exhibit list.** It has `cik, accession, form, filing_date,
primary_document, items, source, fetched_at, run_id, run_at` — so **EX-99.1 presence itself is NOT
in the store** and cannot be measured from it at all.

Store numbers, form `8-K%` with item `2.02` in `items`, `filing_date >= current_date - 400`:

- all 35 board tickers map to a cik (0 missing, 0 null)
- **22 of 35** have at least one 8-K item 2.02 in the last 400 days
- **21 of 35** have one in the last 120 days
- median count per ticker among those 22: **5** (min 2, max 9)
- the 13 with none in 400 days: ALC, BRSL, BTDR, EC, ETOR, EXK, HSAI, LEGN, LWLG, ONON, PBR, SE, WIX.
  Most are foreign private issuers, which file **6-K** (238 892 rows in the view) and carry no 8-K
  item numbers — so any R8 rule keyed on 8-K item 2.02 structurally skips them, it is not a gap in the data.

SEC free filing index sample (plain GET, no key, UA = the repo's own SEC contact string (`core/providers/sec_edgar.py`, the contact from the environment),
0.35 s between requests): the newest item-2.02 accession of each of those 22 tickers, **22 sampled,
0 failures**.

- **21 of 22 carry an `EX-99.1`** (and the same 21 carry some `EX-99`); EX-99.1 size
  **n=21 min=70 806 median=273 298 max=1 484 146 bytes**.
- The one without: WYFI `0001213900-26-006189` (21 Jan 2026) — item 2.02 with no EX-99 exhibit at all.
- Caveat worth keeping: the exhibit **type** is only in the filing's `-index-headers.html` SGML
  (`<TYPE>EX-99.1`), and the tags there are HTML-escaped. `index.json` carries names and sizes but no
  type, and a file-name test is wrong: matching `ex99` in the name finds only **14 of 22**, because
  issuers name the exhibit `coreweave3q26earningspress.htm`, `exhibit991tdg2026q4earning.htm`,
  `ex_1042327.htm` and so on. A fetcher for #1214 must read the type, never the file name.

## Failed commands

- `python3` (system 3.14) has no `duckdb`; used `/srv/life/apps/revenuechaser/.venv/bin/python` instead.
- First SEC pass regexed `<TYPE>` against the raw `-index-headers.html` and found 0 of 22 — the tags are
  HTML-escaped there. Re-run with `html.unescape` gave the 21/22 above.

## Note on where this file sits

The job named `/srv/life/handoff/earnings_rules_measure_2026-11-21.md` as the only file to create, so it is
here. `/srv/life/CLAUDE.md` (MD RULE, avo 3 Nov) says nothing new is written under `/srv/life/handoff` and
every .md goes to `alsanvolkan/claude-coordinator` in the same turn — which needs a push, which this job
forbids. Unresolved on purpose: move it to the coordinator repo when a writing session can.
