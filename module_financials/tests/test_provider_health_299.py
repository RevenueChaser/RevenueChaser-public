"""#299 (Financials half): the board's amber banner is backed by a real ProviderHealth.

``reporting/html_builder`` renders ``provider_health_html(results.get("provider_health"))`` while nothing
ever built one, so a failed Yahoo read was invisible on the board. A run now takes its own scope of the
yfinance client's call accounting (``yfinance.health_scope``) and hands it to the payload.

The scope matters: the client's counter is a module global shared by every board, and the dashboard runs two
job workers, so a plain ``reset()`` here would zero another board's run in flight.

SEC EDGAR is not in this banner on purpose: since G6 the statements come from the fundamentals serving layer
(``run._sec_statements`` -> ``fundamentals_layer.records``), which makes no request.
"""
from __future__ import annotations

import threading

import pytest

from RevenueChaser.core.providers import yfinance as yfinance_client
from RevenueChaser.core.reporting_common import provider_health_html
from RevenueChaser.module_financials.engines import comps_engine


@pytest.fixture(autouse=True)
def _clean_global():
    yfinance_client.reset_health()
    yield
    yfinance_client.reset_health()


class _Boom:
    """A ``yf.Ticker`` whose every read raises, as an outage does."""

    def __init__(self, ticker: str = "AAPL"):
        self.ticker = ticker

    @property
    def info(self):
        raise RuntimeError("503 Service Unavailable")

    def __getattr__(self, name):
        raise RuntimeError("503 Service Unavailable")


def test_a_failed_yahoo_read_is_counted_in_the_runs_scope(monkeypatch):
    import sys
    fake = type(sys)("yfinance")
    fake.Ticker = lambda ticker: _Boom(ticker)
    monkeypatch.setitem(sys.modules, "yfinance", fake)

    with yfinance_client.health_scope() as health:
        yfinance_client.get_financials("AAPL")
        got = health.health()

    assert got["provider"] == "yfinance"
    # ``.info`` plus every statement label the client tries: income_stmt/financials, cashflow/cash_flow,
    # balance_sheet.
    assert (got["calls"], got["failed"]) == (6, 6)
    assert got["failures"][0]["endpoint"] == "AAPL.info"
    assert "6 of 6 Yahoo Finance calls failed" in provider_health_html(got)


def test_a_clean_read_raises_no_banner():
    with yfinance_client.health_scope() as health:
        yfinance_client._count(endpoint="AAPL.info")
        got = health.health()
    assert (got["calls"], got["failed"]) == (1, 0)
    assert provider_health_html(got) == ""


def test_a_scope_counts_only_its_own_runs_calls():
    """Without this a second board's Fetch in the other job worker would land in this board's banner."""
    yfinance_client._count(error="before", endpoint="OTHER.info")
    with yfinance_client.health_scope() as health:
        yfinance_client._count(error="mine", endpoint="AAPL.info")
    yfinance_client._count(error="after", endpoint="OTHER.info")

    got = health.health()
    assert (got["calls"], got["failed"]) == (1, 1)
    assert [f["endpoint"] for f in got["failures"]] == ["AAPL.info"]
    assert yfinance_client.health()["calls"] == 3          # the shared global still sees every call


def test_another_threads_calls_stay_out_of_this_scope():
    with yfinance_client.health_scope() as health:
        other = threading.Thread(target=lambda: yfinance_client._count(error="theirs", endpoint="OTHER.info"))
        other.start()
        other.join()
        yfinance_client._count(endpoint="AAPL.info")
    assert (health.health()["calls"], health.health()["failed"]) == (1, 0)


def test_a_comps_peer_info_read_is_counted(monkeypatch):
    """The comps ladder fetched ``.info`` per peer straight from ``yf``, so a failed peer read was uncounted."""
    import sys
    fake = type(sys)("yfinance")
    fake.Ticker = lambda ticker: _Boom(ticker)
    monkeypatch.setitem(sys.modules, "yfinance", fake)

    with yfinance_client.health_scope() as health:
        assert comps_engine._default_fetch("MSFT") == {}
    got = health.health()
    assert (got["calls"], got["failed"]) == (1, 1)
    assert got["failures"][0]["endpoint"] == "MSFT.info"


def test_the_run_hands_the_banner_to_the_report(monkeypatch, tmp_path):
    """End to end: a run whose Yahoo reads failed renders the amber banner instead of a clean board."""
    import RevenueChaser.module_financials.run as fin_run
    from RevenueChaser.core import universe as spine

    monkeypatch.setattr(fin_run, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(fin_run.yfinance_client, "get_financials",
                        lambda ticker, **kw: (fin_run.yfinance_client._count(error="503 Service Unavailable",
                                                                            endpoint=f"{ticker}.info"),
                                              {"ticker": ticker, "annual": []})[1])
    monkeypatch.setattr(fin_run.market_inputs, "overlay", lambda ticker, fin: (fin, "Yahoo"))
    monkeypatch.setattr(fin_run, "_sec_statements", lambda ticker: None)
    monkeypatch.setattr(fin_run, "_stored_risk_free", lambda: None)
    monkeypatch.setattr(spine, "spine_gics", lambda tickers: {})
    monkeypatch.setattr(fin_run.quick_remarks_engine, "run_quick_remarks",
                        lambda ticker, no_fetch=False, financials=None: {})

    out = fin_run.run("AAPL", modules=["dcf"], output="html")

    health = out["results"]["provider_health"]
    assert (health["provider"], health["calls"], health["failed"]) == ("yfinance", 1, 1)
    assert "Yahoo Finance" in (tmp_path / "AAPL_report.html").read_text(encoding="utf-8")
