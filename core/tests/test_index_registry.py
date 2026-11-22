"""Tests for the index membership registry (pure functions, no network)."""
import pytest

from revenuechaser.rcdata.tests import universe_store
from revenuechaser.core import index_registry as ir
from revenuechaser.core import rawstore


def test_index_memberships_inversion():
    indexes = {
        "sp500": {"AAPL", "MSFT"},
        "dow": {"AAPL"},
        "nasdaq": {"MSFT"},
    }
    memberships = ir._index_memberships(indexes)
    assert memberships["AAPL"] == ["S&P 500", "Dow Jones"]
    assert memberships["MSFT"] == ["S&P 500", "Nasdaq Composite"]
    assert "XXX" not in memberships


def test_the_labels_put_the_sp_indexes_first_and_name_every_russell_index():
    labels = list(ir.LABELS.values())
    assert labels[:3] == ["S&P 500", "Dow Jones", "S&P SmallCap 600"] and labels[-1] == "Nasdaq Composite"
    assert {"Russell 1000", "Russell 2000", "Russell 3000", "Russell Microcap", "Russell Midcap", "Russell Top 200",
            "Russell 1000 Growth", "Russell 1000 Value", "Russell 2000 Growth", "Russell 2000 Value",
            "Russell Midcap Growth", "Russell Midcap Value", "Russell Top 200 Growth", "Russell Top 200 Value",
            "Nasdaq-100 Top 30"} <= set(labels)


#: Group A (avo, 22 Nov 2026 23:17): the S&P and Dow Jones indexes read from their funds' files.
GROUP_A = {"sp100": "S&P 100", "sp500_growth": "S&P 500 Growth", "sp500_value": "S&P 500 Value",
           "sp500_ex_sp100": "S&P 500 ex S&P 100", "sp400_growth": "S&P MidCap 400 Growth",
           "sp400_value": "S&P MidCap 400 Value", "sp600_growth": "S&P SmallCap 600 Growth",
           "sp600_value": "S&P SmallCap 600 Value", "sp900_growth": "S&P 900 Growth", "sp900_value": "S&P 900 Value",
           "sp1500": "S&P Composite 1500", "sp_total_market": "S&P Total Market",
           "sp_hy_dividend_aristocrats": "S&P High Yield Dividend Aristocrats",
           "sp500_high_dividend": "S&P 500 High Dividend", "dj_us": "Dow Jones U.S.",
           "dj_us_select_dividend": "Dow Jones U.S. Select Dividend", "dj_us_select_reit": "Dow Jones U.S. Select REIT"}


def test_the_group_a_indexes_have_labels_after_the_headline_ones_and_before_russell():
    """Display order: the badge shows the first match, so the headline S&P labels stay first; the S&P family next,
    then Dow Jones, then Russell, and Nasdaq Composite last."""
    order = list(ir.LABELS)
    assert {s: ir.LABELS.get(s) for s in GROUP_A} == GROUP_A
    assert all(3 <= order.index(s) < order.index("russell_top200") for s in GROUP_A)
    assert max(order.index(s) for s in GROUP_A if s.startswith("sp")) < min(
        order.index(s) for s in GROUP_A if s.startswith("dj_"))
    assert len(set(ir.LABELS.values())) == len(ir.LABELS)             # no two slugs share a label


def test_index_for_with_registry():
    reg = {"AAPL": {"index": ["S&P 500"]}}
    assert ir.index_for("aapl", reg) == ["S&P 500"]
    assert ir.index_for("MSFT", reg) == []


def test_annotate_cards_sets_index():
    cards = [{"ticker": "AAPL"}, {"ticker": "MSFT"}]
    reg = {"AAPL": {"index": ["S&P 500", "Dow Jones"]}}
    ir.annotate_cards(cards, reg)
    assert cards[0]["index"] == ["S&P 500", "Dow Jones"]
    assert cards[1]["index"] == []


def test_save_and_load_index(rawstore_tmp_db):
    """Since #642 PR 6 ``load_index`` is the spine's membership; this store holds no ``dow`` rows, so it is None."""
    universe_store.membership("sp500", {"AAPL", "MSFT"})
    assert ir.load_index("sp500") == {"AAPL", "MSFT"}
    assert ir.load_index("dow") is None








