# prices.duckdb: what it holds, what it checks, and what it does not

A working log, written 2026-11-22 from a night of read-only measurement on homesrv. Every number carries how it
was obtained, so a later reader can re-run it rather than trust it. Code read at `400073ab`; the live store was
opened `read_only=True` throughout.

Written because the served stock history silently stopped at Thursday 2026-11-19 and nobody noticed for days.
Chasing that produced most of what is below.

## 1. What is served, and by whom

Measured on the live file (`SELECT source, count(*) ... GROUP BY source`):

| source | bars | securities |
|---|---|---|
| `wrds/compustat` | 30,925,311 | 10,592 |
| `market_series/cboe` | 8,530 | 1 (`index:SPX`) |
| **total** | **30,933,841** | 10,593 |

Range 1983-12-30 … 2026-11-20, but the newest **stock** session is **2026-11-19**: the only 2026-11-20 row is the
CBOE index. **No security has bars from two sources.** Names per session grows 574 (1984) → 1,020 (1994) → 2,006
(2004) → 3,581 (2014) → 6,932 (2022) → 8,766 (2026), so "history since 1983" is thin history until the 2010s.

**CRSP covers 82.9 % of the served sessions and wins none of them.** `HIST_SERVED = source <> 'wrds/crsp'`
(`prices/serving.py:231`) filters CRSP out of `_hist_all` *before* the winner `arg_min(priority, series)` runs, so
the served bar is always Compustat's. Alpaca's bars are never served at all — it is a tester (avo's own design,
quoted in `prices/bars.py`'s docstring).

**The one exception** is #661: a CRSP factor step that no Compustat or Alpaca action is near, between two served
bars at most `GAP_DAYS` apart, which the served close jumps `GAP_FACTOR` (1.9) or more across, is applied as a
`corporate_action` row with `source = 'wrds/crsp'` (`serving.py:791-794`) and takes effect **on read** through
`adj_factor`. It writes no bar — stored bars stay nominal by contract.

Verified live against the pre-deploy backup `backups/deploy-2026-11-21_661/prices.duckdb`:

| | live | backup |
|---|---|---|
| `corporate_action` with `source='wrds/crsp'` | **80 rows, 71 securities, all `applied`** | **0** |
| TNXP (`190856:01`) `adj_factor` boundary at 2018-11-28 | present, a ×10 step | absent |

A trap worth recording: **`price_bar_daily.source` can never show `crsp`**, so "zero crsp rows" is not evidence
the fix is absent. Checking the wrong table cost this thread an hour and a wrong report.

## 2. Where the data lives

`/mnt/data/apps/revenuechaser/data/market/` with two layers, `raw/` (as fetched, 24 GB) and `parquet/`
(normalized), over 19 sources. CRSP and Compustat share one WRDS connection, so there is no `crsp` folder:

| path | vendor | size |
|---|---|---|
| `parquet/wrds/prices/dsf`, `stkdelists` | CRSP | 1.1 GB |
| `parquet/wrds/prices/secd`, `sec_divid`, `sec_split` | Compustat | 1.0 GB |
| `parquet/alpaca/{bars, bars_revision, corporate_actions}` | Alpaca | 192 MB after the 2022 backfill |

**CRSP has no 2026 partition at all** — `dsf`'s newest is `year=2025`, and `CRSP_LAST_YEAR = 2025`
(`wrds_history.py:98`) caps the fetch. The module docstring gives CRSP's WRDS span as 1925-12-31 … 2025-12-31, so
the cutoff is the vendor's and the code's together. **Consequence: 2026 has no second source**, and 2026 is the
year any current backtest leans on hardest.

## 3. The comparisons, and what their numbers actually mean

`_report_parts` (`serving.py:1423`) writes one row per `COMPARISONS` entry into `wrds_price_diff`. Two things
about it are easy to misread, and this thread misread both:

- **`max_close_diff` is relative, not dollars**: `max(abs(x.close - y.close) / y.close)` (`serving.py:1431`). A
  reported 251.77 is **25,177 %**, not $251.77.
- **`close_differs` has no cent floor**: `abs(x.close - y.close) > TOLERANCE * y.close`, `TOLERANCE = 1e-4`
  (`serving.py:85`). For a $5 close that is $0.0005, so a one-cent rounding difference counts twenty times over.
  The Alpaca tester in the same file does it properly with `greatest(TOLERANCE * a.close, HALF_CENT)`
  (`serving.py:1490`, `HALF_CENT = 0.005` at `:93`). The two comparisons in one file do not use the same rule.

**Nothing reads `wrds_price_diff` back.** It is written and never consulted, so a tenfold rise in disagreements
is indistinguishable from a quiet day. It is also in `incremental.KEPT` (`incremental.py:54`), so a live-copy
build copies the row unchanged and only a **whole** build — held for a person by `whole_build_by_hand = True`
(`serving.py:590`) — refreshes it. There is therefore no daily series to calibrate any threshold from.

`crsp_vs_alpaca` reported **0 securities, 0 sessions** and nobody noticed: CRSP ends 2025 and Alpaca's partitions
began 2026-10-26, so the pair was disjoint by construction. The 2022 backfill (below) should end that.

## 4. The measurements, and the method that beats waiting for a build

**The method.** The comparison is SQL over tables the build stages *from parquet*, so it can be run read-only
against the parquet and the live file with no build, no writer turn and no swap. It is faithful: counting CRSP vs
the served close from parquet reproduced the build's own figures — **25,656,198 sessions compared (identical)**
and **313,203 differing against the build's 313,202**, one boundary row apart. The permno↔security_id link is in
the live store: `build_identity` rows with `what = 'link'`, `key` = permno, `how = 'hdrcusip'` (27,711 links).

Use this for any exploratory question about the prices data. A whole build is hours; this is seconds.

**CRSP vs the served Compustat close**, 25,656,198 sessions, 1983-12-30 … 2025-12-31:

| threshold | rows | share |
|---|---|---|
| no cent floor (what is reported today) | 313,203 | 1.22 % |
| with the half-cent floor | **257,850** | 1.01 % |
| rounding only | 55,353 | **17.7 % of the count** |

So the headline count is **not** mostly rounding: 82 % of it is real disagreement. Magnitudes, past the floor:

| difference | rows |
|---|---|
| 0.01–0.1 % | 19,138 |
| 0.1–1 % | 73,449 |
| 1–10 % | 103,698 |
| 10–100 % | 47,049 |
| > 100 % | 14,468 |

**The > 100 % tail is not missing splits.** It comes from only **24 securities**, and 95 % of its ratios are not
near a clean split factor — they drift (2.02, 2.03 … 2.17), with 3,241 distinct ratios across those 24 names,
about 135 each. A split holds one constant ratio until the next event; a ratio that moves daily is the signature
of two series on different bases, or a bad link, on a small set of names. 24 of 10,593 is a bug to chase, not a
policy question.

**The bulk (1–100 %, 150,747 rows) is a population, not a fault**: 2,074 securities, spread evenly by year
(8,208 rows / 293 names in 2008; 9,812 / 393 in 2016; 5,137 / 261 in 2023; 3,882 / 218 in 2025). Of the 338
securities with ≥ 50 rows, only **28 have a tight ratio** (systematic) and **310 are scattered**; 1,128
securities have ≤ 5 rows between them. That shape says sporadic bad or stale single-day bars, not a basis
mismatch.

**Net:** about **1 % of served bars differ from the second source by more than 1 %, every year, with no triage.**
99 % agree. It is persistent and invisible rather than catastrophic.

**Alpaca after the 2022 backfill** (request #1141, `backfill_from=2022-01-01`, 20 → 1,230 partitions, 6.8 MB →
192 MB, 3,587,055 bars over 7,241 securities, 2021-12-29 … 2026-11-20). Its parquet carries `security_id`
itself, so it joins the served bars with no link table. Overlap with the served bars went **81,608 → 3,545,076**
sessions (5,821 securities), i.e. 0.26 % → **11.5 %** of all served bars. Disagreements there: 10,253 without the
floor, 7,423 with it — rounding is 27.6 % of that count, and the largest relative difference is 7,346 %.

## 5. Why the fetch stops without saying so

`due.py:118-133` gates a dataset in this order. Live values measured 2026-11-22:

| gate | live state | holds `wrds/prices`? |
|---|---|---|
| `attended` | `RC_WRDS_UNATTENDED` unset, so `base.wrds_attended()` is True | **yes, this alone** |
| `dataset_mode` (**not** the kind mode — `ops.py:1207-1210`: "kind is no longer read") | `full` for `wrds/prices`, `alpaca/bars`, `prices/serving` (Redis `rc:ops:live`, set by `deploy-678`) | no |
| `starts_by_hand and not ever_built` | both `ever_built` True — a **first-run** guard only | no |
| pause / `next_due` | no hold | no |
| `EARLIEST_NY_HOUR` | `{"wrds/prices": 5}` — 05:00 New York | no, it only picks the hour |

So **`alpaca/bars` already runs daily on its own** and only `attended` stopped the WRDS fetch. The fetch record
was hand-driven: 10-30, 11-02, 11-03, 11-09, 11-15, 11-16, 11-17, 11-19, 11-20 at 07:17 / 09:33 / 11:12 / 14:10 /
21:13 / 22:05 — including a **Sunday 22:05**, so it was never a weekday rule. The last one landed Friday 14:05
UTC = 09:05 New York, before that day's open, so it could only bring Thursday.

`EARLIEST_NY_HOUR = 5` already encodes the right schedule: the fetch brings the **previous** session each New
York morning, so a one-session gap is the healthy state and two is the first fault. The retry guard (#344, #1115)
is keyed on `"wrds" in ds.providers` (`due.py:141`), not on `attended`.

**And the stall was invisible for a one-line reason.** `newdata._missed` already counts trading sessions from a
dataset's `source_as_of` to `calendar.latest_complete_session` (`newdata.py:266-276`); one missed is `late`, two
is `stale`, and it drives the Settings card, the "prices behind · last session" alert (`control.py:238-241`) and
Grafana's `rc_dataset_state{state="stale"}` (`metrics.py:61`, `:263-270`) — all at read time, no build. It stayed
silent because `check()` reads `max(session_date) FROM price_bar_daily` **with no filter**
(`serving.py:1250`) while `_issues` five screens up already uses `WHERE security_id NOT LIKE 'index:%'`
(`:1123`). The unfiltered query returned 2026-11-20, the lone CBOE index row, so `source_as_of` was a day ahead
of the truth and the gap read 0 instead of 1.

## 6. Seams worth knowing

- **Issues** need no new mechanism: declare a kind in `ISSUE_KINDS` (`serving.py:130-199`), append to
  `ctx.pending[NAME]`, and `after_swap` calls `ops.sync_issues(NAME, ISSUE_KINDS, found, ...)` (`ops.py:697`)
  which opens, keeps and resolves rows itself. `/metrics` already exposes `rc_dataset_open_issues` per dataset.
- **Reading the live file mid-build** is `prices/stage.py:57-80`: `ATTACH … (READ_ONLY)`, check
  `duckdb_tables()`, compare, `DETACH` in `finally`.
- **A code change does not restate old rows for the prices kind.** `dirty.py` (#814) keeps a code fingerprint per
  dataset and promises "a deploy that touches one dataset restates that dataset's tables", but
  `grep -rn "recoded\|plan\.dirty" rcdata/build/prices/ rcdata/build/base.py` returns **nothing** and
  `incremental.scope` reads only `plan.changed`. #661 reached history only because the *shared* fingerprint also
  moved, forcing a whole build — which must be hand-started. Anything shipped as a derivation fix needs a whole
  build to reach the past.
- **The delisted store was never built.** `delisted.duckdb` does not exist, though the code does
  (`delisted/serving.py`) and its input — CRSP's `dsf` and `stkdelists` — is already on disk, "no fetch, no
  network". It would hold `delisted_price_bar_daily` with `price_bar_daily`'s own columns, so dead names union
  onto the live table. It is the only available answer to survivorship. Its limits: CRSP's 2025 cutoff, no
  delisting **reason** (the fetch omits the type-code columns), no share type, and a `permno:*` key that joins
  live `gvkey:iid` bars only "where the link exists".

## 7. Open, and what I would not claim

- The nature of the 150,747 mid-range disagreements beyond their shape: not traced to a cause on any single name.
- Whether the 24 drifting-ratio securities are a basis mismatch or a bad link: not determined.
- Whether `wrds/prices.check()`'s own `source_as_of` (the snapshot day, `wrds_history.py:623-633`) being one
  session *ahead* of the bar it carries matters as much as the index-filter bug.
- The Redis ops state (`rc:ops:live`): open `build_issues` rows were never read here — no `redis-cli` on the box
  and the URL lives only in the secrets file.
- 2026 cannot gain a second source from CRSP. Alpaca's backfill covers its risky days only, by design.
