"""#25 HR-2: dedupe, the readability gate and the dirty list of the hit rate (``core/hit_rate.py``)."""
from __future__ import annotations

from datetime import date, timedelta

from RevenueChaser.core import hit_rate


def _pick(subject, day, mfe=0.12, status="closed", version="v1", source="swing", horizon=30):
    return {"source": source, "subject": subject, "forecast_date": day, "horizon_days": horizon, "mfe": mfe,
            "mae": -0.05, "status": status, "model_version": version}


def _readable_set(n=30, dates=3, version="v1"):
    start = date(2026, 1, 5)
    return [_pick(f"T{i}", start + timedelta(days=i % dates), version=version) for i in range(n)]


def test_a_repeat_within_90_days_counts_once_and_the_earliest_is_kept():
    rows = [_pick("AAA", date(2026, 3, 1), mfe=0.30), _pick("AAA", date(2026, 1, 1), mfe=0.01),
            _pick("AAA", date(2026, 3, 31), mfe=0.5)]
    kept = hit_rate.dedupe(rows)
    assert [r["forecast_date"] for r in kept] == [date(2026, 1, 1), date(2026, 3, 31)]   # 89 days: dropped; 89+1: kept
    # Another family, version or horizon is its own count.
    assert len(hit_rate.dedupe(rows[:2] + [_pick("AAA", date(2026, 1, 2), source="fundamentals")])) == 2 + 1


def test_the_gate_needs_30_records_over_3_freeze_dates():
    assert hit_rate.summary(_readable_set())[0]["readable"] is True
    short = hit_rate.summary(_readable_set(n=29))[0]
    assert short["readable"] is False and short["ge10"] is None and short["n"] == 29
    assert hit_rate.summary(_readable_set(dates=2))[0]["readable"] is False


def test_the_rates_are_cumulative_shares_and_versions_never_pool():
    rows = _readable_set()
    rows[0]["mfe"] = 0.25
    rows[1]["mfe"] = 0.02
    s = hit_rate.summary(rows + _readable_set(n=5, version="v2"))
    v1 = next(r for r in s if r["model_version"] == "v1")
    assert (v1["ge20"], v1["ge10"], v1["ge5"]) == (1 / 30, 29 / 30, 29 / 30)
    assert next(r for r in s if r["model_version"] == "v2")["readable"] is False


def test_a_dirty_outcome_is_listed_not_counted():
    rows = _readable_set() + [_pick("BAD", date(2026, 1, 5), status="split_check"),
                              _pick("GONE", date(2026, 1, 6), status="no_bars", mfe=None),
                              _pick("OPEN", date(2026, 1, 7), status="open", mfe=None)]
    s = hit_rate.summary(rows)[0]
    assert (s["n"], s["dirty"], s["open"], s["dirty_subjects"]) == (30, 2, 1, ["BAD", "GONE"])
