"""Small/Micro Cap engine tests (synthetic data, no network)."""
from __future__ import annotations

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.core.identity.sources import SourceResult
from RevenueChaser.module_asymmetric_growth import engine as agh




def _financials(country="United States", exchange="NMS") -> dict:
    return {
        "ticker": "TEST",
        "sector": "Healthcare",
        "info": {
            "country": country, "exchange": exchange,
            "industry": "Biotechnology", "longName": "Test Bio Corp",
        },
        "market_cap": 500_000_000.0,
        "current_price": 20.0,
        "annual": [
            {"fiscal_year": "2022", "revenue": 100.0, "gross_profit": 50.0,
             "operating_cash_flow": 30.0, "capex": 10.0,
             "total_debt": 5.0, "cash": 5.0, "total_assets": 200.0,
             "rd_expense": 25.0, "diluted_shares": 100.0},
            {"fiscal_year": "2023", "revenue": 123.0, "gross_profit": 61.5,
             "operating_cash_flow": 40.0, "capex": 10.0,
             "total_debt": 5.0, "cash": 5.0, "total_assets": 220.0,
             "rd_expense": 31.0, "diluted_shares": 100.0},
            {"fiscal_year": "2024", "revenue": 160.0, "gross_profit": 80.0,
             "operating_cash_flow": 50.0, "capex": 10.0,
             "total_debt": 5.0, "cash": 5.0, "total_assets": 250.0,
             "rd_expense": 40.0, "diluted_shares": 100.0},
        ],
    }


def _technical_pass() -> dict:
    return {"dist_52w_pct": 0.005, "vol_ratio": 1.8, "above_sma50": True, "price": 20.0}


def _technical_fail() -> dict:
    return {"dist_52w_pct": 0.05, "vol_ratio": 1.1, "above_sma50": False, "price": 18.0}


def test_full_pass():
    c = agh.score_ticker("TEST", _financials(), _technical_pass())
    assert c is not None
    assert c["total_points"] == 9
    assert c["tech_breakthrough"] is True
    assert c["themes"] == []          # C21 (#383): no pinned medium theme → no label; the points above are the proof
                                      # that dropping the keyword guess moved no signal
    assert c["dilution_warning"] is False


def test_non_us_excluded():
    c = agh.score_ticker("TEST", _financials(country="Canada", exchange="TSE"), _technical_pass())
    assert c is None


def test_partial_points():
    c = agh.score_ticker("TEST", _financials(), _technical_fail())
    assert c is not None
    # growth 3/3, survival 3/3, momentum 1/3 (dist 5% <= 10% geÃ§er) -> total 7
    assert c["total_points"] == 7


def test_institutional():
    totals = {
        "TEST": {
            "2026-03-31": {"holders": 875, "new_holders": 117, "exited_holders": 191,
                           "buy_flow": 80e6, "sell_flow": 92e6},
            "2025-12-31": {"holders": 900, "new_holders": 10, "exited_holders": 20,
                           "buy_flow": 10e6, "sell_flow": 5e6},
        }
    }
    inst = agh._institutional("TEST", totals)
    assert inst["inst_holders"] == 875
    assert inst["inst_new"] == 117
    assert inst["inst_exited"] == 191
    assert inst["inst_buy_flow"] == 80e6
    # bilinmeyen ticker -> None
    missing = agh._institutional("NOPE", totals)
    assert missing["inst_holders"] is None


def test_points_bucket():
    assert agh._points_bucket(9) == "pts_9"
    assert agh._points_bucket(8) == "pts_8_7"
    assert agh._points_bucket(7) == "pts_8_7"
    assert agh._points_bucket(6) == "pts_6_5"
    assert agh._points_bucket(5) == "pts_6_5"
    assert agh._points_bucket(4) == "pts_lt5"


def test_dilution_warning():
    fin = _financials()
    fin["annual"][-1]["diluted_shares"] = 200.0  # +100% YoY
    c = agh.score_ticker("TEST", fin, _technical_pass())
    assert c["dilution_warning"] is True
    assert c["dilution_yoy"] == 1.0


def test_runway_fcf_negative():
    fin = _financials()
    # FCF negatif: ocf 10 - capex 25 = -15; cash 5 -> runway = 5/15 = 0.33y (fail)
    fin["annual"][-1]["operating_cash_flow"] = 10.0
    fin["annual"][-1]["capex"] = 25.0
    c = agh.score_ticker("TEST", fin, _technical_pass())
    runway_sub = c["signals"][1]["subs"][2]
    assert runway_sub["passed"] is False
    assert abs(c["runway_years"] - 5 / 15) < 1e-9








# ── Universe membership = the SEC exchange file (#264) ────────────────────────

def _sec_rows(*pairs):
    """``[(ticker, exchange), ...]`` as the SEC map adapter returns them (name ``"<T> Inc (SEC)"``)."""
    return [{"ticker": t, "cik": str(1000 + i), "name": f"{t} Inc (SEC)", "exchange": ex}
            for i, (t, ex) in enumerate(pairs)]






def _screen_quotes(monkeypatch, quotes):
    """Fake ``yf.screen`` paging over ``quotes``; the returned list records each call."""
    import yfinance as yf
    calls: list[int] = []

    def fake_screen(query, offset=None, size=None, **kw):
        calls.append(1)
        start = offset or 0
        return {"total": len(quotes), "quotes": quotes[start:start + size]}

    monkeypatch.setattr(yf, "screen", fake_screen)
    return calls
































