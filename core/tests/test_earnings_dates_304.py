"""#304: the cards' next earnings date comes from the stored D26 calendar, Yahoo's value only when the store has none."""
from __future__ import annotations

from datetime import date, datetime, timezone

from RevenueChaser.core import earnings_dates as ed
from RevenueChaser.core import screen_common as sc
from RevenueChaser.core.tests.test_screen_common_147 import Board

TODAY = date(2026, 10, 22)
YAHOO = 1_790_000_000.0


def _utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc)


def test_the_stored_date_is_noon_utc_of_that_day():
    assert _utc(ed.epoch(date(2026, 10, 28))) == datetime(2026, 10, 28, 12, tzinfo=timezone.utc)














def test_with_stored_date_overlays_a_copy_and_keeps_the_rest_of_the_quote():
    row = {"ticker": "AAA", "quote": {"earningsTimestampStart": YAHOO, "price": 5.0}}
    out = ed.with_stored_date(row, {"AAA": date(2026, 10, 28)})
    assert out["quote"]["earningsTimestampStart"] == ed.epoch(date(2026, 10, 28))
    assert out["quote"]["price"] == 5.0
    assert row["quote"]["earningsTimestampStart"] == YAHOO, "the universe row itself is never changed"


def test_a_ticker_the_store_has_no_date_for_keeps_yahoos_value():
    row = {"ticker": "ZZZ", "quote": {"earningsTimestampStart": YAHOO}}
    assert ed.with_stored_date(row, {"AAA": date(2026, 10, 28)}) is row


def test_a_row_without_a_quote_gets_one():
    assert ed.with_stored_date({"ticker": "AAA"}, {"AAA": date(2026, 10, 28)})["quote"] == {
        "earningsTimestampStart": ed.epoch(date(2026, 10, 28))}


def test_run_screen_scores_the_stored_date_and_leaves_the_other_rows_alone(monkeypatch):
    rows = [{"ticker": "A", "quote": {"earningsTimestampStart": YAHOO}},
            {"ticker": "B", "quote": {"earningsTimestampStart": YAHOO}}]
    b = Board(monkeypatch, rows=rows)
    monkeypatch.setattr(sc.earnings_dates, "stored_next_dates", lambda: {"A": date(2026, 10, 28)})
    seen = {}

    def compute_row(row, spy_df, no_fetch, spine, drops):
        seen[row["ticker"]] = row["quote"]["earningsTimestampStart"]
        return {"ticker": row["ticker"]}
    b.run(compute_row=compute_row)
    assert seen == {"A": ed.epoch(date(2026, 10, 28)), "B": YAHOO}
    assert rows[0]["quote"]["earningsTimestampStart"] == YAHOO




def test_run_screen_counts_the_names_that_score_the_stored_date(monkeypatch):
    rows = [{"ticker": t, "quote": {"earningsTimestampStart": YAHOO}} for t in "ABC"]
    b = Board(monkeypatch, rows=rows)
    monkeypatch.setattr(sc.earnings_dates, "stored_next_dates",
                        lambda: {"A": date(2026, 10, 28), "C": date(2026, 11, 2), "ZZZ": date(2026, 11, 3)})
    b.run()
    assert b.stats["earnings_stored"] == 2
