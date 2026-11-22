"""#299 (Financials half): the board's amber banner is backed by a real ProviderHealth.

``reporting/html_builder`` renders ``provider_health_html(results.get("provider_health"))`` while nothing
ever built one, so a failed Yahoo read was invisible on the board. A run now takes its own scope of the
yfinance client's call accounting (``yfinance.health_scope``). The Financials board itself no longer has a
banner: since #645 it makes no provider call, so a run records no health at all (the last test here).

The scope matters: the client's counter is a module global shared by every board, and the dashboard runs two
job workers, so a plain ``reset()`` here would zero another board's run in flight.

SEC EDGAR is not in this banner on purpose: since G6 the statements come from the fundamentals serving layer
(``run._sec_statements`` -> ``fundamentals_layer.records``), which makes no request.
"""
from __future__ import annotations

import threading

import pytest

from revenuechaser.core.providers import yfinance as yfinance_client
from revenuechaser.core.reporting_common import provider_health_html
from revenuechaser.module_financials.engines import comps_engine


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


def test_the_comps_peer_read_is_no_longer_a_provider_read_at_all(monkeypatch):
    """#286 closed this half of #299 by removing the read rather than counting it.

    The ladder used to fetch ``.info`` per peer straight from ``yf``, so a failed peer read was uncounted and a
    half-fetched comps table looked complete; #1101 routed it through the client so it reached the banner. Since
    20 Nov 2026 the peer figures come from the store (``module_financials/store_reads.peer_multiples``), so there
    is no peer call to count — and the strongest form of the old assertion is that a provider is never touched.
    """
    import sys
    fake = type(sys)("yfinance")
    fake.Ticker = lambda ticker: _Boom(ticker)
    monkeypatch.setitem(sys.modules, "yfinance", fake)

    from revenuechaser.module_financials import store_reads
    monkeypatch.setattr(store_reads, "_records", lambda tickers: {t: [] for t in tickers})
    monkeypatch.setattr(store_reads, "_market", lambda tickers: {})

    with yfinance_client.health_scope() as health:
        got = comps_engine._default_fetch_many(["MSFT"])
    assert got["MSFT"]["stored"] is False
    assert health.health()["calls"] == 0, "the comps peer side must cost no provider call"


def test_the_run_reports_no_provider_health_at_all(monkeypatch, tmp_path):
    """#645: the board makes no provider call, so a run records no health and the board renders no banner.

    This replaces the end-to-end banner test: there is no Yahoo read left to fail. The guard that matters now is
    that the whole run never reaches the library — a fake ``yfinance`` whose ``Ticker`` raises would be hit by any
    read that came back.
    """
    import sys
    import revenuechaser.module_financials.run as fin_run
    from revenuechaser.core import universe as spine

    fake = type(sys)("yfinance")
    fake.Ticker = lambda ticker: _Boom(ticker)
    monkeypatch.setitem(sys.modules, "yfinance", fake)

    monkeypatch.setattr(fin_run, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(fin_run.market_inputs, "overlay", lambda ticker, fin: (fin, "not stored (price)"))
    monkeypatch.setattr(fin_run, "_sec_statements", lambda ticker: (None, {"entity_name": "Apple Inc."}))
    monkeypatch.setattr(fin_run, "_stored_risk_free", lambda: None)
    monkeypatch.setattr(spine, "spine_gics", lambda tickers: {})
    monkeypatch.setattr(fin_run, "picker_payload", lambda ticker: {})

    with yfinance_client.health_scope() as health:
        out = fin_run.run("AAPL", modules=["dcf"], output="html")

    assert health.health()["calls"] == 0, "the Financials board must cost no provider call"
    assert "provider_health" not in out["results"]
    html = (tmp_path / "AAPL_report.html").read_text(encoding="utf-8")
    assert "Yahoo Finance" not in html
    # And the no-data state is what the board shows instead of a model (avo's option B of 10 Nov 2026).
    assert out["results"]["modules"] == {}
    assert fin_run.NO_SEC_DATA in html and "Apple Inc." in html
