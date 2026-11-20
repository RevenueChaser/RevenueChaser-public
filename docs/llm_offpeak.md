# Plan — DeepSeek off-peak gate

DeepSeek bills peak hours at **2×** the off-peak rate. This plan makes the
optional LLM steps of the Relatedness board (profile extraction and theme naming;
`module_relatedness` is the only caller of `core/providers/deepseek.py`) run
**off-peak only**, stop automatically at the peak boundary, and resume on the
next off-peak run. It is deliberately small: a gate, not a scheduler.

Status: **implemented.** `core/offpeak.py`, `core/providers/deepseek.py`
(durable `llm_cache`), `module_relatedness/store.py` (durable profiles) and the
off-peak CLI are done and tested. Remaining: the live run itself (manual,
off-peak).

## Implemented (2026-09-20)

- `deepseek.complete`: order **cache → gate → HTTP**; at most **2 attempts** (one
  retry, only after an HTTP 429 or an error raised before the request left the
  machine; a 5xx or a failure after the send is final, it may already be billed);
  cache is the durable `llm_cache` table (no `.cache/llm_cache/*.json` files). Rows
  carry `cache_key`, `ticker`, `cik`, `model`, `thinking`, `effort`,
  `prompt_version`, `input_hash`, `response`, `fetched_at`, `status`.
- `module_relatedness/store.py`: durable profiles (`relatedness_profiles` +
  `relatedness_attributes`), structured `cache_key`, mode stamp in `run_registry`.
  Absence of a profile row = **pending** (resume is automatic and cache-first).
- `module_relatedness/engine.run`: catches `PeakHoursError` at the boundary, renders
  from the durable profiles already written, and returns `pending` + `next_off_peak`;
  records a `relatedness_run` marker in `run_registry`.
