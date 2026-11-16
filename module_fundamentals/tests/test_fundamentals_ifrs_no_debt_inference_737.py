"""#737, avo 16 Nov 2026 ("hepsine onerdigin gibi", Q2): no debt-free inference for an IFRS filer.

The facts layer maps an IFRS filer's statements onto us-gaap fields but maps no debt line and no finance cost
(``rcdata/build/fundamentals/facts.py`` ``IFRS_AS_GAAP``). So "no debt tag, no interest" is what every IFRS
borrower looks like, and BP, UL, RELX and WPP were read debt-free on the live board (WPP ROIC 379 %). Until the
tags are mapped, such a filer's debt stays unknown: the layer's meta says ``us_gaap`` False and the pipeline
passes ``infer_debt_free=False``.
"""
from __future__ import annotations

from RevenueChaser.core import fundamentals_layer as layer
from RevenueChaser.module_fundamentals import pipeline
from RevenueChaser.module_fundamentals.tests.test_fundamentals_debt_free_737 import _ttm_pair, _year


def test_an_ifrs_filer_with_no_debt_tag_stays_unknown():
    q = pipeline._quality_metrics(_year(), infer_debt_free=False)
    assert q["debt_basis"] is None and q["net_debt_ebitda"] is None and q["net_cash"] is None


def test_an_ifrs_filer_trailing_year_stays_unknown_too():
    annual, quarterly = _ttm_pair()
    q = pipeline._quality_metrics(annual, quarterly, infer_debt_free=False)
    assert q["debt_basis"] is None and q["net_debt_ebitda"] is None


def test_the_layer_meta_carries_us_gaap():
    assert layer._meta({"us_gaap": False}, True, [])["us_gaap"] is False
    assert layer._meta({"us_gaap": True}, True, [])["us_gaap"] is True
    assert layer._meta({}, True, [])["us_gaap"] is None

