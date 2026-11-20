# Data-system ideas from other open-source projects

Read-only research, 20 Nov 2026, for avo's ask: "what can be done about our data system — we can take
development ideas from other repos too". Fincept is reviewed in its own thread and is deliberately **not**
repeated here.

Read first: [`data_architecture.md`](data_architecture.md) (the builder, the serving kinds, the swap rule, the
ops store), [`data_health.md`](data_health.md) (the dataset registry, freshness states, `/metrics`) and
[`data_retrieval.md`](data_retrieval.md) (Fetch vs Refresh). Every idea below is written against what those
documents say exists today; nothing here is a plan that was approved, and nothing here was built.

**Tags.** `[OKUNDU]` = read in the named source (its docs, README or licence page) or in our own code at the
cited `file:line`. `[ÇIKARIM]` = our own inference from those two, not something a source states.

**Licences.** Ideas only. No code is copied from any project below. AGPL-3 (OpenBB) and GPL-3 projects are read
for their design and never vendored, as `data_health.md` §6 already rules for `edgar-crawler`. Where a licence
is quoted it was read on the project's own page on 20 Nov 2026.

---

## The ranked list

| # | Idea | Source | Effort | Risk |
|---|---|---|---|---|
| 1 | Bitemporal read: "what did we know on day D" | [microsoft/qlib](https://github.com/microsoft/qlib) PIT, [pit-fundamentals-store](https://github.com/narasimhamungi/pit-fundamentals-store) | M | low–med |
| 2 | Declarative per-table expectations as the swap gate | [Elementary](https://pypi.org/project/elementary-data/), [SQLMesh audits](https://github.com/TobikoData/sqlmesh) | M | low |
| 3 | Row-count anomaly instead of one flat 1 % shrink rule | [Elementary](https://pypi.org/project/elementary-data/) | S–M | low |
| 4 | Generate the data-flow diagram and lineage from the registry | [SQLMesh column-level lineage](https://sqlmesh.readthedocs.io/en/stable/faq/faq/) | S | very low |
| 5 | Cross-check the hand-typed NYSE holiday table in CI | [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars) | S | very low |
| 6 | Declarative incremental cursors + schema contracts for ingest | [dlt](https://github.com/dlt-hub/dlt) | M | low–med |
| 7 | A real dirty set per dataset (fingerprint of its rules) | [SQLMesh plan](https://github.com/TobikoData/sqlmesh) | L | med |
| 8 | Blocking checks: a need refuses to serve on a failed upstream | [Dagster asset checks](https://docs.dagster.io/guides/test/data-freshness-testing) | S | low |
| 9 | More than one snapshot back: a catalog with time travel | [DuckLake](https://ducklake.select/) | L | med–high |
| 10 | One standard field name per concept across providers | [OpenBB](https://github.com/OpenBB-finance/OpenBB) (AGPL-3, ideas only) | L | med |
| 11 | Delisted names: a decision, not a fix | our own universe rule | — | avo's call |
| 12 | Vector index for Relatedness: **do not** take it yet | [DuckDB `vss`](https://duckdb.org/docs/current/core_extensions/vss) | — | rejected |

---

### 1. Bitemporal read: "what did we know on day D"

`[OKUNDU]` Qlib's point-in-time database exists for one reason, in its own words: "the same piece of data may be
amended for multiple times overtime. If we only use the latest version for historical backtesting, data leakage
will happen." It stores one row per statement, each carrying a publication date and a period
([qlib PIT docs](https://qlib.readthedocs.io/en/latest/advanced/PIT.html), MIT).
`pit-fundamentals-store` says the same with database words: separate **valid time** (the period) from
**knowledge time** (when we learned it), so a restatement cannot leak backwards.

`[OKUNDU]` We are half-way there already. `data_architecture.md` → Fundamentals: "**Every value carries its
filing**" — accession, filed date and form — and `fundamental_revision` records every Compustat value that
changed between two monthly snapshots. What we serve, though, is the newest fact per period: a restated 2024 Q2
replaces the figure we read in 2024, and no reader can ask for the earlier one.

`[ÇIKARIM]` **What we would change.** One optional argument on the read path, `rcdata.read(..., known_as_of=D)`:
serve, per (security, period, concept), the newest row whose `filed_date <= D`. The rows needed for SEC facts are
already stored; this is a filter and a second index, not a new ingest. For Compustat it needs the snapshot day on
the revision rows. Then Forecast, Asymmetric Growth and any later backtest read a world that cannot see the
future.

**Effort** M (one serving-version bump on `fundamentals`, a whole rebuild of that kind, plus the read path).
**Risk** low–med: a bump is its own PR with a checkpoint (CLAUDE.md), and nothing that reads today changes
meaning while the argument is unset.

### 2. Declarative per-table expectations as the swap gate

`[OKUNDU]` SQLMesh runs **audits** as part of `plan`/`run` — small declarations such as "this column has no NULLs"
or "no duplicates" — and the plan is not applied when they fail (Apache 2.0; its FAQ). Elementary ships the same
family as dbt tests that "collect metrics and metadata over time" and compare each run with history (Apache 2.0).

`[OKUNDU]` Our swap gate today is: the `serving_schema_version` row, every table's row count, a `failed`
`dataset_check` row, every live table present, and the 1 % shrink rule — plus `prices`' per-security-id check with
a 5-bar tolerance (`rcdata/build/prices/serving.py` `_refuse_shrink`, #1096). That is a strong *volume* gate and
no *content* gate: a table can swap in with a NULL key, a duplicated primary key or a price of 0 as long as the
count holds.

`[ÇIKARIM]` **What we would change.** A per-table declaration beside each dataset — not-null columns, unique key,
value ranges, "every row's `session_date` is in the calendar" — evaluated in the build file before the swap, each
failure a `build_issue` and, above a named severity, a refusal. The shape already exists (`build_issues`,
`dataset_check`); what is missing is the declaration, so the rules stop being hand-written per dataset.

**Effort** M. **Risk** low, as long as the first round runs in warn-only mode for a week and the severities are
set from what it actually finds.

### 3. Row-count anomaly instead of one flat 1 % shrink rule

`[OKUNDU]` Elementary's volume tests compare a run with the table's own history rather than a fixed threshold.

`[OKUNDU]` Ours is fixed: 1 % of the file's rows, `SHRINKS_BY_CHOICE` for the tables where that rule is wrong,
`allow_shrink` for the rest. #1096 showed the other half of the problem: a table may **grow** while 10 securities
each lose 32 bars.

`[ÇIKARIM]` **What we would change.** `dataset_check` already keeps rows/added/removed per run for 365 days
(`ops.RUN_ROWS_DAYS`). Compare a build's delta with that dataset's own distribution (a robust z-score, or simply
"more than 5× the median daily add, or any removal where the median is 0") and put the verdict in the build note;
refuse only where the per-key check already refuses. It is the generalisation of the per-id rule to every kind,
with the thresholds measured instead of guessed.

**Effort** S–M. **Risk** low: a note first, a refusal only once the distribution is seen.

### 4. Generate the data-flow diagram and the lineage from the registry

`[OKUNDU]` SQLMesh's selling point is column-level lineage computed from the models themselves, so "impact of
changes" is read before a run, never maintained by hand.

`[OKUNDU]` We keep a hand-drawn data-flow diagram on the Settings board (`data_health.md` §3.7) and
`data_health.md` §8 says the Stage 2/3 dataset tables in `data_architecture.md` are "still written by hand rather
than generated from `core/datasets.py`" — issue #146 is open for exactly that.

`[ÇIKARIM]` **What we would change.** The pieces of a true graph already exist in declarations: `DatasetSpec`
(tables, file, source, writer), each dataset's `tables` and `feeds` (`base.shrink_scope`), and each board's
`READS` over needs. One generator turns those into the diagram and into the doc tables, and a test fails when the
checked-in copy drifts. This closes #146 instead of adding a feature.

**Effort** S. **Risk** very low — generated docs, no runtime path.

### 5. Cross-check the hand-typed NYSE holiday table in CI

`[OKUNDU]` `core/calendar.py:39-75` is a hand-typed `_MARKET_HOLIDAYS`, 1993–2028, and rule C raises outside that
range rather than guessing (`core/calendar.py:25`) — a good rule. 2029 arrives as an exception, by design.

`[OKUNDU]` `exchange_calendars` ships `XNYS` and 50-odd other calendars, and says plainly that "all of the
exchange calendars are maintained by user contributions" — so it is a **second opinion**, never a source of truth.

`[ÇIKARIM]` **What we would change.** One offline test (the package pinned, no network) that compares our table
with `XNYS` over 1993–2028 and fails on a difference, with a small allow-list for differences we have decided.
A disagreement is then a CI failure rather than a wrong `session_date` in a build.

**Effort** S. **Risk** very low; it adds a test-only dependency, nothing in the serving path.

### 6. Declarative incremental cursors and schema contracts for ingest

`[OKUNDU]` dlt (Apache 2.0) makes two things declarations instead of code: an **incremental cursor** (a column
whose last value is kept in pipeline state between runs) and a **schema contract** with three modes — `evolve`,
`freeze`, `discard` — settable per table, column and data type.

`[OKUNDU]` Ours is per-dataset code: `sec/companyfacts` and `sec/filings` read the SEC daily index "of the last 7
days, or back to the day after their last whole run", with the state in `raw/sec/<name>/_scanned.json`;
`yfinance/fx` goes "from 7 days before the newest stored day"; `alpaca/corporate_actions` runs −14/+90 days. Each
is sensible and each is written again by hand.

`[ÇIKARIM]` **What we would change.** Not adopting dlt (it would own our ingest), but lifting its two
declarations into `rcdata/build/base.py`: a dataset declares `cursor = ("stg_x", "filed_date", {"lookback_days":
7})` and the base class derives the window, keeps the state in the ops store rather than a JSON file beside the
raw tree, and logs it. The contract half maps onto the staging tables: an unexpected provider column is today
dropped or breaks a stage, depending on the dataset; `freeze` vs `evolve` says which per source.

**Effort** M (one dataset at a time, no big-bang). **Risk** low–med: a wrong window silently narrows a fetch, so
each converted dataset needs its first run compared with the old one's counts.

### 7. A real dirty set per dataset

`[OKUNDU]` `rcdata/build/dirty.py` already holds the contract — cumulative ranges vs restated keys — and
`data_architecture.md` says the honest state out loud: "a dataset that declares none is `dirty.ALL`, which is why
every kind is still built whole today."

`[OKUNDU]` SQLMesh's answer to the same problem is a fingerprint per model plus a plan that classifies a change as
breaking or non-breaking, and only then backfills what the change touched.

`[ÇIKARIM]` **What we would change.** Give the heavy datasets (`fundamentals/tables`, `prices/serving`,
`ownership/serve`) a `dirty(ctx)` of their own, keyed on the source partitions that moved since the last build,
and treat a change in the dataset's own rules fingerprint as "full" exactly as the serving-version bump already
does. The prize is the hourly pass stopping its whole-kind rebuilds — the same pass that is OOM-limited to one
heavy dataset (#812).

**Effort** L. **Risk** med: a dirty set that is too small serves stale rows, which the counts would not catch, so
each one lands with a whole-build comparison.

### 8. Blocking checks: a need refuses to serve on a failed upstream

`[OKUNDU]` Dagster's asset checks can be `blocking`: when a check fails with ERROR severity, downstream assets do
not execute.

`[OKUNDU]` We have the states (`rc_dataset_state`: fresh, unchanged, late, stale, never) and the swap refusal, and
the needs layer reports freshness, coverage and provenance on every `ask()`. What it does not do is refuse.

`[ÇIKARIM]` **What we would change.** A need declares what it will not serve under (for example: an upstream
dataset whose newest `dataset_check` is `failed`, or a staleness past its catalog limit), and `ask()` answers with
that marker instead of rows, which the boards already render as "not stored". It is a declaration over state we
already keep.

**Effort** S. **Risk** low, and it is the cheapest honesty win on the list.

### 9. More than one snapshot back: a catalog with time travel

`[OKUNDU]` DuckLake (MIT) keeps metadata in a SQL catalog — PostgreSQL, SQLite, MySQL or DuckDB — and data in
Parquet, records each write as a snapshot, and reads a past version with `AT (VERSION => n)`; old Parquet files
are not overwritten.

`[OKUNDU]` Our rollback is one deep: the live file is copied to `<kind>.prev.duckdb` under `serving_prev/` and
`os.replace` swaps the new file in. Two bad builds in a row and the good file is gone.

`[ÇIKARIM]` **What we would change.** The cheap half first, and it is not DuckLake: keep N `prev` files per kind
(a week), since the raw disk holds them and the restore path already exists. The expensive half — the catalog in
`ops` and the data in the Parquet we already write — would make "what did `prices` serve on 12 Nov" answerable
without a restore, and is what the ownership and fundamentals lanes would want for a real audit trail. DuckDB as
the catalog is single-client, which fits our one-writer rule.

**Effort** L (the N-deep `prev`: S). **Risk** med–high for the catalog: it is the read path of every board. The
N-deep `prev` is low risk and should go first.

### 10. One standard field name per concept across providers

`[OKUNDU]` OpenBB is AGPL-3, so this is read for its shape only: a standard model per concept and a mapping per
provider, so a field has one name whatever answered.

`[OKUNDU]` We do the equivalent per dataset, and the cross-check report (`module_settings/newdata.py`,
`/api/settings/status` → `cross_check`) is already "the stored second-source report per field".

`[ÇIKARIM]` **What we would change.** Little, and that is the finding: our served tables are already the standard
model. The one gap worth naming is that the second-source agreement rules (within 0.5 %, EPS within a cent,
period ends within 7 days) are written per dataset in prose and in code; one table of them, read by both the check
and the doc, would make them one source of truth. Low value against items 1–8.

**Effort** L if taken as a layer, S as the rules table. **Risk** med as a layer; S version is low.

### 11. Delisted names: a decision, not a fix

`[OKUNDU]` `data_architecture.md` → prices: what the store keeps is **today's universe** (avo, 4 Nov 2026), and
with it "CRSP serves no bar at all" because "no delisted name is in it".

`[ÇIKARIM]` Every open-source backtest stack treats this as the first bias to remove (it is why qlib's PIT exists
and why academic sets keep delisted securities). Today's universe is a standing decision and this document does
not argue with it; the consequence is simply that no board built on this store can measure a strategy over names
that stopped trading.

**The decision only avo can make:** does any board ever need delisted names (a `delisted` tier the daily fetches
skip, filled once from Compustat/CRSP history), or is the answer "no backtests over dead names, by design"? If
the answer is no, item 1's value drops to live boards only, which is still real.

### 12. Vector index for Relatedness: do not take it yet

`[OKUNDU]` Relatedness loads **every** stored vector into memory and scores in Python
(`module_relatedness/store.py:185-189` `load_vectors`, `rawstore.get_all("relatedness_embeddings")`).

`[OKUNDU]` The obvious upgrade, DuckDB's `vss` extension, says of itself that HNSW persistence is experimental,
off by default, that WAL recovery for custom indexes "is not yet properly implemented", and recommends against
production use.

`[ÇIKARIM]` So: keep the brute-force scoring. At our universe size it is a numpy matrix multiply, and a stale or
corrupt index is a worse board than a slower one. Revisit when DuckDB drops the experimental flag.

---

## What we would not take

- **Adopting an orchestrator** (Dagster, Prefect, Airflow). Our scheduling is systemd timers and the hourly
  builder pass; `data_health.md` §7 already rules out scheduling inside the application. Their *vocabulary*
  (assets, checks, freshness policies, partitions) is what items 2, 3 and 8 borrow.
- **dbt / SQLMesh as our transformation engine.** Our builds are Python around DuckDB with memory limits, spill
  folders and a per-kind swap; a SQL-model engine would own all of that.
- **Vendoring any GPL/AGPL code** — `edgar-crawler` (GPL-3) and OpenBB (AGPL-3) are read, never copied, as
  `data_health.md` §6 already decided.

## Suggested order, if avo wants any of it

4 and 5 first (both small, both close an open hole: #146 and the hand-typed calendar), then 8, then 3, then 1,
then 2. 6, 7 and 9 are each their own lane and should not be opened while the F-band lanes are running.
