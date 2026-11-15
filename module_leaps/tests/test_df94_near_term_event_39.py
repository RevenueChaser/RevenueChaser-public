"""DF94 (#39): a pinned name's near-event flag comes from the stored earnings calendar, not only from a flow print.

Red-first for the five behaviours:
1. a watchlist ticker with no far-dated print and earnings within ``NEAR_EVENT_DAYS`` is a near event, so Quiet;
2. the same ticker with earnings beyond the window keeps the label its footprint earns;
3. a flow candidate keeps its own near-event flag, whether the calendar has no row or a later one;
4. the window is inclusive at exactly ``NEAR_EVENT_DAYS`` days, and excludes the next day;
5. the Refresh (cached path) keeps the recorded flag and never consults today's calendar.
"""
from datetime import date, timedelta

import pytest

from RevenueChaser.core import earnings_dates
from RevenueChaser.core import rawstore
from RevenueChaser.core.providers.result import ProviderResult
from RevenueChaser.module_leaps import engine
from RevenueChaser.module_leaps.scan import scan_leaps, scan_leaps_cached
from RevenueChaser.module_leaps.tests.test_leaps_l3 import run_at_of

TODAY = date(2026, 10, 6)
FAR = "2027-12-17"                       # > 270 days after TODAY
GROWING = (1000, 200)                    # today's far-dated OI, against the seeded 500/0 session


class _UW:
    """A UW double: far-dated OI per ticker, one tape page, names from the screener."""
    auth_error = None

    def __init__(self, oi, tape=()):
        self.oi, self.tape = oi, list(tape)
        self.calls = self.failed = 0

    def health(self):
        return {"calls": self.calls, "failed": self.failed, "auth_error": None, "failures": [],
                "breaker_open": False, "skipped_calls": 0}

    def option_trades(self, **kw):
        return list(self.tape)

    def screener_batch(self, tickers):
        return {t: {"full_name": f"{t} Inc"} for t in tickers}

    def oi_per_expiry(self, ticker, date=None):
        self.calls += 1
        call, put = self.oi.get(ticker, (0, 0))
        return [{"expiry": FAR, "call_oi": call, "put_oi": put}]

    def flow_per_expiry(self, ticker):
        self.calls += 1
        return []

    def iv_rank(self, ticker):
        self.calls += 1
        return [{"iv_rank_1y": "55.0"}]

    def oi_per_expiry_result(self, ticker, date=None):
        return ProviderResult("ok", self.oi_per_expiry(ticker, date))

    def flow_per_expiry_result(self, ticker):
        return ProviderResult("ok", self.flow_per_expiry(ticker))

    def iv_rank_result(self, ticker):
        return ProviderResult("ok", self.iv_rank(ticker))


def _print(pid, ticker, ned=None):
    return {"id": pid, "underlying_symbol": ticker, "strike": "200", "expiry": "2027-06-18",
            "premium": "200000", "size": 10, "option_type": "call", "delta": "0.8",
            "next_earnings_date": ned, "executed_at": f"{TODAY.isoformat()}T14:00:00Z",
            "ask_vol": 10, "bid_vol": 2, "tags": []}


def _calendar(monkeypatch, dates=None, calls=None):
    """The stored calendar as a fake: ``dates`` as returned, every call counted."""
    def read(today=None):
        if calls is not None:
            calls.append(today)
        return dict(dates or {})
    monkeypatch.setattr(earnings_dates, "stored_next_dates", read)




# ── 1. the pinned name's own calendar date is the near event ──



# ── 2. beyond the window the footprint's own label stands ──



# ── 3. a flow candidate keeps the flag it has when the calendar has no row ──





# ── 4. the window is inclusive at exactly NEAR_EVENT_DAYS ──

def test_the_near_event_window_is_inclusive_at_the_constant(rawstore_tmp_db, monkeypatch):
    far_out = TODAY + timedelta(days=engine.NEAR_EVENT_DAYS + 1)
    _calendar(monkeypatch, {"AAA": TODAY + timedelta(days=engine.NEAR_EVENT_DAYS), "BBB": far_out})
    rawstore.save_watchlist({"AAA", "BBB"})
    watched, _ = scan_leaps(_UW({"AAA": (0, 0), "BBB": (0, 0)}), today=TODAY)
    flags = {w["ticker"]: w["near_term_event"] for w in watched}
    assert flags == {"AAA": True, "BBB": False}


# ── 5. the Refresh keeps the recorded flag, whatever today's calendar says ──





# ── 6. a calendar that cannot be read never fails the scan, and says so once ──

def _raise_read(today=None):
    raise RuntimeError("no such table: earnings_calendar")




# ── 7. the cached path stays store-only ──

def test_the_cached_path_makes_no_network_call_and_no_calendar_read(rawstore_tmp_db, monkeypatch):
    from RevenueChaser.core.providers import unusual_whales as uw_mod

    def _network(*a, **k):
        raise AssertionError("the cached path opened a network call")

    monkeypatch.setattr(uw_mod.UWClient, "option_trades", _network)
    monkeypatch.setattr(uw_mod.UWClient, "screener_batch", _network)
    monkeypatch.setattr(earnings_dates, "stored_next_dates", _network)

    engine.save_cache("AAA", {"ticker": "AAA", "label": "Quiet", "score": 5, "as_of": "2026-10-05",
                              "near_term_event": False})
    rawstore.save_watchlist({"AAA"})
    watched, unwatched = scan_leaps_cached(today=TODAY)
    assert [w["ticker"] for w in watched] == ["AAA"] and unwatched == []
    assert rawstore.load_watchlist() == {"AAA"}
