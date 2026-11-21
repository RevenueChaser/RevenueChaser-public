"""The door's write log: one JSON line per write or guarded press, allowed or refused.

Run plan row 7 asks for "a write log", and the question it has to answer afterwards is a narrow one: *who pressed
what, when, and did it go through*. So a line carries nine fields and no tenth, and three things are deliberately
absent.

* **No body and no query string.** A press whose body decided what happened is a press the dashboard logged in its
  own run record; copying it here would put a second copy of whatever the caller typed into a second file, and the
  `private_check` guard exists because a second copy is how a value ends up somewhere it was never meant to be.
* **No header but the login.** ``X-RC-Panel`` says which screen pressed and is not evidence of anything;
  a cookie or an ``Authorization`` the door never forwards is not written down either.
* **No traceback.** An upstream that did not answer is a status and a reason, never an exception's text, which can
  carry a URL that holds a password.

**Where it goes.** The line is emitted through the ``RevenueChaser.v2.door.write`` logger, which on homesrv is the
container's stdout and so journald — the door's image is ``read_only: true`` with one ``:ro`` mount, and a write
log that needed a writable mount would have made the write side need the artifacts root to change, which #1317
says it must not. ``RC_DOOR_WRITE_LOG`` adds a file beside it when there is somewhere to put one; with the
variable unset nothing is written to disk and the record still happens.

**Why the login is cut and escaped.** It is a caller's header value. ``json.dumps`` escapes a newline, so one
press is one line however the value is written, and :data:`MAX_LOGIN_CHARS` stops a very long value from being the
whole of a log file.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from RevenueChaser.v2.door import config, proxy

LOGGER = logging.getLogger("RevenueChaser.v2.door.write")

#: A tailnet login is an address. Anything longer than this is not one, and is cut rather than written whole.
MAX_LOGIN_CHARS = 200

#: The fields of a line, in order, and the whole of it. ``v2/tests/test_door_proxy.py`` fails a tenth.
FIELDS = ("ts", "login", "method", "path", "klass", "outcome", "reason", "status", "duration_ms")


def should_record(decision: proxy.Decision) -> bool:
    """True for a write and for a guarded press. A read is not a write and is not logged: it is the common case,
    and a log that held every board poll would bury the lines that matter."""
    return decision.klass in (proxy.RouteClass.WRITE, proxy.RouteClass.GUARDED)


def record(decision: proxy.Decision, *, method: str, path: str, login: str, status: int,
           duration_ms: int) -> dict:
    """Write one line for this press and return it.

    ``status`` is what the caller was answered, which for an allowed write is the dashboard's own answer: a press
    that reached the dashboard and was refused *there* reads as ``allowed`` with a 403, and that distinction is
    the reason the outcome and the status are two fields.
    """
    row = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "login": _clean(login),
        "method": method.upper(),
        "path": path,
        "klass": decision.klass.value if decision.klass else "",
        "outcome": "allowed" if decision.allowed else "refused",
        "reason": decision.reason,
        "status": int(status),
        "duration_ms": int(duration_ms),
    }
    line = json.dumps({name: row[name] for name in FIELDS}, ensure_ascii=False, separators=(",", ":"))
    LOGGER.info("%s", line)
    path_on_disk = config.write_log_path()
    if path_on_disk is not None:
        try:
            path_on_disk.parent.mkdir(parents=True, exist_ok=True)
            with path_on_disk.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:                  # a read-only root is a misconfiguration, not a reason to 500
            LOGGER.warning("the write log file could not be appended to: %s: %s", type(exc).__name__, exc)
    return row


def _clean(login: str) -> str:
    """One line, at most :data:`MAX_LOGIN_CHARS` characters, with the control characters gone."""
    flat = "".join(ch for ch in (login or "") if ch.isprintable())
    return flat[:MAX_LOGIN_CHARS]
