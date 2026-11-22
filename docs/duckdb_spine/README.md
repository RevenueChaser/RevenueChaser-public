# `duckdb_spine` — a working folder for the spine store

What we learn about `spine.duckdb` as we go: which issues touch it, the order they have to land in, the owner's
decisions with his words and the time, measurements with the method that produced them, and what was **not**
measured. Notes accumulate here instead of being re-derived.

One note per session or investigation, named `YYYY-MM-DD_<slug>.md`, newest listed first.

| note | what it covers |
|---|---|
| [2026-11-22_issues-plan-and-decisions.md](2026-11-22_issues-plan-and-decisions.md) | Every open spine item (identity, ETF identity, index membership, tier rule, OpenFIGI queue, universe hysteresis) checked against the code, the same-file conflicts, the owner's six decisions, what TickerInside can and cannot supply, the 11-step order, the live-write gates and the open risks |

## The one thing to read before touching this store

**A spine change that moves a security's identity is a prices change.** The prices store keys every bar by
`security_id`, taken from the strongest identifier the spine holds (`rcdata/build/prices/__init__.py:72-79`:
`gvkey:iid`, else `figi:`, else `cik:<CIK>:<ticker>`, else `sym:`). A spine row that gains a Compustat link turns
a `cik:` or `figi:` id into `gvkey:iid`, and the bars have to follow. So an identity PR is never "spine only": it
is planned together with a prices build, a per-id before/after comparison, and a rollback for both files.

Two smaller ones:

- **The code can be ahead of the live file.** `SERVING_SCHEMA_VERSION["spine"]` is 10 in code
  (`rcdata/serving_versions.py:10`), and the live file was measured at 9 on 21 Nov 2026. Read the live version
  before reasoning about what a board sees.
- **ETF identity has two owners today.** The spine's `etf` table carries no gvkey, CUSIP or FIGI
  (`rcdata/build/spine/etf.py:43-54`), so prices links ETFs on its own path (`GVKEY_ALIAS`,
  `rcdata/build/prices/wrds_history.py:730`). The decision of 22 Nov 2026 is that the spine becomes the single
  owner; until that lands, a fix on one side does not reach the other.
