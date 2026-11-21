"""#1267 — a count belongs to the ledger it was made against, and is never added to another one's row.

``core/providers/spend.py`` holds a provider's counts in a module global and writes them once ``FLUSH_EVERY``
calls or ``FLUSH_AFTER_S`` seconds have gathered. The write path resolves the store itself (``ops.ledger_id``:
the Redis namespace, or ``<MARKET_DIR>/ops.sqlite``), so a process that moved its market root in between wrote
the counts of the **old** root into the **new** root's ``provider_calls_daily`` row.

Measured in CI on 21 Nov 2026 (#1267): ``rcdata/tests/test_fund_fx.py`` asked Yahoo twice, read **25** from the
counter -- exactly ``FLUSH_EVERY`` -- and ``test_fund_estimates.py`` asked four times and read 6. Both start from
a counter of 0, so nothing had leaked into their namespace; what reached the row was the suite's own backlog,
flushed inside a test that happened to make the call that reached the flush point. The counter is the one
``rcdata.caps`` reads for the day caps, and about twenty assertions across ``rcdata/tests/`` read it absolutely.

A live process never moves its root, so nothing is dropped there; the suite and the e2e dashboards do. That the
buffer still writes everything a root counted while the root stays put is pinned where it always was, by
``core/providers/tests/test_app_spend_166.py``: a test of it here would be green on the base and prove nothing.
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import calendar as rc_calendar
from RevenueChaser.core import config
from RevenueChaser.core.providers import spend
from RevenueChaser.rcdata import ops


@pytest.fixture(autouse=True)
def clean_spend(monkeypatch):
    """An empty buffer, the ledger on, and the clock under this test's control."""
    monkeypatch.delenv(spend.ENV, raising=False)
    monkeypatch.setattr(spend, "_pending", {})
    monkeypatch.setattr(spend, "_since", {})
    # ``raising=False``: on the merge base these two do not exist yet, so ``red-on-base`` reads the
    # assertion each test makes and not an error in its fixture.
    monkeypatch.setattr(spend, "_dropped", {}, raising=False)
    monkeypatch.setattr(spend, "_ledger", None, raising=False)
    now = [0.0]
    monkeypatch.setattr(spend, "_clock", lambda: now[0])
    return now


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """Two market roots and the move between them, as the suite's own per-test roots are."""
    a, b = tmp_path / "root-a" / "market", tmp_path / "root-b" / "market"

    def point_at(root):
        monkeypatch.setattr(config, "MARKET_DIR", root)

    point_at(a)
    return a, b, point_at


def _row(provider: str) -> dict:
    """``provider``'s row for today in the ledger the process points at now, zeros when it has none."""
    today = rc_calendar.today_ny().isoformat()
    return next((r for r in ops.calls_by_day(today, today) if r["provider"] == provider),
                {"calls": 0, "failures": 0, "http_429": 0})


def test_the_ledger_a_write_lands_in_is_named_by_the_market_root(roots):
    """Both backends name it from the market root: the ops file's path, or the Redis namespace, which
    ``ops_redis.namespace()`` hashes from that root. CI runs the suite on Redis and a workstation on the file."""
    a, b, point_at = roots
    first = ops.ledger_id()
    assert first.startswith(f"{ops.backend()}:")
    if ops.backend() == "sqlite":
        assert str(ops.ops_path()) in first
    point_at(b)
    assert ops.ledger_id() != first, "a moved root is another ledger, and a held count belongs to the old one"


def test_counts_of_one_root_are_not_added_to_the_next_roots_row(roots, clean_spend):
    """The CI failure: the flush point is reached inside a test of another root, with a backlog in hand."""
    a, b, point_at = roots
    spend.count("yfinance", calls=3)
    assert _row("yfinance")["calls"] == 0, "nothing is written before the flush point"

    point_at(b)
    clean_spend[0] += spend.FLUSH_AFTER_S          # the next count reaches the flush point
    spend.count("yfinance", calls=1)

    assert _row("yfinance")["calls"] == 0, "the three counts of the old root are not written to the new one"
    assert spend.pending() == {"yfinance": [1, 0, 0]}, "the new root's own count is held, and its clock restarts"
    assert spend.dropped() == {"yfinance": [3, 0, 0]}

    clean_spend[0] += spend.FLUSH_AFTER_S
    spend.flush()
    assert _row("yfinance")["calls"] == 1, "what this root counted, and only that, is on its row"


def test_a_flush_after_the_root_moved_writes_nothing_and_says_what_it_dropped(roots, clean_spend):
    a, b, point_at = roots
    spend.count("sec", calls=4, failures=1)
    point_at(b)
    spend.flush()
    row = _row("sec")
    assert (row["calls"], row["failures"]) == (0, 0)
    assert spend.pending() == {}
    assert spend.dropped() == {"sec": [4, 1, 0]}
