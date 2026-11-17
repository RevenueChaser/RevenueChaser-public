"""PR 9 (G3): Sector Rotation reads its weekly closes from the prices store and its macro series from
``market_series`` (FRED, Cboe; MOVE and wheat from the new Yahoo source), with no call at Fetch time.

The RRG, the holdings RS and Money Flow read ``rcdata.read.ticker_bars`` (total-return basis since C1, 17 Nov 2026);
the macro series are ``rcdata.read.market_series`` rows shown in their own table, not on the map (B1). A Refresh and a
Fetch compute the same map offline. The old D01 tables are not read. Offline, temp stores.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from RevenueChaser.core import calendar, rawstore
from RevenueChaser.core.rotation_reference import MACRO_SERIES
from RevenueChaser.module_sector_rotation import engine, money_flow
from RevenueChaser.module_sector_rotation.tests.bars_seed import ny, pin_clock, sessions
from RevenueChaser.rcdata.tests import prices_store

SESSION = date(2026, 6, 30)
DAYS = sessions(date(2025, 3, 3), SESSION)


def _bars(ticker, step=0.001, start=100.0):
    """A drift plus a small wiggle of its own per ticker: a perfectly smooth line has no spread to scale by (A1)."""
    phase = sum(map(ord, ticker))
    return [{"ticker": ticker, "session_date": d, "volume": 1e6 + i,
             "close": start * (1 + step) ** i * (1 + 0.003 * math.sin(i / 9 + phase))}
            for i, d in enumerate(DAYS)]


@pytest.fixture
def world(monkeypatch):
    pin_clock(monkeypatch, ny(2026, 7, 1, 10))
    return monkeypatch


def test_the_rrg_reads_the_prices_store_not_d01(world):
    eng = engine.RotationEngine()
    assert eng.process_all() == []                                      # SPY only in the old D01: no map
    prices_store.put_bars(_bars("SPY") + _bars("XLK", 0.002) + _bars("XLE", -0.001), replace=False)
    snaps = {s.ticker: s for s in engine.RotationEngine().process_all()}
    assert {"XLK", "XLE"} <= set(snaps)
    assert snaps["XLK"].rs_1m > 0 > snaps["XLE"].rs_1m
    week_close = [b for b in _bars("XLK", 0.002) if b["session_date"] <= engine.week_cut(SESSION)][-1]["close"]
    assert snaps["XLK"].close_price == pytest.approx(week_close)          # the map's own week (A1), not the last bar


def test_a_split_is_applied_to_the_weekly_closes(world):
    xlk = [{"ticker": "XLK", "session_date": d, "close": 100.0, "volume": 1e6} for d in DAYS]
    ex = DAYS[-30]
    for r in xlk:
        if r["session_date"] >= ex:
            r["close"] = 50.0                                            # a 2-for-1: as traded, the price halves
    prices_store.put_bars(xlk)
    prices_store.put_action("XLK", ex, "split", 2.0)
    closes = [c for _, c in engine.bar_points(["XLK"], DAYS[0], SESSION)["XLK"]]
    assert closes == pytest.approx([50.0] * len(DAYS))


def test_the_macro_series_are_not_on_the_map(world):
    """B1 (avo 17 Nov 2026): a rate or an index level has no "beating SPY"; it goes to the macro table."""
    prices_store.put_bars(_bars("SPY") + _bars("XLK", 0.002))
    rows = [{"series_id": sid, "source": src, "obs_date": d, "value": 4.0 + i / 1000}
            for i, d in enumerate(DAYS) for sid, src in (v["series"] for v in MACRO_SERIES.values())]
    prices_store.put_series(rows)
    snaps = {s.ticker for s in engine.RotationEngine().process_all()}
    assert "XLK" in snaps and not snaps & set(MACRO_SERIES)


def test_the_macro_table_reads_market_series(world):
    series = {ticker: info["series"] for ticker, info in MACRO_SERIES.items()}
    assert series["US10Y"] == ("DGS10", "fred") and series["VVIX"] == ("VVIX", "cboe")
    assert series["MOVE"] == ("MOVE", "yahoo") and series["HY_OAS"] == ("BAMLH0A0HYM2", "fred")
    rows = [{"series_id": "DGS10", "source": "fred", "obs_date": d, "value": 4.0 + i / 100} for i, d in enumerate(DAYS)]
    rows += [{"series_id": "VVIX", "source": "cboe", "obs_date": d, "value": 100.0 + i % 50} for i, d in enumerate(DAYS)]
    rows.append({"series_id": "DGS10", "source": "treasury", "obs_date": DAYS[-1], "value": 99.0})   # not FRED's
    prices_store.put_series(rows)
    table = {r["ticker"]: r for r in engine.macro_table(SESSION)}
    assert set(table) == {"US10Y", "VVIX"}
    ten = table["US10Y"]
    assert ten["block"] == "Rates" and ten["unit"] == "bp"
    assert ten["last"] == pytest.approx(4.0 + (len(DAYS) - 1) / 100)
    assert ten["chg_1w"] == pytest.approx(5.0) and ten["chg_13w"] == pytest.approx(63.0)
    assert ten["pct_1y"] == 100 and len(ten["spark"]) == 65
    assert table["VVIX"]["block"] == "Volatility" and table["VVIX"]["unit"] == "%"
    assert [r["ticker"] for r in engine.macro_table(SESSION)] == ["US10Y", "VVIX"]


def test_money_flow_reads_the_prices_store():
    prices_store.put_bars([{"ticker": "XLK", "session_date": d, "close": 10.0 + i, "volume": 5.0}
                           for i, d in enumerate(DAYS[-40:])])
    rows = money_flow.bar_rows(["XLK", "XLE"], SESSION, days=30)
    assert len(rows) == 30 and {r["ticker"] for r in rows} == {"XLK"}
    assert rows[-1] == {"ticker": "XLK", "date": SESSION.isoformat(), "close": 49.0, "volume": 5.0}


def test_the_stale_line_names_the_prices_store(world):
    short = [r for r in _bars("SPY") if r["session_date"] < SESSION]
    prices_store.put_bars(short + [r for r in _bars("XLK") if r["session_date"] < SESSION])
    eng = engine.RotationEngine()
    eng.process_all()
    assert eng.as_of == calendar.previous_trading_day(SESSION - timedelta(days=1))
    assert "prices store" in eng.stale and "D01" not in eng.stale
