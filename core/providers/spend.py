"""The dashboard's own provider spend, on the builder's ledger (#166 item 1).

A board Fetch goes out to the same providers the builder uses and spends the same quota, but until this module
nothing on the app side wrote a number anywhere: ``provider_health`` is computed per run and shown as that run's
banner (``core/reporting_common.py`` ``provider_health_html``), and since #860 took ``result_runs`` with it, not
even that survives the render. So the Spend card on Settings / Data health counted the builder alone, and the
caps were measured against half of what was really spent.

This module is the other half: the app's clients count here, and ``rcdata.ops.provider_calls_daily`` -- the one
counter ``rcdata.caps`` reads and the Spend card renders -- holds both halves under the same provider names
(``uw``, ``sec``, ``yfinance``). Nothing on the page changes shape; its numbers become true.

**The unit, per provider, is the builder's unit for that provider** (#166 design question 2), because the two
write the same row:

* ``uw`` and ``sec``: one count per **HTTP request sent**, retries included. A request cut off by a timeout was
  still made and the provider still counted it (#519 finding 3).
* ``yfinance``: one count per **Yahoo read** (``yfinance.attempt``), as ``rcdata/build/sources/yahoo.py`` counts
  it -- the library fetches its own cookie and crumb, so a read is one or more requests.

``failures`` is a final failure (the retries are spent), never one attempt of a retry ladder; ``http_429`` is one
per 429 answer. A call the circuit breaker refused sent nothing and is counted nowhere.

**What this is not.** It is a record, not a gate: nothing here refuses a Fetch that would cross a cap (#166
item 5). It makes no request of its own to find out what was spent (design question 6) -- every number comes from
what the client already did.

**Rollback without a revert:** ``RC_APP_SPEND=0`` stops the writes, read at call time. The clients go on working;
the Spend card then counts the builder only, as it did before this module.

A write is buffered, like the builder's (``rcdata/build/base.py`` ``count`` / ``flush_counts``): a provider's
counts go to ``ops.sqlite`` once ``FLUSH_EVERY`` calls or ``FLUSH_AFTER_S`` seconds have gathered, so a Fetch of
a few thousand names costs tens of writes and not thousands. A failed write (a locked ``ops.sqlite``) keeps the
counts pending for the next flush rather than dropping them, and never fails the provider call it was counting.

**Counts belong to the ledger they were made against** (#1267). Because they are written later, the store the
write lands in is whichever one the process points at *then* (``ops.ledger_id``), not the one that was open when
the call was counted. A process that moves its market root -- the test suite, which gives every test its own
root, and an e2e dashboard -- would otherwise have the gathered counts of one root written into the next root's
``provider_calls_daily`` row, which is what #1267 measured: a test that asked a provider twice read 25 (exactly
``FLUSH_EVERY``) from the counter, because the flush point was reached inside it with another root's backlog in
hand. Pending counts whose ledger is no longer the current one are therefore **dropped**, with a warning and a
record in :func:`dropped`: they cannot be written to the store they belong to (the write path resolves the store
itself), and adding them to another store's row is a wrong number in the counter the day caps read. In a live
process the root never moves, so nothing is ever dropped there.
"""
from __future__ import annotations

import atexit
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

#: ``RC_APP_SPEND=0``: count nothing. Any other value, or unset, counts.
ENV = "RC_APP_SPEND"
#: A provider's pending counts are written once this many calls have gathered.
FLUSH_EVERY = 25
#: ...or this long after the first pending count of that provider, whichever comes first.
FLUSH_AFTER_S = 30.0

_lock = threading.Lock()
_pending: dict[str, list[int]] = {}        # provider -> [calls, failures, http_429]
_since: dict[str, float] = {}              # provider -> the clock of its first pending count
_ledger: str | None = None                 # the ledger ``_pending`` was counted against (``ops.ledger_id``)
_dropped: dict[str, list[int]] = {}        # provider -> what was dropped with a ledger that moved (#1267)
_clock = time.monotonic


