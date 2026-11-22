"""#25 HR-2: the readability gate, the dirty list and the 90-day dedupe (``core/hit_rate.py``)."""
from __future__ import annotations

from datetime import date, timedelta

from revenuechaser.core import hit_rate, outcomes

D0 = date(2026, 1, 5)


def pick(subject, day=D0, *, mfe=0.12, status=outcomes.CLOSED, source="fundamentals", version="11+a"):
    return {"source": source, "subject": subject, "forecast_date": day, "model_version": version,
            "status": status, "mfe": mfe}


def test_the_same_name_within_90_days_counts_once_from_its_first_pick():
    rows = [pick("A", D0), pick("A", D0 + timedelta(days=30)), pick("A", D0 + timedelta(days=89)),
            pick("A", D0 + timedelta(days=90)), pick("B", D0 + timedelta(days=30))]
    kept = hit_rate.dedupe(rows)
    assert [(r["subject"], r["forecast_date"]) for r in kept] == [
        ("A", D0), ("B", D0 + timedelta(days=30)), ("A", D0 + timedelta(days=90))]


def test_two_boards_or_two_versions_are_never_deduped_against_each_other():
    rows = [pick("A"), pick("A", source="swing"), pick("A", version="12+b")]
    assert len(hit_rate.dedupe(rows)) == 3


def _many(n, dates):
    return [pick(f"T{i}", D0 + timedelta(days=i % dates), mfe=0.25 if i % 2 else 0.01) for i in range(n)]


def test_thirty_closed_records_over_three_dates_are_readable():
    line, = hit_rate.summary(_many(30, 3))
    assert line["readable"] and line["records"] == 30 and line["dates"] == 3
    assert line["ge20"] == 0.5 and line["ge10"] == 0.5 and line["ge5"] == 0.5


def test_too_few_records_or_too_few_dates_give_no_rate():
    assert not hit_rate.summary(_many(29, 3))[0]["readable"]
    two_days, = hit_rate.summary(_many(40, 2))
    assert not two_days["readable"] and two_days["ge10"] is None


def test_open_records_wait_and_dirty_ones_are_listed_not_counted():
    rows = _many(30, 3) + [pick("OPEN1", status=outcomes.OPEN, mfe=None),
                           pick("SPLIT", status=outcomes.SPLIT_CHECK, mfe=3.0),
                           pick("GONE", status=outcomes.NO_BARS, mfe=None)]
    line, = hit_rate.summary(rows)
    assert line["records"] == 30 and line["open"] == 1
    assert sorted(d["subject"] for d in line["dirty"]) == ["GONE", "SPLIT"]
    assert line["ge20"] == 0.5, "a split jump never inflates the rate"


def test_one_line_per_board_and_version():
    rows = _many(30, 3) + [pick("X", version="12+b")]
    assert [(line["source"], line["model_version"]) for line in hit_rate.summary(rows)] == [
        ("fundamentals", "11+a"), ("fundamentals", "12+b")]
