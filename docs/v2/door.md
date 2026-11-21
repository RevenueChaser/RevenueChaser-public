# The v2 door

The v2 interface's one process (run plan steps 6 and 7, #1264 and #1317, epic #1238). It serves `/api/v1` over
the v2 envelopes the dashboard's board jobs write, and the static `v2/web/dist/` files the `web` CI job builds. The
stack it is built against is [`v2/README.md`](../../v2/README.md); the homesrv side of it — the port, the memory
slice, the Grafana frame origin and the `tailscale serve` line — is home-server `docs/rc-v2-door.md`.

**The dashboard on port 8000 is not touched.** It keeps its own payload route, its own bytes, the DuckDB writer
and the job queue; v2 adds no second writer. The door reads envelope files beside them, and the one way a v2
screen changes anything is by the door **pressing one of the dashboard's own routes** through the proxy below.

## The routes

`/api/v1` and nothing else. Outside `/api/v1/proxy` every method but `GET`, `HEAD` and `OPTIONS` is refused `405`
by the app itself, in front of every route it has: step 7 opened one prefix for writes, not the door.

| Route | Answer |
|---|---|
| `GET /api/v1/health` | one named probe per dependency, each with a **2 s** budget; `200` when no required probe is red, `503` otherwise |
| `GET /api/v1/version` | `door_version`, the `build_sha` the image was built from, `envelope_schema_version`, the board keys |
| `GET /api/v1/boards` | one row per board: `present`, `run_id`, `data_asof`, `built_at`, `renderer`, `private`, sizes — never a board's rows |
| `GET /api/v1/boards/{board}` | that board's envelope, gzip as stored; `404` for an unknown board and `404` for a known board whose job has not run |

A board is named by the key `app/dashboard.TABS` and `core/v2_envelope.BOARDS` already use (`module_relatedness`),
so the door, the schemas and the Android app share one name for each board.

## The proxy, and its three classes

