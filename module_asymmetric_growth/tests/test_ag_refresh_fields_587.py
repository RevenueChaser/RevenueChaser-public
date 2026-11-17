"""#587 live check (17 Nov 2026): a Refresh's cards carry ``fiscal_year`` and ``basis`` as the Fetch's did, read
from the columns the table keeps them under (``anchor_fy``, ``period_ends.basis``)."""
from __future__ import annotations

from RevenueChaser.core import ticker_store
from RevenueChaser.module_asymmetric_growth import engine
from RevenueChaser.module_asymmetric_growth.tests.test_score_ticker import _fin, _tech


def test_a_refresh_card_keeps_fiscal_year_and_basis(rawstore_tmp_db):
    card = engine.score_ticker("AAA", _fin(), _tech())
    assert card["fiscal_year"] is not None and card["basis"] in ("FY", "TTM")
    ticker_store.write_from_cards([card], asof="2026-11-17T00:00:00")
    back = engine.stored_result()["cards"][0]
    assert (back["fiscal_year"], back["basis"]) == (card["fiscal_year"], card["basis"])
