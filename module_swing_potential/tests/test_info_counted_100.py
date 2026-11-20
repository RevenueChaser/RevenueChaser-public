"""#100: Swing's ``.info`` sweep is counted in the run's own scope, and a 401 no longer poisons the sweep.

Measured on ``main`` c2b2c88 (20 Nov 2026): ``load_ticker_info`` counted on ``yfinance._HEALTH`` directly. Since
#299 the module global is only half the accounting — a run opens its own thread-local ``health_scope`` and the
board's banner reads that — so the Swing banner showed **zero** yfinance calls while the sweep made one
``.info`` request per name. The read also never consulted the 401 cure (#402), which is exactly the 14 Oct
failure: the first refused name left every later one failing the same way.

Offline: yfinance answers nothing real here and the session reset is faked.
"""
from __future__ import annotations

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


def test_swing_info_read_reaches_the_runs_own_scope(monkeypatch, rawstore_tmp_db):
    """The #299 bug: it counted on the module global, so the Swing banner read zero all sweep long."""
    import yfinance

    from RevenueChaser.module_swing_potential import indicators

    class _T:
        def __init__(self, ticker):
            pass

        @property
        def info(self):
            return {"marketCap": 1_000_000.0, "sharesOutstanding": 1000.0, "floatShares": 900.0}

    monkeypatch.setattr(yfinance, "Ticker", _T)
    with yfp.health_scope() as health:
        got = indicators.load_ticker_info("AAPL")
    assert got.get("marketCap") == 1_000_000.0
    assert health.health()["calls"] == 1, "one .info request per name must show in the board's own banner"


def test_swing_info_read_retries_after_a_401(monkeypatch, rawstore_tmp_db, resets):
    import yfinance

    from RevenueChaser.module_swing_potential import indicators

    tries: list[int] = []

    class _T:
        def __init__(self, ticker):
            pass

        @property
        def info(self):
            tries.append(1)
            if len(tries) == 1:
                raise RuntimeError(AUTH)
            return {"marketCap": 2_000_000.0, "sharesOutstanding": 1000.0, "floatShares": 900.0}

    monkeypatch.setattr(yfinance, "Ticker", _T)
    got = indicators.load_ticker_info("AAPL")
    assert got.get("marketCap") == 2_000_000.0, "the sweep's first name no longer poisons the rest of the night"
    assert len(tries) == 2 and len(resets) == 1
