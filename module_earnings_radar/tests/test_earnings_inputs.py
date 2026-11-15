"""The Earnings inputs sweeps (E0, #372): D26, D37, D27, D10 and D14 against fake providers.

No request leaves the process: UW goes through a ``CappedUWClient`` whose transport is a dict of canned answers,
FRED and yfinance through monkeypatched provider functions.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.core.providers import unusual_whales

NY = ZoneInfo("America/New_York")
NIGHT = datetime(2026, 10, 13, 19, 30, tzinfo=NY).timestamp()        # session 2026-10-13, complete
SESSION = date(2026, 10, 13)
INTRADAY = datetime(2026, 10, 14, 11, 0, tzinfo=NY).timestamp()


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text, self.headers = status, body, "", {}

    def json(self):
        return self._body


class FakeUW:
    """The transport of a ``CappedUWClient``: ``routes`` maps an endpoint path to ``fn(params) -> (status, body)``."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None):
        path = url[len(unusual_whales.BASE):]
        self.calls.append((path, dict(params or {})))
        for prefix, fn in self.routes.items():
            if path == prefix or path.startswith(prefix.rstrip("*")) and prefix.endswith("*"):
                status, body = fn(params or {})
                return _Resp(status, body)
        return _Resp(404, {})

    def close(self):
        pass


# --- D26 earnings calendar (#304) -----------------------------------------------------------------------------------

def _cal_item(symbol, **kw):
    return {"symbol": symbol, "sector": "Technology", "full_name": f"{symbol} Inc", "marketcap": "1234567890",
            "expected_move_perc": "0.051", "street_mean_est": "1.23", "pre_earnings_close": None,
            "post_earnings_close": None, "report_time": "premarket", **kw}


def _calendar_routes(by_day=None):
    """One item per day and session unless ``by_day`` says otherwise."""
    def answer(session):
        def fn(params):
            d = params["date"]
            items = (by_day or {}).get((d, session))
            if items is None:
                items = [_cal_item(f"T{d[5:7]}{d[8:]}{session[0].upper()}")]
            if isinstance(items, int):
                return items, {}
            return 200, {"data": items}
        return fn
    return {"/earnings/premarket": answer("premarket"), "/earnings/afterhours": answer("afterhours")}


# --- D27 FRED macro series (#305, FRED part) ------------------------------------------------------------------------

class _FredResp:
    def __init__(self, obs, status=200):
        self._obs, self.status_code = obs, status

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            req = httpx.Request("GET", "https://fred.example/obs?api_key=SECRETKEY")
            raise httpx.HTTPStatusError("bad", request=req, response=httpx.Response(self.status_code, request=req))

    def json(self):
        return {"observations": self._obs}


@pytest.fixture
def fred(monkeypatch):
    from RevenueChaser.module_earnings_radar import macro_watch
    calls, fail = [], set()
    obs = [{"date": "2026-10-13", "value": "4.05"}, {"date": "2026-10-12", "value": "."},
           {"date": "2026-07-03", "value": "4.30"}]

    def get(url, params=None, timeout=None, **kwargs):
        calls.append(params["series_id"])
        return _FredResp([] if params["series_id"] in fail else obs, 500 if params["series_id"] in fail else 200)

    monkeypatch.setattr("httpx.get", get)
    monkeypatch.setattr(macro_watch, "FRED_API_KEY", "SECRETKEY")
    return calls, fail


def test_the_old_fred_daily_reader_still_swallows_a_failure(fred):
    from RevenueChaser.module_earnings_radar import macro_watch
    _, fail = fred
    fail.add("DGS10")
    assert macro_watch._fred_daily("DGS10") == []
    assert macro_watch._fred_daily("DGS5") == [("2026-07-03", 4.30), ("2026-10-13", 4.05)]


# --- D10 short interest (#296) --------------------------------------------------------------------------------------


def _seed_13f(tickers):
    """The served store, which is where the sweep reads its 13F ticker set since #515."""
    import duckdb

    from RevenueChaser.rcdata import serving

    path = serving.live_path("ownership")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE IF NOT EXISTS sec13f_ticker_period (ticker TEXT, period DATE, shares DOUBLE, "
                    "filing_deadline DATE)")
        con.executemany("INSERT INTO sec13f_ticker_period (ticker, period, shares, filing_deadline) VALUES (?,?,?,?)",
                        [[t, date(2026, 6, 30), 1.0, date(2026, 8, 14)] for t in tickers])
    finally:
        con.close()


def _si_item(symbol, **kw):
    return {"symbol": symbol, "market_date": "2026-09-30", "short_interest": 75000, "si_float": "0.017647058",
            "total_float": 4250000, "days_to_cover": "2.1", "fee_rate": "0.2782", "rebate_rate": "3.3518",
            "short_shares_available": 10000000, "si_float_with_synth_long_pct_of_total_shares": "0.0173", **kw}


