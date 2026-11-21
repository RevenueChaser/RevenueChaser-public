# The v2 door

The read side of the v2 interface (run plan step 6, #1264, epic #1238). One FastAPI process serves `/api/v1` over
the v2 envelopes the dashboard's board jobs write, and the static `v2/web/dist/` files the `web` CI job builds. The
stack it is built against is [`v2/README.md`](../../v2/README.md); the homesrv side of it — the port, the memory
slice, the Grafana frame origin and the `tailscale serve` line — is home-server `docs/rc-v2-door.md`.

**The dashboard on port 8000 is not touched.** It keeps its own payload route, its own bytes and the DuckDB
writer; the door only reads files beside them, and nothing in the door can write anything at all.

## The routes

`/api/v1` and nothing else. Every method but `GET`, `HEAD` and `OPTIONS` is refused `405` by the app itself, in
front of every route it has or will have: the proxy with its Read and Write classes is step 7, and until it exists
there is no path through the door to a write.

| Route | Answer |
|---|---|
| `GET /api/v1/health` | one named probe per dependency, each with a **2 s** budget; `200` when no required probe is red, `503` otherwise |
| `GET /api/v1/version` | `door_version`, the `build_sha` the image was built from, `envelope_schema_version`, the board keys |
| `GET /api/v1/boards` | one row per board: `present`, `run_id`, `data_asof`, `built_at`, `renderer`, `private`, sizes — never a board's rows |
| `GET /api/v1/boards/{board}` | that board's envelope, gzip as stored; `404` for an unknown board and `404` for a known board whose job has not run |

A board is named by the key `app/dashboard.TABS` and `core/v2_envelope.BOARDS` already use (`module_relatedness`),
so the door, the schemas and the Android app share one name for each board.

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
write side is the PR that makes it required.

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

The CSP names no CDN, ever: v2 runs on a tailnet with no guaranteed outbound internet (`v2/README.md`
decision 2). `frame-ancestors 'none'` is the other direction — nothing frames the door — so it is Grafana's own
header, not this one, that lets the v2 Settings screen show the RC boards.
