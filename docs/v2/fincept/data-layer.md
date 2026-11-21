# Fincept's data layer beside ours, and what v2 can take from it

Fincept facts are from `docs/ARCHITECTURE.md`, `fincept-qt/docs/DATAHUB_TOPICS.md`, `src/datahub/TopicPolicy.h`,
`src/datahub/Producer.h` and `src/datahub/DataHub.cpp` at commit `914134d`. Ours are from `main` at `7bfbec1`
(`rcdata/caps.py`, `rcdata/build/base.py`, `core/datasets.py`) and from `docs/data_architecture.md`. Reading marks as
in the [README](README.md).

## Two different jobs

`[INFERRED]` Fincept is a **live terminal for one desk**: it fetches what the open screen needs, when the screen
opens, keeps it for seconds or minutes, and keeps no history of its own. RevenueChaser is a **research store**: a
builder fetches on a schedule whether or not anyone looks, keeps every bar since 1984, and boards compute over the
whole universe. Most of Fincept's data layer solves a problem we do not have (many live panels sharing one fetch),
and it has no answer to the one we solved (a durable, audited, rebuildable history). So the lesson is narrow: take
its **read side**, keep our **write side**.

## Side by side

| Concern | Fincept | RevenueChaser | Which is better here |
|---|---|---|---|
| When data is fetched | On demand: a panel subscribes to a topic and the hub fetches if the cached value is stale `[READ]` `ARCHITECTURE.md` 7.1 | On a schedule: the builder runs hourly and by need, boards read finished files `[READ]` `docs/data_architecture.md` | Ours for history and screens over the universe. Theirs for a live quote. |
| Where it is kept | A SQLite TTL key/value cache, separate file from the main database `[READ]` | Parquet raw, then DuckDB files built and swapped in whole; one file per board `[READ]` | Ours. Theirs is a cache, not a record. |
| Freshness rule | One policy per topic: `ttl_ms`, `min_interval_ms`, `refresh_timeout_ms`, `push_only`, `coalesce_within_ms` `[READ]` `TopicPolicy.h` | Per dataset: "due" rules in the builder, and freshness pairs per dataset `[READ]` `rcdata/build/due.py`, `core/datasets.py:152` | Theirs is easier to read: **one table lists every topic's TTL** (`DATAHUB_TOPICS.md`). Ours is spread over the builder. |
| One fetch, many readers | Yes, by design: "one-fetch/many-subscribers" `[READ]` | Not needed: readers open a finished file | Not comparable. Becomes relevant for v2's alert lane. |
| Provider failure | The hub keeps serving the **last known good** value and retries on a backoff ladder `[READ]` `ARCHITECTURE.md` 6.3, `DataHub.cpp:23-47` | A failed build does not swap, so the last good file stays in place; a shrink guard refuses a build that lost rows `[READ]` `docs/data_architecture.md` | Same idea, both sound. Ours is stronger (atomic, with a previous file kept). |
| Fallback source | Per script: Cboe first, Yahoo second, and the reply names which one answered and why (`source`, `fallback_reason`) `[READ]` `deriv_market.py:1-25` | Primary and secondary sources exist for prices (`docs/compustat_primary_switch.md`) `[READ]` file name only | **Theirs shows the user which source answered.** Ours `[NOT CHECKED]` on the board. |
| Rate limits | A producer may state `max_requests_per_sec`; `min_interval_ms` per topic `[READ]` `Producer.h:30` | Published limits per provider with their source URL, a day cap counter and a pacer `[READ]` `rcdata/caps.py` | Ours. It counts every request and cites where each number comes from. |
| Slow or hung fetch | `refresh_timeout_ms` clears the in-flight flag so a dead producer cannot pin a topic `[READ]` | Job locks and an idle check for the deploy gate `[READ]` `app/jobs.py:524` | Different problems; no gap seen. |
| Live streams | WebSocket topics are push-only and coalesced (50-100 ms, latest wins; trades batched, never dropped) `[READ]` | None | Theirs, and it is the model for v2's alert lane. |
| What the user is told | Every table footer says source, time and delay: "as of 02:33 · delayed up to 20 min · Yahoo Finance screener" `[READ]` `QuoteTableWidget.cpp:164-167`, `images/Dashboard.png` | Data health board and Grafana show freshness per dataset `[READ]` `docs/data_health.md` file name only; per panel `[NOT CHECKED]` | **Theirs.** The statement is on the panel the number is on. |
| Connector catalogue | One JSON file describes all 204 connectors: commands, parameters, key variables, a sample, TTL `[READ]` | Sources are Python modules; limits in `caps.py`; needs in a catalogue `[READ]` | Theirs is a better index. Ours is better enforced. |
| Keys | Encrypted local store; 22 named keys injected per call, every other secret-shaped variable stripped from the child process `[READ]` `ARCHITECTURE.md` 6.4 | `core/credentials.py`, keys never in the repository `[READ]` `CLAUDE.md` | Equal. The "strip everything not on the list" rule is worth copying for any child process. |

## What to take for RevenueChaser v2

1. **Say on every panel where the number came from and how old it is.** Source, as-of time, and delay, in the
   panel's footer. The board payload v2 plans already carries `as_of` and provenance; this makes them visible.
2. **One table of every dataset's freshness rule.** A generated document like their `DATAHUB_TOPICS.md`: dataset,
   producer, how often, how stale it may be. Ours exists in code; it should be readable in one place and checked
   against the code, as `core/tests/test_doc_constants.py` already does for other values.
3. **A machine-readable source catalogue.** One file listing every source we call: what it gives, key or no key, the
   published limit and its URL, which datasets and boards depend on it. `rcdata/caps.py` and the needs catalogue are
   two halves of it today. It also answers "what breaks if we drop UW" by lookup.
4. **Name the fallback when it is used.** When a secondary source answered, the payload says so and why, and the
   panel shows it.
5. **For the alert lane only: topics with a policy.** Push-only, coalesced, last value kept, one fetch for many
   listeners. This is the part of the DataHub that fits a live lane; the boards do not need it.
6. **Free sources first for option chains.** Their order (Cboe delayed first, Yahoo second, real time only with a
   paid key) is the order the owner's plan to leave UW already points at.

## What not to take

- **No store of record.** A TTL cache cannot answer "what did we know on that day"; our build-then-swap files can.
- **Fetching inside the screen's request.** It is the cause of the stalls the GUI review found on our side.
- **Yahoo as the single pillar.** Their equity core is one unofficial source with no published limit; ours treats it
  as one source among several (`rcdata/caps.py` marks its window as owner-set, "Yahoo publishes none").
- **Their server.** The symbol master, calendar and metered datasets sit behind a Fincept account.
