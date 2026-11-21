# The paid providers' money: the record and the day cap

The contract of `core/llm_spend.py`, `core/llm_prices.py` and `provider_spend_daily` — issue #166 item 3 (money)
and its gate. The metered providers' call counter is a different thing and stays where it was:
`provider_calls_daily`, written by the builder and by `core/providers/spend.py`, described in
[`data_health.md`](data_health.md).

## What is recorded

One row per **provider, model and New York day** in `provider_spend_daily` (`rcdata/ops.py`; a new table, no
`ops_schema` upgrade step, mirrored on Redis by `rcdata/ops_redis.py`):

| column | meaning |
| --- | --- |
| `calls` | paid answers that reached the caller |
| `tokens_in` / `tokens_out` | the tokens the gate reported for them |
| `usd_micros` | what they cost, in millionths of a USD |

`core/llm_spend.record(...)` writes it after a paid answer, straight through (no buffer: a paid answer takes
seconds, and the gate below reads the figure in the next breath). Only the paid writer goes through it — EVREN
has its own client and costs nothing (`core/llm_writers.py`).

Money is an integer number of micro-USD so that a day's figure is a sum of exact numbers. The table is a counter, so
it is not in the ops backup (`rcdata/backup.OPS_BACKUP_TABLES` keeps state, not counters): a restored box starts
the day at zero, which is the same thing `provider_calls_daily` does. Tokens are recorded
whatever the price is, so a day can be re-costed from its own rows once a price is known.

## What a call costs

`core/llm_prices.py` is the only place that says, and it has two sources, in this order:

1. **A published per-token price**, when the box is told one: `RC_LLM_PRICES` as JSON,
   `{"<model>": [usd per million input tokens, usd per million output tokens]}`. The table in the file is empty
   on purpose — the model names are our own LiteLLM gate's aliases (`deepseek-v4-flash`), not a provider's
   published model, so a price here would be invented.
2. **The measured cost of a call**: `MEASURED_USD_PER_CALL`, `0.0018` USD for `deepseek-v4-flash`, from the
   10 Nov 2026 pilot (400 names, 668 calls, about 1 USD). `module_relatedness/config.EST_USD_PER_CALL` reads this
   same number, so the board's per-run ceiling and the day's ledger cannot drift apart.

**So the ledger's USD is a measured estimate until a per-token price is set, and never the provider's invoice.**
`llm_prices.unit(model)` says which of the two a figure came from, and it travels with the number to the page and
into the refusal message. A paid model with no figure at all would spend money the cap could never see, so
`core/tests/test_llm_prices.py` fails one.

## The day cap (the gate)

`core/llm_spend.refusal()` is asked by `core/providers/deepseek.complete` before a request leaves the machine,
after its cache (a cached answer costs nothing) and after the off-peak gate
([`llm_offpeak.md`](llm_offpeak.md)). When it answers, the call is not made and `BudgetSpentError` is raised;
nothing is queued and nothing sleeps, because what is spent is spent until the New York day turns.

- The cap is the **box's** money for the whole New York day, over every paid job and every run. The per-run
  ceiling the Relatedness board already had cannot see that: six runs of 25 USD are 150 USD and no run was over
  its own cap.
- Default: **25.0 USD a New York day** — the same ceiling avo set for one Relatedness run
  (`RC_RELATEDNESS_USD_CAP`), so a full profile round (~14 USD, #712) fits in a day and a second round waits for
  the next. `core/tests/test_doc_constants.py` holds this line to `llm_spend.DEFAULT_DAY_CAP_USD`.
- `RC_LLM_USD_DAY_CAP`: a number is the cap in USD, `0` refuses every paid call, `off` (or `none`, or a negative
  number) is no cap. An unreadable value falls back to the default, not to no cap.
- **Fail closed:** when the ledger cannot be read the paid call is refused. A cap that cannot be checked is not a
  cap, and every job's default writer is EVREN, which costs nothing — so an unreachable store stops the money,
  not the work.

A job that is stopped by the gate stops the way it stops at the peak boundary: it keeps what it has written and
reports `stopped_reason` **`budget`** (`module_relatedness/engine.py`, `compare.py`, `naming.py`,
`rcdata/build/sec_reads/asker.py`). It is a boundary and not a failed call, so the run is not marked failed and
the banner stays empty.

## Switch and rollback

`RC_LLM_SPEND=0` stops the writes **and** the gate — one switch for both halves, because a gate reading a counter
nobody writes is worse than no gate. Nothing else changes: the paid client goes on working exactly as it did
before #166.

## What this is not

- Not a record of the free writer: EVREN's answers cost nothing and are not written here.
- Not the metered providers' quota gate. `provider_calls_daily` still only **records** what a Fetch spends on UW,
  EDGAR and Yahoo; nothing refuses a Fetch that would cross a day cap on the app side (#166 item 5, still open).
  The builder's own day caps (`rcdata/caps.at_cap`) are unchanged.
- Not a screen. The figures are in the Settings data layer (`module_settings/newdata._money`) for the v2 board to
  draw; the old dashboard's Spend card is untouched (new design is v2's, avo 21 Nov 2026).
