"""``core.baselines`` (#25 HR-1) end to end: a run fills ``forecast_baselines`` from the store alone.

Kept apart from ``core/tests/test_baselines.py`` on purpose — a second, differently shaped fixture. That file's bars
put the MFE on the first window session with a pinned amplitude; here the amplitude and the MFE are both parameters
of the same builder, so a rule that only holds for one arrangement of bars fails in one of the two.

``forecast_baselines`` is derived and keyed on ``(forecast_date, horizon_days, basis)``; these tests check the number
a hit rate is compared against, not the writer's bookkeeping.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.core import baselines, calendar as cal, ledger, rawstore
from RevenueChaser.core.tests.d01_seed import write_d01

D = date(2026, 9, 1)                      # the freeze date (a Tuesday)
LAST_BAR = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc)     # 2026-10-09 is complete
TABLE = "forecast_baselines"


def _sessions(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if cal.is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def _series(ticker, *, mfe, mae=-0.02, amp=0.002, start=None, last=LAST_BAR):
    """Bars whose open is 10 every session, whose close oscillates by ``amp`` (the trailing-vol signal), and whose
    high/low after ``D`` are exactly ``10 * (1 + mfe)`` / ``10 * (1 + mae)`` — so the MFE and MAE an outcome computes
    are the arguments, whatever the amplitude."""
    rows = []
    for i, d in enumerate(_sessions(start or D - timedelta(days=40), last)):
        close = 10.0 * (1 + (amp if i % 2 else -amp))
        high = max(10.0 * (1 + (mfe if d > D else amp)), close)
        low = min(10.0 * (1 + (mae if d > D else -amp)), close)
        rows.append({"ticker": ticker, "session_date": d, "open": 10.0, "high": high, "low": low, "close": close,
                     "adj_close": None, "volume": 1000.0, "split_ratio": None, "adj_source": None,
                     "source": "yfinance", "fetched_at": 0.0, "run_id": "seed", "run_at": 0.0})
    return rows


@pytest.fixture
def clock(monkeypatch):
    """The universe is written an hour before ``D`` ended, so ``universe_at(D)`` finds it (the store stamps the wall
    clock, and these dates are in the past)."""
    ticks = [baselines.day_end(D) - 3600]
    monkeypatch.setattr(rawstore, "_change_clock", lambda: ticks.__setitem__(0, ticks[0] + 1) or ticks[0])
    return ticks


def _seed(series, *, universe=None):
    """The bars, the universe of those names, and one pick on ``D`` — the ledger is what names a date to score."""
    rows = [r for s in series for r in s]
    write_d01(rows)
    universe_store.put([{"ticker": t, "name": t, "market_cap": 1e9} for t in (universe or sorted({r["ticker"]
                                                                                              for r in rows}))])
    ledger.write_picks("swing", "Swing", [{"subject": series[0][0]["ticker"], "rank": 1}],
                       model_version="v1+abcd", forecast_date=D, run_id="freeze1")


def _row(basis="universe", horizon=30):
    got = rawstore.query(f"SELECT * FROM {TABLE} WHERE forecast_date = ? AND basis = ? AND horizon_days = ?",
                         [D, basis, horizon], db="forecast")
    assert len(got) == 1, f"{basis}/{horizon}: {got}"
    return got[0]


def test_a_baselines_run_populates_forecast_baselines(rawstore_tmp_db, clock):
    """The population test ``core/tests/test_db_persistence.py`` maps this table to: one run, rows in the store."""
    _seed([_series(f"N{i}", mfe=0.03 + 0.01 * i, amp=0.0005 * (i + 1)) for i in range(20)])
    out = baselines.run(now=NOW, run_id="r1")
    assert out["written"] == rawstore.count(TABLE) > 0
    assert [r["horizon_days"] for r in rawstore.query(f"SELECT horizon_days FROM {TABLE} WHERE basis = ? "
                                                      "ORDER BY horizon_days", ["universe"], db="forecast")] == \
        sorted(baselines.HORIZONS)






def test_a_run_writes_the_baselines_table_and_nothing_else(rawstore_tmp_db, clock, monkeypatch):
    """The baseline is derived from the ledger and the bars: it never rewrites either."""
    _seed([_series("A", mfe=0.10), _series("B", mfe=0.20)])
    written = []
    real = rawstore.write_rows
    monkeypatch.setattr(rawstore, "write_rows", lambda name, rows: written.append(name) or real(name, rows))
    baselines.run(now=NOW, run_id="r1")
    assert set(written) == {TABLE}
    assert rawstore.count("forecast_outcomes") == 0 and rawstore.count("forecast_ledger") == 1
