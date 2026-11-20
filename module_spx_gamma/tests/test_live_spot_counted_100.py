"""#100: ``candles.live_spot`` — the board's one live Yahoo request a session, counted and 401-cured.

Measured on ``main`` c2b2c88 (20 Nov 2026): the read called ``yfinance.Ticker(...).history`` directly, so the
SPX Gamma banner never counted it and a refused session was never reset. The 14 Oct shape matters here: the
library does not raise a refused ``history``, it logs the 401 and hands back an empty frame, so the empty
answer is what has to reach the cure.

Offline: yfinance answers nothing real here and the session reset is faked.
"""
from __future__ import annotations

import pandas as pd
import pytest

from RevenueChaser.core.providers import yf_session
from RevenueChaser.core.providers import yfinance as yfp

AUTH = "HTTP Error 401: Invalid Crumb"


@pytest.fixture
def resets(monkeypatch):
    """Count the session resets and keep the real one off the installed library."""
    done: list[int] = []
    monkeypatch.setattr(yf_session, "_reset", lambda: (done.append(1), ["crumb"])[1])
    return done


def test_live_spot_is_counted_for_the_banner(monkeypatch):
    import yfinance

    from RevenueChaser.core import calendar as nyse_calendar
    from RevenueChaser.module_spx_gamma import candles

    monkeypatch.setattr(nyse_calendar, "in_us_session_window", lambda *a, **k: True)

    class _T:
        def __init__(self, symbol):
            pass

        def history(self, **kw):
            return pd.DataFrame({"Close": [7700.0, 7777.5]})

    monkeypatch.setattr(yfinance, "Ticker", _T)
    with yfp.health_scope() as health:
        assert candles.live_spot() == (7777.5, None)
    assert health.health()["calls"] == 1, "the one live request a session must show in the banner"


def test_live_spot_retries_after_a_401_yfinance_only_logged(monkeypatch, resets):
    """The 14 Oct shape: the library logs the 401 and hands back an empty frame, raising nothing."""
    import yfinance

    from RevenueChaser.core import calendar as nyse_calendar
    from RevenueChaser.module_spx_gamma import candles

    monkeypatch.setattr(nyse_calendar, "in_us_session_window", lambda *a, **k: True)
    tries: list[int] = []

    class _T:
        def __init__(self, symbol):
            pass

        def history(self, **kw):
            tries.append(1)
            if len(tries) == 1:
                yf_session._STATE["seen"] = yf_session.clock()   # what the log watcher does
                return pd.DataFrame()
            return pd.DataFrame({"Close": [8001.0]})

    monkeypatch.setattr(yfinance, "Ticker", _T)
    assert candles.live_spot() == (8001.0, None)
    assert len(tries) == 2 and len(resets) == 1


def test_live_spot_still_reports_an_empty_answer_as_its_reason(monkeypatch, resets):
    import yfinance

    from RevenueChaser.core import calendar as nyse_calendar
    from RevenueChaser.module_spx_gamma import candles

    monkeypatch.setattr(nyse_calendar, "in_us_session_window", lambda *a, **k: True)

    class _T:
        def __init__(self, symbol):
            pass

        def history(self, **kw):
            return pd.DataFrame()

    monkeypatch.setattr(yfinance, "Ticker", _T)
    spot, error = candles.live_spot()
    assert spot is None and error == "no live bar returned"
    assert resets == [], "no 401 pending: nothing to cure"


def test_live_spot_counts_a_refused_read_as_failed(monkeypatch):
    import yfinance

    from RevenueChaser.core import calendar as nyse_calendar
    from RevenueChaser.module_spx_gamma import candles

    monkeypatch.setattr(nyse_calendar, "in_us_session_window", lambda *a, **k: True)

    class _T:
        def __init__(self, symbol):
            pass

        def history(self, **kw):
            raise RuntimeError("Yahoo refused the window")

    monkeypatch.setattr(yfinance, "Ticker", _T)
    with yfp.health_scope() as health:
        spot, error = candles.live_spot()
    assert spot is None and "Yahoo refused the window" in error
    assert health.health()["failed"] == 1