def on() -> bool:
    """Whether the ledger is being written, read at call time (so the switch takes effect without a restart)."""
    return (os.getenv(ENV) or "").strip() != "0"


def _ledger_now() -> str | None:
    """The ledger a write would land in now, or None when ops cannot be reached. Never raises."""
    try:
        from ...rcdata import ops
        return ops.ledger_id()
    except Exception:                                   # noqa: BLE001 - counting may never break a provider call
        logger.warning("the spend ledger could not be identified; counts stay pending", exc_info=True)
        return None


def _drop_locked(now: str | None) -> None:
    """Drop the pending counts, whose ledger is not ``now`` any more. The caller holds ``_lock``."""
    global _ledger
    if not _pending:
        _ledger = now
        return
    taken = {n: list(b) for n, b in _pending.items()}
    for name, book in taken.items():
        kept = _dropped.setdefault(name, [0, 0, 0])
        for i in range(3):
            kept[i] += book[i]
    _pending.clear()
    _since.clear()
    logger.warning("the market root moved from %s to %s with %s pending on the spend ledger; "
                   "they belong to the old store and are not written to the new one (#1267)",
                   _ledger, now, {n: b[0] for n, b in taken.items()})
    _ledger = now


def dropped() -> dict[str, list[int]]:
    """What was counted against a ledger the process left before the counts were written (#1267)."""
    with _lock:
        return {k: list(v) for k, v in _dropped.items()}


def count(provider: str, calls: int = 0, failures: int = 0, http_429: int = 0) -> None:
    """Add to ``provider``'s pending counts and flush them when they are due. Never raises."""
    if not on() or not (calls or failures or http_429):
        return
    now = _ledger_now()
    with _lock:
        global _ledger
        if now is not None and _ledger is not None and now != _ledger:
            _drop_locked(now)
        elif _ledger is None:
            _ledger = now
        book = _pending.setdefault(provider, [0, 0, 0])
        book[0] += calls
        book[1] += failures
        book[2] += http_429
        _since.setdefault(provider, _clock())
        due = book[0] >= FLUSH_EVERY or _clock() - _since[provider] >= FLUSH_AFTER_S
    if due:
        flush(provider)


def flush(provider: str | None = None) -> None:
    """Write the pending counts (of ``provider``, or of every provider) to ``ops.provider_calls_daily``.

    A store error leaves them pending, so the next flush writes them and the day's count loses nothing
    (``rcdata/build/base.py`` ``flush_counts``, #519 finding 4). Never raises.
    """
    try:
        from ...rcdata import ops
    except Exception:                                   # noqa: BLE001 - counting may never break a provider call
        logger.warning("the spend ledger is not reachable; counts stay pending", exc_info=True)
        return
    now = _ledger_now()
    with _lock:
        if now is not None and _ledger is not None and now != _ledger:
            # The counts were made against another store and the write path resolves the store itself (#1267).
            _drop_locked(now)
            return
        names = [provider] if provider is not None else sorted(_pending)
        taken = {n: _pending.pop(n) for n in names if n in _pending}
        for n in taken:
            _since.pop(n, None)
    for name, (calls, failures, http_429) in taken.items():
        try:
            ops.count_calls(name, calls, failures=failures, http_429=http_429)
        except Exception:                               # noqa: BLE001 - as above; kept for the next flush
            logger.warning("the spend of %s was not written; it stays pending", name, exc_info=True)
            with _lock:
                book = _pending.setdefault(name, [0, 0, 0])
                book[0] += calls
                book[1] += failures
                book[2] += http_429
                _since.setdefault(name, _clock())


def pending() -> dict[str, list[int]]:
    """What is counted and not yet written, per provider: for a test and for a reader of this process's state."""
    with _lock:
        return {k: list(v) for k, v in _pending.items()}


atexit.register(flush)
