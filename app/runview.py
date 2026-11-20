"""The Runs tab (``/view/runs``, ``GET /api/runs``): the dashboard's own run log.

The log it used to read, ``job_runs``, lived in the old raw.duckdb and went with that file (#860), so the tab listed
nothing for two months. Since #1198 the new store's ``job_runs2`` holds what the old table never did -- the seconds
of **each step** of a run (``counts["steps"]``) and a **chain id** (``params["chain"]``) that ties a scheduled task's
run to the dataset runs it caused -- and this module is the reader of all three (#1205).

What the page gets:

- ``rows``: one per run, newest first, over the newest ``limit`` rows of the table. A builder run is named by its
  dataset, a scheduled task by its registry name, a dashboard job by its module; ``steps`` is the list of
  ``{name, seconds}`` in the order they ran.
- ``chains``: the same runs grouped by chain id, newest chain first, with the chain's span and busy time. One hourly
  pass and every dataset run it caused are one chain, which is what answers "where did this hour go".
- ``days``: runs, time and failures per day (the server's own day), newest first; the page's top strip is the first.
- ``audit``: the RevenueChaser half of the run-record audit of step 9 (home-server #519): **a chain whose root run
  left no row of its own**, and **a row with no chain id at all**. The cross-store comparison (homesrv's own
  ``ops.db job_runs`` against these rows) is deliberately not here: neither store reads the other.

Read-only throughout: no route in this module writes, and a store that holds no rows yet is an empty page, never an
error.
"""
from __future__ import annotations

import logging
from datetime import datetime

from markupsafe import Markup

from RevenueChaser.core import templating
from RevenueChaser.core.html_safe import script_json

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000
MAX_QUERY = 100
POLL_PATH = "/api/runs"
#: A run whose status is one of these is a problem: the "Problems only" switch keeps these and nothing else.
#: Three vocabularies meet in one table -- the builder writes ``failed``, a dashboard job ``error`` or
#: ``cancelled``, a task ``failed``, and ``lost`` is a run whose end write never came (#82).
BAD = frozenset({"failed", "error", "cancelled", "lost"})
#: How many offending chains the audit names, so one broken writer cannot fill the payload.
AUDIT_NAMES = 10
#: The order a builder run's steps really run in (``rcdata/build/base.py``: ``start`` before the first named one,
#: then the fetch half, then the build half). The stored dict cannot say it: ``ops._json`` writes the ``counts``
#: column with ``sort_keys=True``, so a row read back has its steps in alphabetical order, whatever order they
#: were stamped in (CI on this PR, unit 4/6, on the Redis backend). A step this list does not name is shown after
#: the ones it does, in the order the row holds, rather than being dropped or guessed at.
STEP_ORDER = ("start", "fetch", "parquet", "backfill", "build", "check", "swap", "after_swap")


