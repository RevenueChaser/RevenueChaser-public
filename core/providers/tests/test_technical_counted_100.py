"""#100: ``technical.fetch_technical`` reads Yahoo through the provider, counted and 401-cured.

Measured on ``main`` c2b2c88 (20 Nov 2026): this module called ``yfinance.Ticker`` directly for both its
``.info`` and its 1-year ``history``, counted neither for the board banner (#299) and swallowed a failure into
the debug log — the same shape #299 fixed for the comps ladder. It also never consulted the 401 session cure
(#402), whose only caller had been deleted with the old bar path.

Offline: yfinance answers nothing real here and the session reset is faked.
"""
from __future__ import annotations

import pandas as pd
import pytest

from revenuechaser.core.providers import yf_session
from revenuechaser.core.providers import yfinance as yfp

AUTH = "HTTP Error 401: Invalid Crumb"


@pytest.fixture
def resets(monkeypatch):
    """Count the session resets and keep the real one off the installed library."""
    done: list[int] = []
    monkeypatch.setattr(yf_session, "_reset", lambda: (done.append(1), ["crumb"])[1])
    return done


def _hist(n: int = 100) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    closes = [100.0 + i for i in range(n)]
    return pd.DataFrame({"Close": closes, "High": [c + 1 for c in closes],
                         "Volume": [1000 + i for i in range(n)]}, index=idx)


def test_technical_counts_both_of_its_reads_for_the_banner(monkeypatch):
    from revenuechaser.core.providers import technical as tech
    import yfinance

    class _T:
        def __init__(self, ticker):
            pass

        @property
        def info(self):
            return {"currentPrice": 150.0, "fiftyTwoWeekHigh": 200.0}

        def history(self, period=None):
            return _hist()

    monkeypatch.setattr(yfinance, "Ticker", _T)
    with yfp.health_scope() as health:
        out = tech.fetch_technical("AAPL")
    assert out["price"] == 150.0
    reported = health.health()
    assert reported["calls"] == 2, "the .info read and the history read both reach the banner"
    assert reported["failed"] == 0


def test_technical_counts_a_refused_info_read_as_failed(monkeypatch):
    from revenuechaser.core.providers import technical as tech
    import yfinance

    class _T:
        def __init__(self, ticker):
            pass

        @property
        def info(self):
            raise RuntimeError("Yahoo refused")

        def history(self, period=None):
            return _hist()

    monkeypatch.setattr(yfinance, "Ticker", _T)
    with yfp.health_scope() as health:
        out = tech.fetch_technical("AAPL")
    reported = health.health()
    assert reported["failed"] == 1, "a failed read must reach the banner, not only the debug log"
    assert reported["failures"][0]["endpoint"] == "AAPL.info"
    # the history still answered, so the derived values are there
    assert out["sma50"] is not None


def test_technical_retries_its_info_read_after_a_401(monkeypatch, resets):
    from revenuechaser.core.providers import technical as tech
    import yfinance

    tries: list[int] = []

    class _T:
        def __init__(self, ticker):
            pass

        @property
        def info(self):
            tries.append(1)
            if len(tries) == 1:
                raise RuntimeError(AUTH)
            return {"currentPrice": 150.0, "fiftyTwoWeekHigh": 200.0}

        def history(self, period=None):
            return _hist()

    monkeypatch.setattr(yfinance, "Ticker", _T)
    out = tech.fetch_technical("AAPL")
    assert out["price"] == 150.0, "the retry after the session reset answered"
    assert len(tries) == 2 and len(resets) == 1
