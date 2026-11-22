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








