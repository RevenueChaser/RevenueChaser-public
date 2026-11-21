# Edge counts and the service's answer inventory, 21 Nov 2026

Read on 21 Nov 2026 on homesrv, read-only, before the #894 step 4 deploy (PR #1229, merge `934f39ea`). They are
the "before" side of the step's own acceptance line: the first Value Chain build after the deploy is compared
with the last one before it.

## The board's edges before the deploy

`boards/value_chain.duckdb`, `chain_meta.last_sync = 2026-11-18T03:24:05Z`:

| source | rows | distinct tickers |
|---|---|---|
| profile | 45,898 | 4,135 |
| xbrl | 753 | 409 |
| **total** | **46,651** | — |

So the board is a profile board with an XBRL floor under it: if the service has no answers, the filings' own
XBRL edges stay and the board is not emptied.

For what the board **serves** rather than stores, the switch measurement of #1159 is the number: 951 → 3,761
pairs when `SERVE_PROFILE_EDGES` went on (customer 2,321 + supplier 1,440; 7.6% overlap with the XBRL edges).

## The SEC reader service's answers behind them

`market/sec_reads.duckdb`, `read_answer`, same read:

| question | prompt version | status | rows | distinct CIK |
|---|---|---|---|---|
| company.profile | v3d | ok | 5,126 | 5,119 |
| company.profile | v3d | no_text | 194 | 194 |
| debt.note | debt.note-1 | ok | 195 | 195 |
| debt.note | debt.note-1 | no_text | 970 | 970 |
| debt.note | debt.note-1 | empty | 5 | 5 |

Earliest answer 2026-11-15 10:37 CET, newest 2026-11-21 01:25 CET. Writers: deepseek 6,472 answers, evren 18.
This is also the confirmation that the `v3d` import of #894 step 2 has run.

A `partial` answer is not a profile: Value Chain filters on status, or it would draw edges from half-read
filings (#894 step 4 design).

## Still owed

The "after" counts — tickers with at least one `source = "profile"` edge, before and after the deploy — come
from the first build after the deploy (`life-rc-valuechain-sync.timer`, 04:20 Amsterdam) and are posted on
#894. They cannot be measured from a cloud session.