- **$ hard-stop**: `config.USD_CAP` (env `RC_RELATEDNESS_USD_CAP`, default 25.0) caps
  LLM calls per run at `USD_CAP / EST_USD_PER_CALL`; the rest stay pending. `--cap 0`
  means no LLM call at all. The budget counts calls, the thinking retry included
  (`profiles.CallBudget`, #118 PR C).
- **Stop events**: the first worker that hits the peak boundary (`peak`), a rejected
  key (`auth`) or repeated transient failures (`transient`) records the reason; the
  run stops submitting groups, renders from the profiles already written and returns
  `stopped_reason` (plus `error`, and `next_off_peak` for a peak stop). An auth or
  transient stop is recorded `partial` in the result history, like a peak stop.
- CLI: `python -m RevenueChaser.module_relatedness --run [--limit N] [--cap USD]`
  (and `--status`). A stopped run or one with work left prints one JSON object
  (`done`, `pending`, `next_off_peak`, `stopped_reason`, `error`). Exit **0** for a
  finished run, a peak stop, the cost cap and pending names (the normal night-to-night
  state, so the scheduled task stays green); exit **1** for an `auth` or `transient`
  stop and for the lock skip (another run holds the lock, nothing ran).

## Decisions (locked)

| Topic | Decision |
|---|---|
| Scheduling | **(1a)** gate + manual; Task Scheduler is a **visible, installable row** on the Settings Automations panel (`RC-Relatedness-OffPeak`), **not installed by default**; no self-deferring job |
| Peak | LLM **must not run** |
| Cache | DuckDB `llm_cache` (model + prompt hash → response) |
| Peak behaviour | A **cache hit is served at peak** (it costs nothing); only a cache **miss** stops. The gate sits after the cache in `deepseek.complete` |
| Boundary | leaving off-peak stops the run; resume on the next off-peak run |

## Windows

Defined in **UTC** so a local daylight-saving change cannot shift them.

| | Peak (UTC) | Off-peak |
|---|---|---|
| Mon–Fri | 01:00–04:00 and 06:00–10:00 | all other hours |
| Sat–Sun | — | 24 hours |

Reference (informational; DST shifts these):

| Local | Peak |
|---|---|
| UTC+3 (Türkiye, no DST) | 04:00–07:00 and 09:00–13:00 |
| CET / CEST | ≈ 02:00–05:00 / 07:00–11:00 (winter) |
| UTC+8 (Beijing) | 09:00–12:00 and 14:00–18:00 |

## Behaviour

1. **Before starting a batch:** `is_off_peak()`. If peak → do not start; 0 HTTP;
   `JobMessage("Peak hours — LLM not run. Next off-peak: HH:MM UTC")`.
2. **Before every call:** re-check `is_off_peak()`.
   - off-peak → call, write `llm_cache`, mark the item `done`.
   - peak reached → **stop**: no further calls and no HTTP; an item already in
     `llm_cache` is still served, the others stay `pending`.
3. Job ends `done` (not an error) with `N/M done, rest pending, next off-peak …`.
4. The board renders whatever completed; no partial/inconsistent writes.
5. Next off-peak run resumes: finished items come from `llm_cache` and the durable
   profiles, only the `pending` ones call the API.
6. `RC_DEEPSEEK_OFF_PEAK_ONLY=1` default **on**. An override exists but is
   discouraged — the rule is "no LLM at peak".
7. The gate never sleeps; the single job worker is never blocked.

## Components

- **`core/offpeak.py`** (done) — pure, I/O-free:
  `PEAK_WINDOWS_UTC = ((1, 4), (6, 10))`, `is_off_peak`, `next_off_peak`,
  `local_peak_windows`, `describe`. Tests in `core/tests/test_offpeak.py`.
- **`core/providers/deepseek.py`** — key via `core/credentials.py`
  (`LITELLM_RC_KEY`, through the LiteLLM gate on 127.0.0.1:9720 since 15 Nov 2026). Order: **cache → gate → HTTP**. A cache miss at peak raises
  `PeakHoursError` (no HTTP). The base URL is `RC_DEEPSEEK_BASE`, read at call time.
  A reply that is not JSON raises `DeepSeekError` and is not cached; the caller's
  `validate=` hook can also keep an answer out of the cache. The key is read from
  the environment only; no key file in the tree is read, and none belongs in the
  repository.
- **`llm_cache`** (`raw.duckdb`) — `cache_key` (a hash of model, thinking mode,
  effort, system and user text), `ticker`, `cik`, `model`, `thinking`, `effort`,
  `prompt_version`, `input_hash`, `response` (`{content, usage}`), `fetched_at`,
  `status`. Turns re-runs into 0-cost hits (and is the bigger saving than off-peak
  itself).
- **Pending marker** — there is none to add: an item with no profile row in
  `relatedness_profiles` is pending, so a stopped batch resumes by itself.
- **Redo** — a stored profile is profiled again when it was made under another
  mode or from another input: the hash of today's prompt (filing text and the
  `equity_universe` company name) differs from the `input_hash` in its cache key
  (#388 D5). Both wait for the run's `$` cap like any pending name. "Another
  mode" is another `prompt_version` for every writer; a DeepSeek profile must
  also match the mode's model, thinking and effort (v3, #400: no thinking and no effort for every writer). The
  input hash covers every chunk's prompt, context included (SIC, sector, industry, segment note, candidates). Another
  writer's profile at the current `prompt_version` is current (`store.is_stale`),
  so the nightly run does not redo it.

## Profile writers (#360)

Since #360 the dashboard Fetch and the scheduled `RC-Relatedness-OffPeak` (`--run --cap 10`) write with the
board's writer (Settings: EVREN by default, no fee; DeepSeek capped at 10 USD and off-peak gated). Pick the model
on the board, not with `RC_EVREN_MODEL` / `RC_DEEPSEEK_MODEL`: the board's model goes to every caller with each
call. The Grok and Claude subscription writers were one-off and are removed (avo, 15 Nov 2026); their stored
profiles stay current at the current `prompt_version` (`store.is_stale`).

## No Fetch and no build calls the paid API (avo, 20 Nov 2026)

avo: "Fetch ve build sirasinda deepseek api kullanilan islem kalmasin hepsi evren deepseek olmali". Every LLM job's
writer comes from one registry (`core/llm_jobs.py`, #404) and its default is EVREN, which has no fee; the paid
DeepSeek API is reachable only when a caller names it — `--provider deepseek`, a `RC_SEC_READS_PROVIDER=deepseek`
process, or the Settings page. Since 20 Nov 2026 no function's writer argument *defaults* to the paid writer
either: `module_relatedness` (`engine.run`, `engine.score`, `engine.build_profiles`, `profiles.llm`,
`profiles.profile_for`, `locator.locate`, `store.save_profile`) carried `provider="deepseek"` as its default, so a
caller that forgot the argument spent money. The writer a call names none for is now read at call time, in one
place (`module_relatedness/config.py` `default_writer()` -> `core.llm_writers.DEFAULT`), and
`core/tests/test_llm_jobs_404.py` fails any writer argument in the tree that defaults to a paid provider.

## Tests

- Peak start → 0 HTTP, immediate stop.
- Peak reached mid-batch → stops there, remaining `pending`, resume continues.
- Peak + cache hit → the cached answer is served, 0 HTTP.
- Off-peak + miss → 1 HTTP, cached; off-peak + hit → 0 HTTP.
- `no_fetch` / Refresh → never touches the LLM, 0 HTTP.
- `RC_DEEPSEEK_OFF_PEAK_ONLY` unset/1 → gate active; 0 → runs (documented escape).

## Not in scope

Installing a Task Scheduler task automatically, an in-app cron/timer, retries beyond the single
429 / pre-send retry above, and streaming.
