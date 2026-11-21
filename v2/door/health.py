"""The door's health probes: one named check per dependency, each with its own time budget.

Run plan row 6 asks for "2 s probes", and the reason is the shape of the failure it guards against: a dependency
that is reachable but wedged. A probe without a budget turns the health route into the same wedge, and a monitor
that times out learns nothing about *which* dependency is at fault. So every probe runs in its own thread with
:data:`config.PROBE_BUDGET_S` seconds; one that overruns is reported ``timeout`` and the others still answer.

A probe returns ``(ok, detail)``. ``ok`` is ``True``, ``False`` or ``None`` — ``None`` meaning "not configured",
which is not a fault: with no ``RC_REDIS_URL`` the read side is complete without Redis, and reporting that as red
would make a correct deployment look broken.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from RevenueChaser.v2.door import boards, config

# A probe whose ``ok`` is ``False`` makes the route answer 503. ``redis`` is not among them: the read side reads
# files, and step 7's write side is what will need the queue (its own PR adds the requirement here).
REQUIRED = ("artifacts",)


def probe_artifacts() -> tuple[bool | None, str]:
    """The artifacts root is there and readable, and how many of the six envelopes are present."""
    root = boards.artifacts_dir()
    if not root.is_dir():
        return False, f"{root} is not a directory"
    rows = boards.board_list()
    present = [row["board"] for row in rows if row["present"]]
    return True, f"{len(present)}/{len(rows)} envelopes in {root}"


def probe_redis() -> tuple[bool | None, str]:
    """Redis answers ``PING``, when ``RC_REDIS_URL`` is set; ``None`` (not a fault) when it is not.

    The import is inside the function so the door starts without the ``redis`` package when no URL is set, and so
    the probe's own failure mode is the probe's, not the module's.
    """
    url = config.redis_url()
    if not url:
        return None, "RC_REDIS_URL not set; the read side needs no queue"
    import redis
    client = redis.Redis.from_url(url, socket_connect_timeout=config.PROBE_BUDGET_S,
                                  socket_timeout=config.PROBE_BUDGET_S)
    try:
        client.ping()
        return True, "PING"
    finally:
        client.close()


PROBES = {"artifacts": probe_artifacts, "redis": probe_redis}


def run(probes=None, budget_s: float | None = None) -> dict:
    """Every probe's result, plus the one word a monitor reads.

    ``status`` is ``ok`` when no required probe is red, else ``degraded``; the route turns the second one into 503.
    A probe that raises is red with its exception's text, never a traceback and never a value from it: a probe
    reads a URL that may hold a password, so only the exception class and its message reach the response.
    """
    probes = dict(PROBES if probes is None else probes)
    budget = config.PROBE_BUDGET_S if budget_s is None else budget_s
    checks = []
    # Not a `with` block: its ``shutdown(wait=True)`` would block on exactly the wedged probe the budget exists to
    # escape, so the pool is released without waiting and a stuck thread is left to end on its own.
    pool = ThreadPoolExecutor(max_workers=max(1, len(probes)), thread_name_prefix="door-probe")
    try:
        futures = {name: pool.submit(fn) for name, fn in probes.items()}
        for name, future in futures.items():
            checks.append({"check": name, **_result(future, budget)})
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    bad = [c["check"] for c in checks if c["check"] in REQUIRED and c["ok"] is False]
    return {"status": "degraded" if bad else "ok", "failed": bad, "budget_s": budget, "checks": checks}


def _result(future, budget: float) -> dict:
    try:
        ok, detail = future.result(timeout=budget)
    except FutureTimeout:
        future.cancel()
        return {"ok": False, "detail": f"no answer in {budget:g}s"}
    except Exception as exc:                        # noqa: BLE001 - a probe's fault is a result, not a 500
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
    return {"ok": ok, "detail": detail}
