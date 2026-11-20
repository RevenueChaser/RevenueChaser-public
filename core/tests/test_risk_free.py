"""``core/risk_free``: the stored FRED 10-year yield as a rate, for every board that discounts with one.

One reader (#644): the yield lives in ``market_series`` as DGS10 in percent, and FRED publishes it a business day
late, so the rate of a session is the newest observation dated on or before it inside a window the caller sets.
"""
from __future__ import annotations

from datetime import datetime, timezone

from RevenueChaser.core import risk_free
from RevenueChaser.rcdata import ops, serving
from RevenueChaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401  (fixtures)


def _serve(points):
    with serving.build("market") as b:
        b.con.execute("CREATE TABLE market_series (series_id TEXT, obs_date DATE, source TEXT, value DOUBLE, "
                      "frequency TEXT, session_date DATE, source_as_of DATE, fetched_at DOUBLE, run_id TEXT)")
        for day, value, source in points:
            b.con.execute("INSERT INTO market_series VALUES ('DGS10', ?, ?, ?, 'daily', ?, ?, 1.0, 'r1')",
                          [day, source, value, day, day])
        b.swap({"market_series": len(points)})
    ops.record_check("market_series", "changed", run_id="r1")


def _clock(monkeypatch, when=datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)):
    from RevenueChaser.core import calendar
    monkeypatch.setattr(calendar, "_now", lambda: when)


def test_the_newest_observation_on_or_before_the_session_in_percent_divided_by_100(market_roots):  # noqa: F811
    _serve([("2026-11-17", 4.11, "fred"), ("2026-11-18", 4.13, "fred"), ("2026-11-19", 4.25, "fred")])
    assert risk_free.stored_dgs10("2026-11-18") == {"value": 0.0413, "as_of": "2026-11-18"}


def test_a_session_before_every_observation_reads_none(market_roots):  # noqa: F811
    _serve([("2026-11-18", 4.13, "fred")])
    assert risk_free.stored_dgs10("2026-11-17") is None


def test_an_observation_older_than_the_window_does_not_count(market_roots):  # noqa: F811
    _serve([("2026-11-01", 4.13, "fred")])
    assert risk_free.stored_dgs10("2026-11-20", 14) is None
    assert risk_free.stored_dgs10("2026-11-20", 30) == {"value": 0.0413, "as_of": "2026-11-01"}


def test_another_source_is_not_the_fred_yield(market_roots):  # noqa: F811
    _serve([("2026-11-18", 4.13, "yahoo")])
    assert risk_free.stored_dgs10("2026-11-18") is None


def test_no_session_means_today_in_new_york(monkeypatch, market_roots):  # noqa: F811
    _clock(monkeypatch)
    _serve([("2026-11-19", 4.25, "fred"), ("2026-11-30", 9.99, "fred")])    # a later day is never read
    assert risk_free.stored_dgs10() == {"value": 0.0425, "as_of": "2026-11-19"}


def test_without_a_market_file_there_is_no_rate(monkeypatch, market_roots):  # noqa: F811
    """``market_roots`` points the market dir at an empty temp root, so nothing is served."""
    _clock(monkeypatch)
    assert not (market_roots[0] / "market.duckdb").exists()
    assert risk_free.stored_dgs10() is None
