"""#297 (D12): the Earnings pipeline keeps the UW statements it reads for R3/R7 and stores them through the run's
vendor capture. One ``/stock/{t}/financials`` request per ticker, as before. Offline fake UW, temp store."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_earnings_radar.pipeline import EarningsPipeline
from RevenueChaser.module_earnings_radar.tests.test_pipeline_score import _FakeUW

COMPLETE = datetime(2026, 10, 8, 20, 35, tzinfo=timezone.utc).timestamp()
_SCREENER = {"AAPL": {"close": "10", "call_volume": "0", "put_volume": "0", "total_open_interest": "0"}}
_CAL = {"AAPL": {"earnings_date": "2026-08-14", "full_name": "Aple", "sector": "Technology",
                 "expected_move_perc": 0.05}}




class _FinUW(_FakeUW):
    """A fake that serves ``financials`` like UWClient and maps it with the real ``_map_financials``."""


    def financials(self, ticker):
        self.fin_calls.append(ticker)
        return self.fin

    def _map_financials(self, ticker, fin=None):
        from RevenueChaser.core.providers.unusual_whales import UWClient
        self.mapped.append(fin)
        return UWClient._map_financials(self, ticker, fin=fin)

    @staticmethod
    def _num(row, *keys):
        from RevenueChaser.core.providers.unusual_whales import UWClient
        return UWClient._num(row, *keys)


def _pipeline(uw):
    p = EarningsPipeline(["AAPL"], uw=uw, cal_meta=_CAL)
    p._screener_cache = _SCREENER
    p._dgs10_cache = {}
    return p








def test_a_capture_failure_leaves_r3_r7_as_they_were(monkeypatch):
    # The store side never changes the score: the map runs first, the capture has its own try (review N4).
    import RevenueChaser.module_earnings_radar.pipeline as pl
    seen = []
    real = pl._build_earnings_detail
    monkeypatch.setattr(pl, "_build_earnings_detail", lambda hist, recs: seen.append(recs) or real(hist, recs))
    uw = _FinUW()
    p = _pipeline(uw)

    def boom(*a, **k):
        raise RuntimeError("capture broke")

    monkeypatch.setattr(p.vendor, "add_uw", boom)
    assert p._score("AAPL") is not None
    assert seen and seen[0]                     # the mapped records reached the detail
