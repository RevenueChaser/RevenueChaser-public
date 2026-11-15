"""LEAPS board -> result history (#377, A3). Offline; the store is a temp DuckDB.

A LEAPS Fetch records every watchlist footprint through ``core/history.record_run``: one ``result_runs`` header plus
one ``leaps_footprint_history`` row per watchlist ticker, whatever its label, with ``fetch_status`` and the inputs it
was classified from. LEAPS is a session board: the first complete, whole run of a session keeps its rows; a later,
intraday or partial run keeps its header only.
"""
from __future__ import annotations

import json
import zlib
from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core import ledger, rawstore
from RevenueChaser.core.providers.result import ProviderResult
from RevenueChaser.core.providers.unusual_whales import UWClient
from RevenueChaser.module_leaps import engine
from RevenueChaser.module_leaps.scan import scan_leaps

TODAY = date(2026, 10, 6)
# 2026-10-06 is a Tuesday: 22:00 UTC = 18:00 ET (session complete); 14:00 UTC = 10:00 ET (intraday).
COMPLETE = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc).timestamp()
INTRADAY = datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc).timestamp()
FAR = "2027-12-17"                       # > 270 days after TODAY


class _UW:
    """A UW double: far-dated OI per ticker, no tape, a failure counter the scan reads per ticker."""
    auth_error = None

    def __init__(self, oi: dict, fail: set = frozenset(), raise_for: set = frozenset()):
        self.oi, self.fail, self.raise_for = oi, set(fail), set(raise_for)
        self.calls = self.failed = 0

    def health(self):
        return {"calls": self.calls, "failed": self.failed, "auth_error": None, "failures": [],
                "breaker_open": False, "skipped_calls": 0}

    def option_trades(self, **kw):
        return []

    def screener_batch(self, tickers):
        return {t: {"full_name": f"{t} Inc"} for t in tickers}

    def oi_per_expiry(self, ticker, date=None):
        self.calls += 1
        if ticker in self.raise_for:
            raise RuntimeError("socket closed")
        if ticker in self.fail:
            self.failed += 1
            return []
        call, put = self.oi.get(ticker, (0, 0))
        return [{"expiry": FAR, "call_oi": call, "put_oi": put}]

    def flow_per_expiry(self, ticker):
        self.calls += 1
        return []

    def iv_rank(self, ticker):
        self.calls += 1
        return [{"iv_rank_1y": "55.0"}]

    # The real client's ``*_result`` reads (the scan reads through them); this double fails only by its counter.
    def oi_per_expiry_result(self, ticker, date=None):
        return ProviderResult("ok", self.oi_per_expiry(ticker, date))

    def flow_per_expiry_result(self, ticker):
        return ProviderResult("ok", self.flow_per_expiry(ticker))

    def iv_rank_result(self, ticker):
        return ProviderResult("ok", self.iv_rank(ticker))


class _Resp:
    def __init__(self, status: int, payload=None):
        self.status_code, self._payload, self.text, self.headers = status, payload or {"data": []}, "", {}

    def json(self):
        return self._payload


def _real_uw(bbb_status: int) -> UWClient:
    """The real UW client, offline: AAA answers far-dated OI, BBB's oi-per-expiry answers ``bbb_status``."""
    c = UWClient(key="k", sleep=lambda s: None)

    def _get(url, params=None):
        if "/stock/BBB/oi-per-expiry" in url:
            return _Resp(bbb_status, None if bbb_status == 200 else {"message": "not found"})
        if "/oi-per-expiry" in url:
            return _Resp(200, {"data": [{"expiry": FAR, "call_oi": 1000, "put_oi": 200}]})
        return _Resp(200)

    c._client.get = _get  # type: ignore[method-assign]
    return c


@pytest.fixture
def store(rawstore_tmp_db):
    ledger.take_notes()
    rawstore.save_watchlist({"AAA", "BBB"})
    return rawstore_tmp_db


def _scan(uw, **kw):
    footprints: list = []
    watched, unwatched = scan_leaps(uw, today=TODAY, footprints=footprints, **kw)
    return footprints, watched, unwatched








def _unpack(cell):
    if isinstance(cell, (bytes, bytearray)):
        return json.loads(zlib.decompress(cell))
    return cell if not isinstance(cell, str) else json.loads(cell)


# ── the scan's footprint sink ──





def test_a_ticker_whose_uw_call_failed_is_provider_failed(store):
    footprints, _, _ = _scan(_UW({"AAA": (1000, 200)}, fail={"BBB"}))
    status = {f["ticker"]: f["fetch_status"] for f in footprints}
    assert status == {"AAA": "ok", "BBB": "provider_failed"}






def test_an_ok_read_with_empty_data_stays_ok(store):
    footprints, _, _ = _scan(_real_uw(200))                 # BBB: 200 with no rows is real, empty data
    assert {f["ticker"]: f["fetch_status"] for f in footprints} == {"AAA": "ok", "BBB": "ok"}


def test_a_ticker_whose_fetch_raised_is_kept_with_its_error(store, monkeypatch):
    real = engine.fetch_and_classify

    def boom(ticker, uw, today=None, inputs=None, near_term_event=False, **kw):
        if ticker == "BBB":
            raise ValueError("bad payload")
        return real(ticker, uw, today=today, inputs=inputs, near_term_event=near_term_event, **kw)

    monkeypatch.setattr(engine, "fetch_and_classify", boom)
    footprints, _, _ = _scan(_UW({"AAA": (1000, 200)}))
    (bbb,) = [f for f in footprints if f["ticker"] == "BBB"]
    assert bbb["snapshot"] is None and bbb["fetch_status"] == "error: ValueError"


def test_a_scan_without_the_sink_is_unchanged(store):
    watched, unwatched = scan_leaps(_UW({"AAA": (1000, 200)}), today=TODAY)
    assert [w["ticker"] for w in watched] == ["AAA", "BBB"] and unwatched == []   # the sink is optional (#377 L2)


# ── the record ──























