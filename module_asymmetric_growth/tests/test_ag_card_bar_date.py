"""Each Asymmetric Growth card says which session its price and momentum come from (AG review SF-1, PR 6).

The board says "data as of" the newest D01 session among its cards, but a name whose bars stop earlier (a halt, a
Daily Bars gap) was scored on its own older bars with nothing on the card to say so. Now the card carries its
own bar date (``period_ends["price_bar"]``, stored with the card) and a data check when that date is older than
the session the scan read up to; a card with no bars at all has no date and no check (its momentum is unknown).
"""
from __future__ import annotations

from RevenueChaser.rcdata.tests import fund_store
from RevenueChaser.core import ticker_store
from RevenueChaser.module_asymmetric_growth import engine, report
from RevenueChaser.module_asymmetric_growth.tests.test_ag_dated_momentum_380 import SESSION, edgar, row, sessions




def test_the_card_explains_the_check():
    src = report.__loader__.get_source(report.__name__)
    assert "price_bar_older:" in src and "pe.price_bar" in src