def _si_routes(screener=(), interest=(), screener_status=200):
    def screen(params):
        if screener_status != 200:
            return screener_status, {}
        asked = params["tickers"].split(",")
        return 200, {"data": [_si_item(t) for t in asked if t in screener]}

    def per_ticker(path_ticker):
        return (200, {"data": _si_item(path_ticker)}) if path_ticker in interest else (404, {})

    routes = {"/short_screener": screen}
    for t in ("A", "B", "C", "X", "Y", "Z"):
        routes[f"/shorts/{t}/interest-float/v2"] = (lambda tt: (lambda params: per_ticker(tt)))(t)
    return routes


@pytest.fixture
def yf_info(monkeypatch):
    from RevenueChaser.core.providers import yfinance as yfp
    asked = []
    infos = {"B": {"shortPercentOfFloat": 0.05, "floatShares": 1_000_000, "sharesShort": 50_000}}

    def get_info(ticker):
        asked.append(ticker)
        return {"info": infos.get(ticker, {})}

    monkeypatch.setattr(yfp, "get_info", get_info)
    return asked


# --- D14 estimate snapshots (A6, #323) ------------------------------------------------------------------------------

def _trend_blocks(nan_avg=False, revisions_key="downLast7days"):
    """The four blocks exactly as yfinance's ``get_*(as_dict=True)`` gives them (``DataFrame.to_dict()``)."""
    import pandas as pd
    periods = ["0q", "+1q", "0y", "+1y"]
    ee = pd.DataFrame({"numberOfAnalysts": [30, 28, 40, 38], "avg": [float("nan") if nan_avg else 1.5, 1.6, 6.5, 7.2],
                       "low": [1.4, 1.5, 6.1, 6.6], "high": [1.7, 1.8, 7.0, 8.0], "yearAgoEps": [1.3, 1.4, 6.0, 6.5],
                       "growth": [0.15, 0.14, 0.08, 0.1], "currency": ["USD"] * 4}, index=periods)
    re_ = pd.DataFrame({"numberOfAnalysts": [25, 24, 35, 33], "avg": [9.1e10, 9.5e10, 3.9e11, 4.2e11],
                        "low": [9.0e10] * 4, "high": [9.3e10] * 4, "yearAgoRevenue": [8.5e10] * 4,
                        "growth": [0.07] * 4}, index=periods)
    et = pd.DataFrame({"current": [1.5, 1.6, 6.5, 7.2], "7daysAgo": [1.5] * 4, "30daysAgo": [1.49] * 4,
                       "60daysAgo": [1.48] * 4, "90daysAgo": [1.45] * 4}, index=periods)
    er = pd.DataFrame({"upLast7days": [2, 1, 3, 2], "upLast30days": [5, 4, 6, 5], revisions_key: [0, 0, 1, 0],
                       "downLast30days": [1, 1, 2, 1]}, index=periods)
    return {"earnings_estimate": ee.to_dict(), "revenue_estimate": re_.to_dict(), "eps_trend": et.to_dict(),
            "eps_revisions": er.to_dict()}


@pytest.fixture
def yf_trend(monkeypatch):
    from RevenueChaser.core.providers import yfinance as yfp
    from RevenueChaser.core.providers.result import ProviderResult
    asked, answers = [], {}

    def get(ticker):
        asked.append(ticker)
        a = answers.get(ticker, "ok")
        if a == "fail":
            return ProviderResult("failed", {}, {"error": "HTTPError", "attempts": 1}, ticker)
        return ProviderResult("ok", {} if a == "empty" else _trend_blocks(), None, ticker)

    monkeypatch.setattr(yfp, "get_earnings_trend", get)
    return asked, answers


def test_the_provider_reads_the_four_blocks_as_one_call(monkeypatch):
    import yfinance
    from RevenueChaser.core.providers import yfinance as yfp
    blocks = _trend_blocks()

    class T:
        def __init__(self, ticker):
            self.ticker = ticker

        def __getattr__(self, name):
            block = name[len("get_"):]
            return lambda as_dict=False: blocks[block]

    monkeypatch.setattr(yfinance, "Ticker", T)
    yfp.reset_health()
    res = yfp.get_earnings_trend("AAPL")
    assert res.status == "ok" and res.data == blocks and yfp.health()["calls"] == 1

    class Boom:
        def __init__(self, ticker):
            pass

        def get_earnings_estimate(self, as_dict=False):
            raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(yfinance, "Ticker", Boom)
    res = yfp.get_earnings_trend("AAPL")
    assert res.status == "failed" and yfp.health()["failed"] == 1


# --- the scheduled entries (#620) ---------------------------------------------------------------------------------

CAPS = ("--max-uw-calls", "unlimited", "--max-fred-calls", "12", "--max-yf-calls", "1000", "--max-cboe-calls", "20",
        "--max-cftc-calls", "5")


def _vol_csv() -> str:
    return "DATE,OPEN,HIGH,LOW,CLOSE\n10/13/2026,20.0,21.0,19.0,20.5\n"


def _cftc_row() -> dict:
    return {"report_date_as_yyyy_mm_dd": "2026-10-06T00:00:00.000", "open_interest_all": "2000000",
            "asset_mgr_positions_long": "500000", "asset_mgr_positions_short": "120000",
            "lev_money_positions_long": "300000", "lev_money_positions_short": "260000",
            "dealer_positions_long_all": "90000", "dealer_positions_short_all": "420000"}


