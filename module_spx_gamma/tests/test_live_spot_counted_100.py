"""#1213 (split out of #100 / PR #1211): the board's one live Yahoo read is counted and 401-cured.

``candles.live_spot`` is the owner's spot exception of 2026-10-22 — one yfinance request a session, because spot
sets the +/-25% strike window for the UW spot-exposure calls and the board's ``current_level``. It called the
library directly, so for a month it was:

* **uncounted** — the SPX Gamma banner (#299) reads the ``health_scope`` the run opens, and this read reached
  neither that scope nor the module global;
* **outside the 401 cure** — a Yahoo "Invalid Crumb" refusal was reported once and never retried after a session
  reset, although #1211 wired that cure into every other Yahoo read.

Offline: no yfinance read answers anything real, the session reset is faked, and the root ``isolate_yf_session``
keeps one test's pending 401 out of the next.
"""
from __future__ import annotations

import pandas as pd
import pytest

from RevenueChaser.core import calendar as nyse_calendar
from RevenueChaser.core.providers import yf_session
from RevenueChaser.core.providers import yfinance as yfp
from RevenueChaser.module_spx_gamma import candles


@pytest.fixture(autouse=True)
def session_open(monkeypatch):
    """Spot is read only while the US session is open; every test here wants that half decided."""
    monkeypatch.setattr(nyse_calendar, "in_us_session_window", lambda *a, **k: True)


@pytest.fixture
def resets(monkeypatch):
    """Count the session resets and keep the real one off the installed library."""
    done: list[int] = []
    monkeypatch.setattr(yf_session, "_reset", lambda: (done.append(1), ["crumb"])[1])
    return done


def _ticker(frames, *, raises=None):
    """A ``yfinance.Ticker`` whose ``history`` answers from ``frames`` in order (or raises first)."""
    seen: list[dict] = []

    class _T:
        def __init__(self, symbol):
            seen.append({"symbol": symbol})

        def history(self, **kw):
            seen[-1].update(kw)
            if raises is not None and len(seen) == 1:
                raise raises
            return frames[min(len(seen), len(frames)) - 1]

    return _T, seen


def _saw_401() -> None:
    """What yfinance's logger does when Yahoo refuses the crumb: the watcher notes it, nothing raises."""
    yf_session._STATE["seen"] = yf_session.clock()


def test_the_live_spot_read_reaches_the_runs_own_scope(monkeypatch):
    import yfinance

    cls, _seen = _ticker([pd.DataFrame({"Close": [7700.0, 7777.5]})])
    monkeypatch.setattr(yfinance, "Ticker", cls)
    with yfp.health_scope() as health:
        assert candles.live_spot() == (7777.5, None)
    reported = health.health()
    assert reported["calls"] == 1 and reported["failed"] == 0, "the board's banner must see the read it made"


def test_a_refused_read_is_counted_failed_in_the_scope(monkeypatch):
    import yfinance

    cls, _seen = _ticker([], raises=RuntimeError("Yahoo said no"))
    monkeypatch.setattr(yfinance, "Ticker", cls)
    with yfp.health_scope() as health:
        spot, error = candles.live_spot()
    assert spot is None and "Yahoo said no" in error
    reported = health.health()
    assert reported["calls"] == 1 and reported["failed"] == 1


def test_a_401_is_cured_by_one_session_reset_and_the_read_is_retried(monkeypatch, resets):
    """The 14 Oct night of #402: without the cure the refusal stands and the board falls back to a stale close."""
    import yfinance

    _saw_401()
    cls, seen = _ticker([pd.DataFrame({"Close": [7801.25]})],
                        raises=RuntimeError("HTTP Error 401: Invalid Crumb"))
    monkeypatch.setattr(yfinance, "Ticker", cls)
    assert candles.live_spot() == (7801.25, None), "one reset, then the read again"
    assert len(resets) == 1 and len(seen) == 2


def test_a_logged_401_with_an_empty_frame_is_retried_too(monkeypatch, resets):
    """A refused ``history`` raises nothing: it logs the 401 and hands back an empty frame, which is the shape
    this read actually meets."""
    import yfinance

    _saw_401()
    cls, seen = _ticker([pd.DataFrame({"Close": []}), pd.DataFrame({"Close": [7650.0]})])
    monkeypatch.setattr(yfinance, "Ticker", cls)
    assert candles.live_spot() == (7650.0, None)
    assert len(resets) == 1 and len(seen) == 2


def test_an_honestly_empty_answer_is_counted_once_and_not_retried(monkeypatch, resets):
    """No pending 401, so nothing to cure: one read, counted, and the caller falls back with a reason."""
    import yfinance

    cls, seen = _ticker([pd.DataFrame({"Close": []})])
    monkeypatch.setattr(yfinance, "Ticker", cls)
    with yfp.health_scope() as health:
        assert candles.live_spot() == (None, "no live bar returned")
    assert not resets and len(seen) == 1
    assert health.health()["calls"] == 1, "an empty answer is still a request the banner should count"


def test_the_read_cannot_go_back_behind_the_provider(monkeypatch):
    """A guard against the regression this issue is: if ``live_spot`` stops going through ``attempt``, the read
    is silently uncounted again and nothing else here would fail — the fakes patch the library, not the helper."""
    import yfinance

    cls, _seen = _ticker([pd.DataFrame({"Close": [7777.5]})])
    monkeypatch.setattr(yfinance, "Ticker", cls)
    passed: list[str] = []
    real = yfp.attempt
    monkeypatch.setattr(yfp, "attempt", lambda *a, **kw: (passed.append(kw.get("endpoint", "")), real(*a, **kw))[1])
    assert candles.live_spot()[0] == 7777.5
    assert passed == ["spx_gamma/live_spot"], "every Yahoo read belongs in core.providers.yfinance.attempt"