def test_technical_from_quote():
    q = {"regularMarketPrice": 10.0, "fiftyTwoWeekHigh": 10.1, "fiftyDayAverage": 9.0,
         "averageDailyVolume10Day": 1000, "averageDailyVolume3Month": 500}
    t = agh.technical_from_quote(q)
    assert abs(t["dist_52w_pct"] - 0.1 / 10.1) < 1e-9
    assert t["vol_ratio"] == 2.0
    assert t["above_sma50"] is True


def test_render_dashboard_universe_provenance():
    from RevenueChaser.module_asymmetric_growth.report import render_asymmetric_growth_hunter_html
    result = {
        "asof": "2026-08-23T00:00:00",
        "universe_total": 1,
        "universe_refreshed_by": "Asymmetric Growth",
        "universe_generated_at": "2026-08-24T10:00:00+00:00",
        "summary": {"scanned": 0, "pts_9": 0, "pts_8_7": 0, "pts_6_5": 0, "pts_lt5": 0,
                    "disruptive_themed": 0, "tech_breakthrough": 0},
        "thresholds": {
            "rev_growth": 0.2, "gross_margin": 0.4, "net_debt_assets": 0.1, "runway": 2.0,
            "dist_52w": 0.1, "vol_ratio": 1.4, "rd_intensity": 0.15, "dilution": 0.2,
            "accelerating": True, "fcf": True, "above_sma50": True,
        },
        "cards": [],
    }
    html = render_asymmetric_growth_hunter_html(result)
    assert "Universe refreshed by" in html
    assert "Asymmetric Growth" in html


# ── Universe Phase B (market-cap backfill) — docs/data_health.md ──────────────

class _FakeFastInfo:
    """Minimal ``fast_info`` stand-in; market_cap must never be touched."""

    def __init__(self, shares, last_price):
        self.shares = shares
        self.last_price = last_price

    @property
    def market_cap(self):
        raise AssertionError("fast_info.market_cap must not be read (falls back to .info)")


def _fake_ticker_factory(shares=1.35e9, last_price=925.57, calls=None):
    class _FakeTicker:
        def __init__(self, ticker):
            if calls is not None:
                calls.append(ticker)

        @property
        def fast_info(self):
            return _FakeFastInfo(shares, last_price)

        @property
        def info(self):
            raise AssertionError("Ticker.info must never be called")

    return _FakeTicker


def _one_quote(symbol="MU", **extra):
    q = {"symbol": symbol, "quoteType": "EQUITY", "exchange": "NMS", "currency": "USD",
         "regularMarketPrice": 925.57, "shortName": "Micron Technology, Inc."}
    q.update(extra)
    return q


def _screen_one(quote):
    def fake_screen(query, offset=None, size=None, **kw):
        start = offset or 0
        return {"total": 1, "quotes": [quote][start:start + size]}
    return fake_screen

































def test_render_uses_the_shared_filter_kit():
    """#383 C1c: the universal filters are the rc_filters bar, not the old Sector cascade / MC / EWEEK / INDEX controls."""
    from RevenueChaser.module_asymmetric_growth.report import render_asymmetric_growth_hunter_html
    result = {
        "asof": "", "summary": {}, "cards": [],
        "thresholds": {
            "rev_growth": 0.2, "gross_margin": 0.4, "net_debt_assets": 0.1, "runway": 2.0,
            "dist_52w": 0.1, "vol_ratio": 1.4, "rd_intensity": 0.15, "dilution": 0.2,
            "accelerating": True, "fcf": True, "above_sma50": True,
        },
    }
    html = render_asymmetric_growth_hunter_html(result)
    for frag in ('id="rc-filters"', "RCFilters.mount", 'data-pt="all"'):
        assert frag in html, f"missing shared filter fragment: {frag}"
    for gone in ("sectorOk(", "mcRange(", 'id="mc-tabs"', 'id="eweek-tabs"', 'id="index-tabs"',
                 'id="theme"', 'id="sector"', 'id="industry"',
                 'id="industry-group"', 'id="sub-industry"', "IGROUP", "ISUB",
                 "industry_group", "sub_industry"):
        assert gone not in html, f"the old filter markup is gone, found: {gone}"


# ── Phase B rate-limit survival — docs/data_health.md ─────────────────────────

def _failing_ticker_factory(behavior, shares=1e9, last_price=10.0):
    """Fake ``yf.Ticker`` whose construction can raise per ``behavior(ticker, idx)``.

    ``behavior`` returns an exception instance to raise on that ticker's ``idx``-th
    construction, or ``None`` to succeed. ``fast_info``/``info`` guards match the
    existing fakes so a stray ``.info`` / ``fast_info.market_cap`` read fails loudly.
    """
    calls = []

    class _FakeTicker:
        def __init__(self, ticker):
            idx = sum(1 for c in calls if c == ticker)
            calls.append(ticker)
            exc = behavior(ticker, idx)
            if exc is not None:
                raise exc

        @property
        def fast_info(self):
            return _FakeFastInfo(shares, last_price)

        @property
        def info(self):
            raise AssertionError("Ticker.info must never be called")

    return _FakeTicker, calls








