"""#582: the large universe's three views are 60 / 120 / 250 groups (measured on live data, avo's choice, 17 Nov 2026).

At ~5,100 names k20 left one group with a third of the names and the least lift over random groups; the out-of-sample
R² flattens above ~120, and 250 is the last level before groups of under four names pile up (see ``config.CUT_TIERS``).
"""
from RevenueChaser.module_comovement import config


def test_the_live_universe_gets_60_120_250():
    assert config.cuts_for(5123) == (60, 120, 250)
    assert config.cuts_for(2000) == (60, 120, 250)
    assert config.cuts_for(1999) == (10, 30, 80)