def clamp_limit(value) -> int:
    """How many rows to read: a bad or missing value falls back, a silly one is capped."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(n, MAX_LIMIT))


def clean_query(value) -> str:
    """The name filter as a bounded string; anything unusable is no filter at all."""
    return value.strip()[:MAX_QUERY] if isinstance(value, str) else ""


def _seconds(start, end) -> float | None:
    """How long a run took, or None while it has no end (or an end before its start, which is a clock change)."""
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError):
        return None
    return round(end - start, 3) if end >= start else None


def _steps(counts) -> list[dict]:
    """``counts["steps"]`` as ``[{name, seconds}]`` in the order the steps run (``STEP_ORDER``), or [].

    #1198 stamps them in order, but the column is written with sorted keys, so the order has to be put back
    here. A name the builder does not use keeps the row's own order, after the known ones.
    """
    steps = (counts or {}).get("steps") if isinstance(counts, dict) else None
    if not isinstance(steps, dict):
        return []
    out = []
    for name, secs in steps.items():
        try:
            out.append({"name": str(name), "seconds": round(float(secs), 3)})
        except (TypeError, ValueError):
            continue                               # a step whose number is unreadable is left out, never guessed
    known = {name: i for i, name in enumerate(STEP_ORDER)}
    return sorted(out, key=lambda s: known.get(s["name"], len(known)))


def _day(epoch) -> str | None:
    """The server's own day of ``epoch`` (``YYYY-MM-DD``). The page shows times in the reader's browser, and the
    dashboard and the reader are on the same box, so this is the day the reader sees."""
    try:
        return datetime.fromtimestamp(float(epoch)).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def view_row(row: dict) -> dict:
    """One stored run as the page reads it. Every value comes from the row: nothing is guessed from the lane, and a
    run that recorded no trigger stays a dash (#83)."""
    counts = row.get("counts") if isinstance(row.get("counts"), dict) else {}
    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    dataset, job = row.get("dataset"), row.get("job")
    # Who wrote the row, which is what the page colours and groups by: the builder names a dataset, the dashboard
    # writes the trigger ``dashboard`` (``app/jobs.py``), and a scheduled task is what is left (``schedule``).
    kind = "build" if dataset else ("dashboard" if row.get("trigger") == "dashboard" else "task")
    return {"run_id": row.get("run_id"), "module": dataset or job, "kind": kind,
            "dataset": dataset, "job": job, "trigger": row.get("trigger"), "status": row.get("status"),
            "started_at": row.get("started_at"), "finished_at": row.get("finished_at"),
            "queued_at": None, "duration_s": _seconds(row.get("started_at"), row.get("finished_at")),
            "error": row.get("error"), "message": None, "host": row.get("host"), "pid": row.get("pid"),
            "chain": params.get("chain"), "steps": _steps(counts),
            # ``steps`` has its own column on the page, so the Counts cell holds what the run counted besides it;
            # ``chain`` likewise is a column, not a params blob the reader has to read.
            "counts": {k: v for k, v in counts.items() if k != "steps"},
            "params": {k: v for k, v in params.items() if k != "chain"}}


def matches(row: dict, problems: bool, query: str) -> bool:
    """Whether a view row passes the page's two filters: the name contains ``query`` (case-insensitively, over the
    job name and the dataset), and with ``problems`` the status is one of ``BAD``."""
    if problems and (row.get("status") or "") not in BAD:
        return False
    if query:
        hay = " ".join(str(row.get(k) or "") for k in ("module", "dataset", "job", "trigger")).lower()
        if query.lower() not in hay:
            return False
    return True


def chains(rows: list[dict]) -> list[dict]:
    """The runs grouped by chain id, newest chain first; inside a chain the runs stay newest first.

    ``seconds`` is the chain's **span** (its first start to its last end), which is the hour a pass really took, and
    ``busy_s`` the sum of its runs, which is more than the span only when two of them overlapped. A chain of one run
    nobody started is still a chain, because step 1 makes such a run the root of its own chain.
    """
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r.get("chain") or r.get("run_id") or "", []).append(r)
    out = []
    for chain, members in groups.items():
        starts = [m["started_at"] for m in members if m.get("started_at") is not None]
        ends = [m["finished_at"] for m in members if m.get("finished_at") is not None]
        running = [m for m in members if (m.get("status") or "") == "running"]
        bad = [m for m in members if (m.get("status") or "") in BAD]
        root = next((m for m in members if m.get("run_id") == chain), None)
        out.append({"chain": chain, "name": (root or members[-1]).get("module"),
                    "root_run": root.get("run_id") if root else None,
                    "started_at": min(starts) if starts else None,
                    "finished_at": None if running or not ends else max(ends),
                    "seconds": None if running or not (starts and ends) else _seconds(min(starts), max(ends)),
                    "busy_s": round(sum(m["duration_s"] for m in members if m.get("duration_s")), 3),
                    "runs": len(members), "bad": len(bad), "running": len(running),
                    "status": "running" if running else ("failed" if bad else "done"),
                    "run_ids": [m.get("run_id") for m in members]})
    out.sort(key=lambda c: (c["started_at"] is not None, c["started_at"] or 0.0, c["chain"]), reverse=True)
    return out


