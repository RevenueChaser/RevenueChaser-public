"""M-OIPD-1 (#382, OIPD-3/OIPD-4): a failed breakdown or candle call is a known failure, not an empty answer.

- The expiry breakdown is read through ``expiry_breakdown_result``. A ``failed`` breakdown fails the run: nothing is
  saved to ``oipd_chain`` and no chain is pulled. Only an ``ok`` breakdown with no picks falls back to the default chain.
- The spot candle is read through ``ohlc_latest_result``. A failed candle is a warning and a history partial reason;
  the whole chain is still saved.

Offline: every client is a test double; the store is the per-test temp DuckDB.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from revenuechaser.core import ledger, rawstore
from revenuechaser.core.providers.result import ProviderResult
from revenuechaser.core.providers.unusual_whales import UWClient
from revenuechaser.module_oipd import engine
from revenuechaser.module_oipd.tests.test_engine import _SPOT, _FakeUW, fixed_today  # noqa: F401

COMPLETE = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc).timestamp()
_ERR = {"status": 503, "error": "HTTP 503", "attempts": 3}


class _ResultCallsUW(_FakeUW):
    """A client with the ``*_result`` twins, like ``UWClient``. Its plain methods answer what the real client's
    plain methods answer on a failure (``[]`` / ``{}``), so an engine that reads them sees an empty market."""

    def __init__(self, breakdown="ok", candle="ok"):
        super().__init__()
        self.breakdown, self.candle = breakdown, candle
        self.contract_expiries: list = []

    def expiry_breakdown(self, ticker, date=None):
        return [] if self.breakdown != "ok" else super().expiry_breakdown(ticker, date)

    def expiry_breakdown_result(self, ticker, date=None):
        self.calls["breakdown"] += 1
        if self.breakdown == "failed":
            return ProviderResult("failed", [], dict(_ERR), "/stock/TST/expiry-breakdown")
        if self.breakdown == "empty":
            return ProviderResult("ok", [], None, "/stock/TST/expiry-breakdown")
        rows = [{"expiry": e, "open_interest": 10000, "volume": 500, "chains": 50} for e in self.expiries]
        return ProviderResult("ok", rows, None, "/stock/TST/expiry-breakdown")

    def option_contracts(self, ticker, expiry=None, **kw):
        self.contract_expiries.append(expiry)
        return super().option_contracts(ticker, expiry=expiry, **kw)

    def ohlc_latest(self, ticker):
        return {} if self.candle != "ok" else super().ohlc_latest(ticker)

    def ohlc_latest_result(self, ticker):
        self.calls["ohlc"] += 1
        if self.candle == "failed":
            return ProviderResult("failed", {}, dict(_ERR), "/stock/TST/ohlc/1d")
        return ProviderResult("ok", {"close": _SPOT}, None, "/stock/TST/ohlc/1d")


@pytest.fixture
def store(rawstore_tmp_db, fixed_today):  # noqa: F811
    ledger.take_notes()
    return rawstore_tmp_db


def _stored():
    return rawstore.count("oipd_chain"), rawstore.get("oipd_meta", "TST")


def _fetch(uw):
    capture: dict = {}
    return engine.run(uw, "TST", capture=capture), capture




# ── the breakdown ────────────────────────────────────────────────────────────────────────

def test_a_failed_breakdown_fails_the_run_and_leaves_the_stored_chain_alone(store):
    engine.run(_FakeUW(), "TST")
    before = _stored()
    assert before[0] > 0

    uw = _ResultCallsUW(breakdown="failed")
    payload, capture = _fetch(uw)

    assert _stored() == before                                  # oipd_chain row count (and meta) unchanged
    assert payload["expiries"] == [] and payload["n_contracts"] == 0
    assert "Unusual Whales request failed" in payload["error"] and "HTTP 503" in payload["error"]
    assert "check the ticker" not in payload["error"]
    assert capture["status"] == "failed"
    assert capture["errors"] and capture["errors"][0]["status"] == 503
    assert uw.contract_expiries == []                           # no default chain after a failed breakdown


def test_a_failed_breakdown_on_an_empty_store_saves_nothing(store):
    payload, capture = _fetch(_ResultCallsUW(breakdown="failed"))
    assert rawstore.count("oipd_chain") == 0 and rawstore.get("oipd_meta", "TST") is None
    assert capture["status"] == "failed" and payload["error"]




def test_a_404_breakdown_is_a_missing_chain_not_an_outage_and_pulls_nothing(store):
    class _NotFound(_ResultCallsUW):
        def expiry_breakdown_result(self, ticker, date=None):
            return ProviderResult("failed", [], {"status": 404, "error": "HTTP 404"}, "")

    uw = _NotFound()
    payload, capture = _fetch(uw)
    assert uw.contract_expiries == []
    assert "check the ticker" in payload["error"] and "request failed" not in payload["error"]
    assert rawstore.count("oipd_chain") == 0


def test_an_ok_empty_breakdown_still_pulls_the_default_chain(store):
    uw = _ResultCallsUW(breakdown="empty")
    payload, capture = _fetch(uw)
    assert uw.contract_expiries == [None]                       # one default-chain pull, no expiry
    assert any("fetched the default chain" in w for w in payload["warnings"])
    assert payload["error"] is None and payload["expiries"]
    assert capture["status"] == "ok" and rawstore.count("oipd_chain") > 0


class _StrictUW(_ResultCallsUW):
    """The plain breakdown and candle methods must not be called when the ``*_result`` twins exist."""

    def expiry_breakdown(self, ticker, date=None):
        raise AssertionError("the engine read the plain expiry_breakdown")

    def ohlc_latest(self, ticker):
        raise AssertionError("the engine read the plain ohlc_latest")


def test_the_engine_reads_the_breakdown_and_the_candle_through_their_result_twins(store):
    uw = _StrictUW()
    payload, _ = _fetch(uw)
    assert uw.calls["breakdown"] == 1 and uw.calls["ohlc"] == 1
    assert len(payload["expiries"]) == 4 and payload["spot"] == _SPOT
    assert sorted(uw.contract_expiries) == uw.expiries          # one pull per picked expiry


# ── the spot candle ──────────────────────────────────────────────────────────────────────

def test_a_failed_candle_still_saves_the_whole_chain_with_a_warning(store):
    uw = _ResultCallsUW(candle="failed")
    payload, capture = _fetch(uw)
    assert uw.calls["ohlc"] == 1
    assert capture["status"] == "ok"                            # the chain itself is whole
    assert rawstore.count("oipd_chain") == len(capture["chain"]) > 0
    assert rawstore.get("oipd_meta", "TST")["spot"] is None
    assert payload["error"] is None and len(payload["expiries"]) == 4 and payload["spot"] is None
    text = " ".join(payload["warnings"])
    assert "spot price request failed" in text and "HTTP 503" in text








# ── the provider: ohlc_latest_result ─────────────────────────────────────────────────────

_BARS = {"data": [
    {"date": "2026-10-08", "market_time": "r", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
    {"date": "2026-10-09", "market_time": "r", "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 20},
    {"date": "2026-10-09", "market_time": "po", "open": 9, "high": 9, "low": 9, "close": 9.0, "volume": 1},
]}


def _client(answer):
    c = UWClient(key="k", sleep=lambda s: None)
    calls: list = []

    def fake(ep, params=None):
        calls.append((ep, dict(params or {})))
        return answer(ep, params)

    c.get_result = fake  # type: ignore[method-assign]
    return c, calls


def test_ohlc_latest_result_is_ok_with_the_bar_the_plain_method_returns():
    c, calls = _client(lambda ep, p=None: ProviderResult("ok", _BARS, None, ep))
    res = c.ohlc_latest_result("AAPL")
    assert isinstance(res, ProviderResult) and res.status == "ok" and res.error is None
    assert res.data["close"] == 2.5                             # the latest regular-session bar, not after-hours
    assert res.data == c.ohlc_latest("AAPL")
    assert calls[0] == calls[1] and calls[0][0] == "/stock/AAPL/ohlc/1d"


def test_ohlc_latest_result_is_failed_and_the_plain_method_keeps_its_empty_dict():
    def failed(ep, params=None):
        return ProviderResult("failed", {}, {"endpoint": ep, **_ERR}, ep)

    c, _ = _client(failed)
    res = c.ohlc_latest_result("AAPL")
    assert res.status == "failed" and res.error["status"] == 503 and res.data == {}
    assert c.ohlc_latest("AAPL") == {}


def test_ohlc_latest_result_with_no_bars_is_ok_and_empty():
    c, _ = _client(lambda ep, p=None: ProviderResult("ok", {"data": []}, None, ep))
    res = c.ohlc_latest_result("AAPL")
    assert res.status == "ok" and res.data == {}
