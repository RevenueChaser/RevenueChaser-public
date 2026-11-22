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
    """Since #642 PR 6 ``load_index`` is the spine's membership; ``dow`` has no source there, so it stays None."""
    universe_store.membership("sp500", {"AAPL", "MSFT"})
    assert ir.load_index("sp500") == {"AAPL", "MSFT"}
    assert ir.load_index("dow") is None








