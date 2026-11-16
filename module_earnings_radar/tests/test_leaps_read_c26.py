"""Earnings and LEAPS (C26, #383; #746): the card carries no LEAPS label while the opened share is untested.

The drawer still draws a label's ``as_of`` and age when a card has one, so those stay tested. Offline: fake UW.
"""
from datetime import date

import pytest

from RevenueChaser.module_earnings_radar.models import TradeCard
from RevenueChaser.module_earnings_radar import pipeline as pl
from RevenueChaser.module_earnings_radar.pipeline import EarningsPipeline
from RevenueChaser.module_earnings_radar.report import export_html
from RevenueChaser.module_earnings_radar.tests.test_pipeline_score import _FakeUW


@pytest.fixture(autouse=True)
def _isolate(rawstore_tmp_db):
    return rawstore_tmp_db


class _LeapsUW(_FakeUW):
    """Fake UW that records every LEAPS read the pipeline makes."""

    def __init__(self, **ov):
        super().__init__(**ov)
        self.leaps_calls = []

    def oi_per_expiry(self, ticker):
        self.leaps_calls.append(("oi_per_expiry", ticker))
        return []

    def flow_per_expiry(self, ticker):
        self.leaps_calls.append(("flow_per_expiry", ticker))
        return []

    def iv_rank(self, ticker):
        self.leaps_calls.append(("iv_rank", ticker))
        return []


def _pipeline(uw):
    p = EarningsPipeline(["AAPL"], uw=uw, cal_meta={"AAPL": {
        "earnings_date": "2026-08-14", "full_name": "Aple", "sector": "Technology",
        "expected_move_perc": 0.05}})
    p._screener_cache = {"AAPL": {"close": "100", "call_volume": "5000",
                                  "put_volume": "5000", "total_open_interest": "50000"}}
    return p


def test_a_card_carries_no_leaps_label_and_makes_no_leaps_call():
    """#746: Earnings reads no LEAPS label until the opened share is tested; nothing is fetched or guessed."""
    uw = _LeapsUW()
    card = _pipeline(uw)._score("AAPL")
    assert card.leaps_label == "N/A" and card.leaps_as_of == ""
    assert card.leaps_score is None
    assert card.leaps_far_call_oi is None and card.leaps_far_put_oi is None     # unknown, never a 0 (#730 item 3)
    assert uw.leaps_calls == []


def test_the_pipeline_no_longer_imports_the_old_leaps_engine():
    import inspect
    assert "module_leaps" not in inspect.getsource(pl)


def test_the_drawer_carries_the_as_of_and_age():
    card = TradeCard(ticker="AAPL", name="Apple", cluster="Technology",
                     earnings_date=date(2026, 8, 11), leaps_label="Accumulating",
                     leaps_as_of="2026-10-10")
    content = export_html([card], [], {}).read_text(encoding="utf-8")
    assert '"leaps_as_of": "2026-10-10"' in content
    expected = (date.today() - date(2026, 10, 10)).days
    assert f'"leaps_age_days": {expected}' in content


def test_a_card_without_an_as_of_shows_the_label_alone():
    card = TradeCard(ticker="AAPL", name="Apple", cluster="Technology",
                     earnings_date=date(2026, 8, 11), leaps_label="Accumulating")
    content = export_html([card], [], {}).read_text(encoding="utf-8")
    assert '"leaps_as_of": ""' in content
    assert '"leaps_age_days": null' in content
