"""E1 (#298, D13): the Earnings Fetch keeps the UW earnings rows it already reads in ``earnings_history``.

``_score`` reads ``/earnings/{t}`` (R4's tape and the drawer) and ``/stock/{t}/earnings`` (R2's EPS prints). The
scoring workers hand both answers to the run's capture; the runner flushes it once, after the run, so a worker never
writes. A print is appended only when its fields changed (change history, rule A); a daytime run appends a change
too. No request is added. Offline fake UW, temp store.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core import ledger, rawstore
from RevenueChaser.module_earnings_radar.pipeline import EarningsPipeline
from RevenueChaser.module_earnings_radar.tests.test_pipeline_score import _FakeUW

# Thu 2026-10-08: 20:35 UTC = 16:35 ET (session complete); 15:00 UTC = 11:00 ET (intraday).
COMPLETE = datetime(2026, 10, 8, 20, 35, tzinfo=timezone.utc).timestamp()
INTRADAY = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc).timestamp()

EARN = [  # /earnings/{t}, newest first: the upcoming event, then a past print
    {"report_date": "2026-10-29", "report_time": "postmarket", "actual_eps": None, "street_mean_est": "1.70",
     "expected_move_perc": "0.061", "post_earnings_move_1d": None, "ending_fiscal_quarter": "2026-09-30",
     "source": "company"},
    {"report_date": "2026-07-30", "report_time": "postmarket", "actual_eps": "1.64", "street_mean_est": "1.60",
     "expected_move_perc": "0.052", "post_earnings_move_1d": "-0.031", "ending_fiscal_quarter": "2026-06-30",
     "source": "company"},
]
STOCK = [  # /stock/{t}/earnings: statement-style prints
    {"ticker": "AAPL", "report_date": "2026-07-30", "report_time": "postmarket", "report_type": "quarterly",
     "reported_eps": "1.64", "estimated_eps": "1.60", "surprise_percentage": "2.5", "fiscal_date_ending": "2026-06-30",
     "inserted_at": "2026-07-31 12:00:00+00:00", "updated_at": "2026-07-31 12:00:00+00:00"},
    {"ticker": "AAPL", "report_date": None, "report_type": "quarterly", "reported_eps": None, "estimated_eps": "1.7",
     "fiscal_date_ending": "2026-09-30"},
]








# ── the mappers ──







# ── the writer: append on change ──



















# ── the pipeline: the workers capture, they never write ──

class _PrintsUW(_FakeUW):
    """A fake that serves both earnings reads like UWClient and counts them."""

    def __init__(self, earn=EARN, stock=STOCK, **ov):
        super().__init__(**ov)
        self.earn, self.stock, self.calls = earn, stock, []

    def earnings_rows(self, ticker):
        self.calls.append(("earnings_rows", ticker))
        return self.earn

    def stock_earnings(self, ticker):
        self.calls.append(("stock_earnings", ticker))
        return self.stock


_SCREENER = {"AAPL": {"close": "10", "call_volume": "0", "put_volume": "0", "total_open_interest": "0"}}
_CAL = {"AAPL": {"earnings_date": "2026-10-29", "full_name": "Aple", "sector": "Technology"}}


def _pipeline(uw):
    p = EarningsPipeline(["AAPL"], uw=uw, cal_meta=_CAL)
    p._screener_cache = _SCREENER
    p._dgs10_cache = {}
    return p






def test_a_capture_failure_leaves_the_card_as_it_was(monkeypatch):
    uw = _PrintsUW()
    want = _pipeline(uw)._score("AAPL")
    p = _pipeline(uw)

    def boom(*a, **k):
        raise RuntimeError("capture broke")

    monkeypatch.setattr(p.earnings_capture, "add", boom)
    got = p._score("AAPL")
    assert got is not None and got.ticker == want.ticker
    assert (got.r2_score, got.r4_score, got.direction_score) == (want.r2_score, want.r4_score, want.direction_score)