def days(rows: list[dict]) -> list[dict]:
    """Runs, time and failures per day over the rows read, newest day first. ``seconds`` is the sum of the runs that
    finished that day's start: a run still going adds nothing, so the figure never grows by guessing."""
    out: dict[str, dict] = {}
    for r in rows:
        day = _day(r.get("started_at"))
        if day is None:
            continue
        d = out.setdefault(day, {"day": day, "runs": 0, "seconds": 0.0, "failed": 0, "running": 0})
        d["runs"] += 1
        d["seconds"] = round(d["seconds"] + (r.get("duration_s") or 0.0), 3)
        d["failed"] += (r.get("status") or "") in BAD
        d["running"] += (r.get("status") or "") == "running"
    return [out[k] for k in sorted(out, reverse=True)]


def audit(rows: list[dict], exists=None) -> dict:
    """The RevenueChaser half of the run-record audit (home-server #519's "not done here").

    Two questions the rows can answer about themselves:

    - **A chain with no root record.** Every row carries the id of the run that started its process (#1198); if no
      ``job_runs2`` row has that id, the outer run left no record of its own. ``exists`` is asked of the **store**
      (``ops.runs_exist``), not of the page, so a root that started before the page's window is not a gap.
    - **A row with no chain id.** Written before #1198, or by a writer that bypassed ``ops.chained_params``.

    It never invents a gap: when the store cannot be asked, ``checked`` is false and both counts are 0.
    """
    no_chain = [r.get("run_id") for r in rows if not r.get("chain")]
    seen = {r.get("run_id") for r in rows}
    wanted = {r["chain"] for r in rows if r.get("chain") and r["chain"] not in seen}
    if wanted and exists is None:
        try:
            from RevenueChaser.rcdata import ops
            exists = ops.runs_exist(sorted(wanted))
        except Exception:  # noqa: BLE001 — a page, not a monitor: an unreadable store is "not checked"
            logger.debug("runs: the chain roots could not be read", exc_info=True)
            return {"checked": False, "no_chain": 0, "no_chain_runs": [], "missing_root": 0, "missing_chains": [],
                    "rows": len(rows)}
    missing = sorted(c for c in wanted if c not in (exists or set()))
    return {"checked": True, "no_chain": len(no_chain), "no_chain_runs": no_chain[:AUDIT_NAMES],
            "missing_root": len(missing), "missing_chains": missing[:AUDIT_NAMES], "rows": len(rows)}


def read(limit=DEFAULT_LIMIT, problems: bool = False, query=None) -> dict:
    """What ``/api/runs`` returns: the newest ``limit`` runs, the chains they make, the per-day totals and the audit.

    The two filters are applied to the window that was read, and the payload says how big that window was
    (``read``), so "0 problem runs" can never be read as "nothing ever failed". A store with no rows, or one that
    cannot be read at all, is an empty page with ``ok`` false: the Runs tab is a view, never a monitor.
    """
    limit, problems, query = clamp_limit(limit), bool(problems), clean_query(query)
    try:
        from RevenueChaser.rcdata import ops
        stored = ops.recent_runs(limit)
    except Exception as exc:  # noqa: BLE001 — a missing or busy ops store is an empty page, not a 500
        logger.debug("runs: the run log could not be read", exc_info=True)
        return {"rows": [], "chains": [], "days": [], "audit": audit([], exists=set()), "total": 0, "shown": 0,
                "read": 0, "limit": limit, "problems": problems, "query": query, "ok": False,
                "error": str(exc)[:200]}
    window = [view_row(r) for r in stored]
    rows = [r for r in window if matches(r, problems, query)]
    return {"rows": rows, "chains": chains(rows), "days": days(window), "audit": audit(window),
            "total": len(window), "shown": len(rows), "read": len(window), "limit": limit,
            "problems": problems, "query": query, "ok": True}


def page_payload() -> dict:
    """What the Runs page is rendered from: the first page of rows, so the first view needs no poll."""
    return {"initial": read()}


def render_page(payload: dict) -> str:
    # script_json output is the one trusted fragment: Markup keeps autoescape from turning its quotes into
    # entities, which an inline <script> would not decode. Every value in it reaches the page as textContent.
    # The page-size control offers what ``clamp_limit`` accepts: the default page first, then the cap.
    return templating.render("runs.html.j2", limits=(DEFAULT_LIMIT, MAX_LIMIT),
                             initial_json=Markup(script_json(payload.get("initial") or {})))