Step 7 (#1317). A v2 screen presses a dashboard route through `/api/v1/proxy` followed by that route's own path:
`POST /api/v1/proxy/api/build/request/spine/security` is the Fetch press. The rules are
`v2/door/proxy.py`'s `decide()` — one function taking a method, a path and the request's headers — and nothing in
`app.py`, because route authorisation is the kind of logic this repository asks for a mutation check on and a
mutation check needs a named function to mutate.

| Class | What the door does |
|---|---|
| **Read** | forwarded with no login. A Read route may not change anything, which the tests hold to by reading the patterns themselves |
| **Write** | forwarded only with a non-empty `Tailscale-User-Login` **and** the caller's own `X-RC-Panel`, and only when the browser does not say the request came from another page. Logged, allowed or refused |
| **Guarded** | refused `403` outright, by either method, whatever headers it carries, and never forwarded |

**A path the table does not name is `404` and is never forwarded.** The table is the allowlist.

**The caller's headers cross unchanged; the door mints none.** This is the design plan's Grok round-1 blocker
(`revenuechaser_v2_plan.md` §9 item 1): a door that minted `X-RC-Panel` itself would defeat the dashboard's own
cross-site check, which reads only the request it received. So exactly three request headers cross — `X-RC-Panel`,
`Tailscale-User-Login` and `Content-Type` — with the caller's values, and a cookie, an `Authorization` or the
caller's `Host` never does. The door asks the dashboard's three questions itself as well (`Sec-Fetch-Site`,
`Origin`, the panel header), because the dashboard will see the door's request and not the caller's.

**The forwarded path is rebuilt, never passed through.** A path is matched segment by segment against a pattern
and the upstream path is then assembled from that pattern and the segments it captured, each of which must be one
plain segment: no slash, no percent sign, no `..`. So a traversal cannot reach a route the table never named.

**The upstream must be loopback.** `RC_DOOR_UPSTREAM` has to be `http` on `127.0.0.1`, `localhost` or `::1`, with
no userinfo and no path, or the press answers `500` and says the door is misconfigured. The dashboard is on the
same box and on the host network; a door that would forward to any host an environment variable named is a relay
for whatever can reach the tailnet. A press that the dashboard does not answer within `15 s` is `504`; the
dashboard's own `4xx` and `5xx` are its answers and pass through unchanged, so a press refused *there* does not
read as a press refused here. A body over 64 KiB is `413`.

### The route table

Class **Read**, what Settings shows:

`/api/settings/status` · `/api/settings/requests` · `/api/settings/tickers` · `/api/settings/lookup/{ticker}` ·
`/api/settings/sample/{table}` · `/api/build/queue` · `/api/build/datasets` · `/api/build/state` ·
`/api/automations` · `/api/jobs` · `/api/job/{job_id}` · `/api/idle` · `/api/logs` · `/api/runs` ·
`/api/data_asof/{mod}` · `/api/watchlists`

Class **Write**, the presses Settings makes:

`/api/build/request/{dataset}` · `/api/build/request/{dataset}/{part}` · `/api/build/schedule/{dataset}/{action}` ·
`/api/build/schedule/{dataset}/{part}/{action}` · `/api/build/automation-ds/{dataset}` ·
`/api/build/automation-ds/{dataset}/{part}` · `/api/build/switch/{name}` · `/api/job/{job_id}/cancel` ·
`/api/automations/{name}/{action}`

A dataset of one or two segments is named twice rather than once with a wildcard, because a wildcard would
forward a depth the table never read.

Class **Guarded**, avo's own presses:

`/api/build/timer` · `/run/module_value_chain` · `/api/watchlist/{kind}/remove/{ticker}` ·
`/api/watchlists/{list_id}/delete` · `/api/watchlists/{list_id}/symbol/remove` ·
`/api/watchlists/{list_id}/section/delete`

The builder timer, the Value Chain sync and a watch-list delete need avo's typed words, and the run plan says a
thread never makes them on its own. They are **in** the table rather than left out of it on purpose: a route that
is merely absent is a `404` today and one table edit away from being open, while a route classified Guarded has to
be reclassified by hand.

The table covers step 9's board, Settings, and nothing beyond it. Step 10's board presses and the pilots'
watch-list edits are added by the PRs that need them, each classified here first.

## The write log

One JSON line per **write** and per **guarded** press, allowed or refused; a read is not a write and is not
logged, because a log that held every board poll would bury the lines that matter. Nine fields and no tenth:
`ts`, `login`, `method`, `path`, `klass`, `outcome`, `reason`, `status`, `duration_ms`.

`outcome` and `status` are two fields on purpose: a press that reached the dashboard and was refused *there* reads
as `allowed` with a `403`.

What is deliberately absent: **no body, no query string, no header but the login, and no traceback.** The
dashboard logs its own run record, and a second copy of whatever a caller typed is how a value ends up somewhere
it was never meant to be; an upstream that did not answer is a status and a reason, never an exception's text,
which can carry a URL that holds a password. The login is a caller's header value, so it is cut to 200 characters
and its control characters are dropped — one press is one line, whatever the value holds.

**Where it goes.** Through the `RevenueChaser.v2.door.write` logger, which in the container is stdout and so
journald. `RC_DOOR_WRITE_LOG` adds a file beside it when there is somewhere writable to put one; unset — the
default, and what the container runs — nothing is written to disk. That is the point: the image is
`read_only: true` with one `:ro` mount, and the write side must never make the artifacts root need to change.

### The hash pair

`data` inside the envelope is the payload file, byte for byte: `write_board` serialises both with the same options
(`core/v2_envelope.JSON_ARGS`). So for every board

```
sha256(core.v2_envelope.data_bytes(envelope)) == sha256(gunzip(<stem>.payload.json.gz))
```

and that equality is the deploy's proof of done — six equal pairs, one per board that writes a payload. It is
checked in CI too, over a real socket, by `module_testing/e2e/test_v2_door.py`.

## The probes, and why they are timed

The failure a health route has to survive is a dependency that is reachable but wedged. Each probe therefore runs
in its own thread with `v2/door/config.py`'s `PROBE_BUDGET_S` seconds; one that overruns is reported as a timeout
and the others still answer, so a monitor learns *which* dependency is at fault.

| Probe | Red when | Required |
|---|---|---|
| `artifacts` | `RC_CACHE_DIR` is not a readable directory | yes — `503` |

The second word of that row is the one that bit on the first deploy: the root can be *there* and still not be *readable*. The image runs as its own `door` user, whose uid exists only inside the image, and the artifacts root belongs to the user the dashboard's jobs run as with mode `2770`. The container joins that gid as a supplementary group (`group_add` in `docker-compose.yml`, `RC_ARTIFACTS_GID`); without it the probe is red, `/api/v1/health` answers 503 and `/api/v1/boards` fails, while `/api/v1/version` still answers, because that route reads no file.
| `redis` | `RC_REDIS_URL` is set and `PING` does not come back | no |

`redis` with no URL set is `null`, not red: the read side reads files and is complete without a queue. Step 7's
write side did **not** make it required either, and that is the honest answer rather than an oversight: the proxy
forwards to the dashboard, which holds the queue, so the door itself keeps no state. The probe turns required when
the door holds state of its own — the saved layouts of step 10.

## How it runs

A Docker container built from the merged SHA (`v2/door/Dockerfile`, compose service `door`):

- **The web files are built in the image**, in a `node:22-alpine` stage, never by a Node toolchain on homesrv
  (`v2/README.md` decision 6).
- **Only `v2/door/requirements.txt` is installed**, not the repository's: pandas, duckdb, scipy, scikit-learn,
  fastembed, plotly, matplotlib and kaleido have no part in serving JSON files.
- **The host network**, with uvicorn bound to `127.0.0.1:8100`. On the host network `0.0.0.0` would open the port
  to the home network, which homeops' ports check would rightly call unknown.
- **`cgroup_parent: life-rc-v2.slice`**, which is what makes that slice's memory limit bind: a systemd unit that
  calls `docker compose up` does not cap the container.
- **`read_only: true`**, one read-only mount (the artifacts folder) and a tmpfs `/tmp`. `RC_STORE_DIR` and
  `RC_EDGAR_DOCS_DIR` point into the tmpfs because `core/config.py` creates all four roots at import and the door
  uses neither of those two: the durable store is not reachable from the container at all.
- **Not root** (`USER door`).

### Environment

| Variable | What |
|---|---|
| `RC_CACHE_DIR` | the artifacts root the dashboard's jobs write, read through `core.config.OUTPUT_DIR` — the one place this variable is read |
| `RC_BUILD_SHA` | the commit the image was built from, answered by `/api/v1/version` |
| `RC_DOOR_HOSTS` | the Host allowlist; default `127.0.0.1,localhost,homesrv.rhinoceros-dominant.ts.net` |
| `RC_DOOR_GRAFANA_ORIGIN` | the one origin the door's CSP lets its pages frame; empty means frame nothing |
| `RC_REDIS_URL` | the ops state, for the health probe now and the write side later |
| `RC_ARTIFACTS_GID` | the gid that owns `RC_CACHE_DIR` on the host, joined as a supplementary group; default `1001` (homesrv's `life`) |
| `RC_DOOR_UPSTREAM` | the dashboard the proxy presses; default `http://127.0.0.1:8000`, and loopback only |
| `RC_DOOR_WRITE_LOG` | a file to append the write log to; unset (the default) means the process log alone |

The CSP names no CDN, ever: v2 runs on a tailnet with no guaranteed outbound internet (`v2/README.md`
decision 2). `frame-ancestors 'none'` is the other direction — nothing frames the door — so it is Grafana's own
header, not this one, that lets the v2 Settings screen show the RC boards.
