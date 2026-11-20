"""The nightly Fetch of one board (avo 17 Nov 2026, choice a): ``python -m RevenueChaser.scripts.board_fetch <board>``.

One RC-Fetch-<Board> registry row per board, each its own server timer, installed disabled: a board's timer is switched
on only once its review and rule decisions are done. The task runs after the nightly prices build and asks nothing until
the dashboard reports nothing writing a store (``/api/idle``: no dashboard job, no job lock such as the hourly
builder's ``rcdata_build``, no other store process), waiting for that up to the task's deadline, and until that build
holds SPY's complete bar of the latest complete New York session (``ledger.d01_has_session``, the freeze's own
anchor), so the Fetch scores on the same session the forecast ledger freezes; otherwise it exits ``EXIT_NOT_READY``.
The Fetch runs in the dashboard, the one writer: the task posts ``/run/<route>`` with the ``X-RC-Panel`` header and
polls ``/api/job/<id>``, as the Value Chain and SPX Gamma night tasks do. It prints one JSON line with the job's notes
(the freeze outcome, ``core.ledger``) and exits 0 only when the job is done.
"""
from __future__ import annotations

import argparse
import json
import time

import httpx

from RevenueChaser.core import calendar, ledger

EXIT_NOT_READY = 3
DASHBOARD = "http://127.0.0.1:8000"     # app.dashboard.main's port
_HEADERS = {"X-RC-Panel": "cli"}        # every non-GET request needs it (CLAUDE.md)
_POLL_S = 20.0
_WAIT_S = 100 * 60                      # under the units' 2 h limit; the job itself keeps running past it

# board -> the dashboard's job route (app/dashboard.py ``jobs.register``)
ROUTES = {
    "ag": "module_asymmetric_growth",
    "swing": "swing",
    "fundamentals": "module_fundamentals",
    "comovement": "module_comovement",
    # avo 18 Nov 2026 ("Zamanlayiciyi kur"): the two boards that only had a dashboard button. /run/rotation also
    # queues the Money flow refresh; /run/earnings with no dates fetches the server's today (Amsterdam), which at
    # the timer's hour is the coming New York session.
    "rotation": "rotation",
    "earnings": "earnings",
    # News earnings (#886): next week's report day of every watch-list name, store-only, every Sunday 09:00.
    "news-earnings": "news_earnings",
}

#: The boards whose Fetch scores against a session and so waits for its SPY bar. A board that only reads a
#: calendar of days still to come has no session to wait for (#886), and on a Sunday there is none to wait for
#: either: it runs as soon as the store is idle.
NEEDS_SESSION = frozenset(ROUTES) - {"news-earnings"}


def _wait_idle(deadline: float) -> list[str]:
    """Poll ``/api/idle`` until it says idle (``[]``) or ``deadline`` passes (the last reasons). The builder runs
    hourly, not after a fixed nightly step, so a timer alone cannot order a Fetch after it (17 Nov 2026)."""
    while True:
        body = httpx.get(f"{DASHBOARD}/api/idle", timeout=30).json()
        if body.get("idle"):
            return []
        if time.monotonic() > deadline:
            return body.get("reasons") or ["not idle"]
        time.sleep(_POLL_S)


def run(board: str) -> int:
    deadline = time.monotonic() + _WAIT_S
    try:
        busy = _wait_idle(deadline)
    except httpx.HTTPError as exc:
        print(json.dumps({"board": board, "status": "dashboard_down", "error": str(exc)}))
        return 1
    if busy:
        print(json.dumps({"board": board, "status": "not_ready", "reason": "store busy: " + "; ".join(busy)}))
        return EXIT_NOT_READY
    session = calendar.latest_complete_session()
    if board in NEEDS_SESSION and not ledger.d01_has_session(session, "SPY"):
        print(json.dumps({"status": "not_ready", "reason": f"the prices store has no complete SPY bar for {session}"}))
        return EXIT_NOT_READY
    route = ROUTES[board]
    try:
        r = httpx.post(f"{DASHBOARD}/run/{route}", headers=_HEADERS, timeout=60)
        body = r.json()
        if r.status_code != 202:
            out = {"status": "refused", "http": r.status_code, "error": body.get("error")}
        else:
            out = {"status": "timeout", "job_id": body["job_id"]}
            while time.monotonic() <= deadline:
                job = httpx.get(f"{DASHBOARD}/api/job/{body['job_id']}", timeout=30).json().get("job") or {}
                if job.get("status") in ("done", "error", "cancelled"):
                    out = {"status": job["status"], "job_id": body["job_id"],
                           "message": job.get("message") or job.get("error"), "notes": job.get("notes") or []}
                    break
                time.sleep(_POLL_S)
    except httpx.HTTPError as exc:
        out = {"status": "dashboard_down", "error": str(exc)}
    print(json.dumps({"board": board, "session": session.isoformat(), **out}, ensure_ascii=False))
    return 0 if out["status"] == "done" else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("board", choices=sorted(ROUTES))
    return run(p.parse_args(argv).board)


if __name__ == "__main__":
    raise SystemExit(main())
