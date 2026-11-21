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

Two boards are not nightly and have no session to wait for: ``news-earnings`` (weekly, #886) and ``relatedness``
(the weekly Sunday profiling pass, #1255, whose timer keeps its own ``life-rc-relatedness`` name). They run as
soon as the store is idle. The idle wait is what #1255 is about: the profiling run used to open the board file in
a writer process of its own and exit 1 on ``StoreLockedError`` ~29 s later, losing the week's run; here a busy
store postpones it inside the window, and only a store still busy at the deadline ends the run -- with
``EXIT_NOT_READY``, which the Jobs board reads as "nothing written", not as a failure.
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
#: Boards whose unit allows a longer wait than ``_WAIT_S``. The weekly Relatedness run has a 4 h unit limit
#: (``life-rc-relatedness.service``), and waiting is the whole point of #1255: a busy store must postpone the run,
#: not end the week's one chance at it.
_BOARD_WAIT_S = {"relatedness": 230 * 60}

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
    # Relatedness profiling, weekly Sunday 22:15 (#1255). Its own unit pair is life-rc-relatedness, not
    # life-rc-fetch-relatedness: the timer predates this task and keeps its name.
    "relatedness": "module_relatedness",
}

#: Extra form fields one board's route takes. The weekly Relatedness run's spend ceiling is avo's 10 USD
#: (2 Nov 2026) and counts only when the board's writer is DeepSeek; the module's own default is 25, so the task
#: has to say it, exactly as the ``--cap 10`` of the registry row it replaces did.
FORM: dict[str, dict[str, str]] = {"relatedness": {"usd_cap": "10"}}

#: The boards whose Fetch scores against a session and so waits for its SPY bar. The others run as soon as the
#: store is idle, whatever day it is: the News earnings
#: list carries a calendar of days still to come (#886), and the Relatedness profiling pass scores profiles
#: against each other, not against a session (#1255).
NEEDS_SESSION = frozenset(ROUTES) - {"news-earnings", "relatedness"}


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
    deadline = time.monotonic() + _BOARD_WAIT_S.get(board, _WAIT_S)
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
        r = httpx.post(f"{DASHBOARD}/run/{route}", headers=_HEADERS, data=FORM.get(board), timeout=60)
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
