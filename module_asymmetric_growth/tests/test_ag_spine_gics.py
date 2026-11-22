"""R5 (#88), #266: the Growth Hunter reads the spine's sector and industry and skips the identity master's excluded types."""
from __future__ import annotations

from revenuechaser.rcdata.tests import universe_store
from revenuechaser.core import rawstore
from revenuechaser.module_asymmetric_growth import engine
from revenuechaser.module_asymmetric_growth.tests.test_score_ticker import _fin, _tech


def _seed(rows, master=None):
    universe_store.replace([{
        "ticker": t, "cik": "", "name": t, "market_cap": 1e9, "price": 10.0,
        "sector": sec, "industry": ind, "quote": {"symbol": t}} for t, sec, ind in rows])
    if master:
        pass


def test_card_sector_and_industry_are_the_spine_not_yfinance(rawstore_tmp_db):
    _seed([("TEST", "Healthcare", "Biotechnology")])
    fin = _fin()
    fin["info"]["industry"] = "Software"                                       # the vendor says Software
    card = engine.score_ticker("TEST", fin, _tech(), {"sector": "Technology"})   # vendor says Technology
    assert card["sector"] == "Healthcare"
    assert card["industry"] == "Biotechnology"


def test_card_has_no_gics_group_or_sub_industry_keys(rawstore_tmp_db):
    _seed([("TEST", "Healthcare", "Biotechnology")])
    card = engine.score_ticker("TEST", _fin(), _tech())
    assert "industry_group" not in card and "sub_industry" not in card


def test_card_without_a_spine_row_is_unclassified(rawstore_tmp_db):
    _seed([("OTHR", "Energy", "Oil & Gas E&P")])
    card = engine.score_ticker("TEST", _fin(), _tech(), {"sector": "Technology"})
    assert (card["sector"], card["industry"]) == ("Unclassified", "Unclassified")


def test_card_with_a_blank_spine_industry_reads_unclassified(rawstore_tmp_db):
    _seed([("TEST", "Technology", "")])
    card = engine.score_ticker("TEST", _fin(), _tech())
    assert (card["sector"], card["industry"]) == ("Technology", "Unclassified")


def test_themes_are_the_pinned_run_never_the_vendor_industry_text(rawstore_tmp_db):
    """C21 (#383): the card's themes are the pinned medium labels; the vendor's free text no longer matches any."""
    _seed([("TEST", "Technology", "Software - Application")])
    rawstore.write_rows("theme_runs", [{"id": "r1", "created_at": "x", "k_fine": 1, "k_medium": 1,
                                        "k_coarse": 1, "jaccard": 1.0, "is_current": 1}])
    rawstore.write_rows("ticker_themes", [{"ticker": "TEST", "theme_id": "r1:m0", "theme": "Memory",
                                           "level": "medium", "theme_run_id": "r1"}])
    fin = _fin()
    fin["info"]["industry"] = "Airlines"        # a keyword the old matcher would have labelled "Airlines"
    card = engine.score_ticker("TEST", fin, _tech())
    assert card["industry"] == "Software - Application"     # still the spine's, not the vendor's (#266)
    assert card["themes"] == ["Memory"]




