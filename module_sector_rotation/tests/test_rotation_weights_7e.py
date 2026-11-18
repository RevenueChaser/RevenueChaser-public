"""Plan v5 step 7e: a company's rotation quadrant comes from the map funds that hold it, weighted by its share of
each fund's newest holdings. No typed ticker or cluster pairs. A company no map fund holds reads its own sector's
fund and says so (avo, 18 Nov 2026)."""
import logging

import pytest

from RevenueChaser.core import rotation_reference
from RevenueChaser.module_sector_rotation import engine, etf_holdings, universe
from RevenueChaser.rcdata import read


def _lines(*rows):
    return [{"etf": e, "as_of": None, "provider": "t", "ticker": t, "name": "", "weight": w} for e, t, w in rows]


@pytest.fixture
def holdings(monkeypatch):
    asked = []
    rows = _lines(
        ("SMH", "NVDA", 20.0), ("SMH", "SMCI", 5.0), ("SMH", None, 25.0), ("SMH", "TSM", 50.0),   # percent
        ("XLK", "NVDA", 0.15), ("XLK", "SMCI", 0.01), ("XLK", "MSFT", 0.84),                      # fractions
        ("IGV", "MSFT", None), ("IGV", "CRM", None),                                              # no weights published
        ("SPY", "NVDA", 7.0))                                                                     # never asked for

    def fake(etfs):
        asked.extend(etfs)
        return [r for r in rows if r["etf"] in set(etfs)]
    monkeypatch.setattr(read, "etf_holdings", fake)
    monkeypatch.setattr(read, "etf_holdings_nport", lambda etfs: [])
    return asked


def test_share_is_the_line_over_the_funds_weighted_lines_largest_first(holdings):
    w = etf_holdings.ticker_weights()
    assert w["NVDA"] == [("SMH", pytest.approx(20 / 75)), ("XLK", pytest.approx(0.15))]
    assert w["SMCI"] == [("SMH", pytest.approx(5 / 75)), ("XLK", pytest.approx(0.01))]
    assert None not in w


def test_only_sector_theme_and_industry_funds_are_read(holdings):
    etf_holdings.ticker_weights()
    groups = {rotation_reference.rotation_etfs()[e]["group"] for e in holdings}
    assert groups == {"sector", "theme", "industry"}
    assert "SPY" not in holdings and "IWM" not in holdings


def test_a_fund_with_no_weighted_line_is_named_and_gives_nothing(holdings, caplog):
    with caplog.at_level(logging.WARNING):
        w = etf_holdings.ticker_weights()
    assert "CRM" not in w and all(etf != "IGV" for etf, _ in w["MSFT"])
    assert "IGV" in caplog.text


def test_a_fund_the_daily_file_lacks_reads_its_n_port_report_and_no_other_fund_does(holdings, monkeypatch, caplog):
    asked = []

    def nport(etfs):
        asked.extend(etfs)
        return _lines(("PEJ", "DIS", 6.0), ("PEJ", "RCL", 2.0), ("SMH", "NVDA", 99.0))      # SMH has a daily file
    monkeypatch.setattr(read, "etf_holdings_nport", nport)
    with caplog.at_level(logging.WARNING):
        w = etf_holdings.ticker_weights()
    assert w["DIS"] == [("PEJ", pytest.approx(0.75))] and w["RCL"] == [("PEJ", pytest.approx(0.25))]
    assert "PEJ" in asked and "SMH" not in asked and "XLK" not in asked
    assert "PEJ" not in caplog.text and "IGV" in caplog.text


def test_quadrant_is_where_most_of_the_weight_sits():
    w = {"AMD": [("SMH", 0.07), ("XLK", 0.01), ("SOXX", 0.05)]}
    quadrants = {"SMH": "LAGGING", "XLK": "LEADING", "SOXX": "LEADING"}
    assert engine.get_quadrant_for_ticker("AMD", w, quadrants) == ("LAGGING", "funds")
    assert engine.get_quadrant_for_ticker("AMD", w, {**quadrants, "SMH": ""}) == ("LEADING", "funds")


def test_a_tie_goes_to_the_better_quadrant():
    w = {"X": [("A", 0.1), ("B", 0.1)]}
    assert engine.get_quadrant_for_ticker("X", w, {"A": "LAGGING", "B": "IMPROVING"}) == ("IMPROVING", "funds")


def test_a_company_no_map_fund_holds_reads_its_sector_fund_and_says_so():
    quadrants = {"SPY": "LEADING", "XLY": "WEAKENING"}
    assert engine.get_quadrant_for_ticker("ONON", {}, quadrants, "Consumer Cyclical") == ("WEAKENING", "sector XLY")
    held = {"ONON": [("XRT", 0.01)]}                       # held, but by a fund with no quadrant yet
    assert engine.get_quadrant_for_ticker("ONON", held, quadrants, "Consumer Cyclical") == ("WEAKENING", "sector XLY")


def test_no_fund_and_no_sector_is_empty_never_spy():
    quadrants = {"SPY": "LEADING", "XLK": "LEADING"}
    assert engine.get_quadrant_for_ticker("ZZZZ", {}, quadrants) == ("", "")
    assert engine.get_quadrant_for_ticker("ZZZZ", {}, quadrants, "Unclassified") == ("", "")
    assert engine.get_quadrant_for_ticker("ZZZZ", {}, {}, "Technology") == ("", "")


def test_the_badge_marks_a_sector_reading():
    from RevenueChaser.module_earnings_radar.report import _quadrant_badge
    assert "·sec" in _quadrant_badge("LAGGING", "sector XLY") and "XLY" in _quadrant_badge("LAGGING", "sector XLY")
    assert "·sec" not in _quadrant_badge("LAGGING", "funds")
    assert "N/A" in _quadrant_badge("")


def test_the_typed_maps_are_gone():
    assert not hasattr(universe, "TICKER_ETF_MAP") and not hasattr(engine, "CLUSTER_TO_ETFS")
