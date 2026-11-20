"""#266: the Index filter's explanation is built on the server from the indexes the filter offers.

The text used to be a literal in ``core/static/rc_filters.js``'s ``explain()`` defaults. After the spine cutover
(#245) it was wrong in three places at once — it named the Dow Jones, credited Unusual Whales and said the lists
were cached in ``index_constituents`` — because a client-side literal cannot follow
``index_registry.filter_labels()``. These tests pin the fix: the text comes from the registry, it can name only a
label the filter offers, and the component's remaining default names no index at all, so a page rendered from a
payload written before this change cannot name one either.

Spine reads are monkeypatched; nothing here opens a store or a socket.
"""
from __future__ import annotations

import json
import re
from html import unescape

import pytest

from RevenueChaser.core import index_registry as ir
from RevenueChaser.core import reporting_common as rc

#: Every label the registry can display. The drift pin walks these: a label the filter does not offer must not be
#: named by the explanation, whichever it is.
ALL_LABELS = tuple(ir.LABELS.values())


def _spine(monkeypatch, members: dict[str, set[str]], nasdaq=("N0001",)) -> None:
    """The spine's index members and Nasdaq-listed names (``core.index_registry`` reads only the spine, #642 PR 6)."""
    from RevenueChaser.core import spine_reads
    monkeypatch.setattr(spine_reads, "membership", lambda *a, **k: [
        {"index_slug": slug, "ticker": t} for slug, ts in members.items() for t in sorted(ts)])
    monkeypatch.setattr(spine_reads, "universe", lambda tiers=("A",): [
        {"ticker": t, "exchange": "Nasdaq"} for t in nasdaq])


def _text(html: str) -> str:
    """The explanation without its tags and with its entities back, so an assertion reads the words the user reads.

    Unescaping matters: the labels carry ``&`` (S&P), and comparing against the escaped HTML would make every
    "this label is not named" assertion pass for the wrong reason.
    """
    return unescape(re.sub(r"<[^>]+>", "", html))


# ── the drift pin: only an offered label may be named ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("members", [
    {"sp500": {"S0001"}},
    {"sp500": {"S0001"}, "sp600": {"M0001"}},
    {"sp600": {"M0001"}},
    {"sp500": {"S0001"}, "sp400": {"D0001"}, "sp600": {"M0001"}, "ndx": {"Q0001"}},
    {},
])
def test_the_explanation_names_no_label_the_filter_does_not_offer(monkeypatch, members):
    _spine(monkeypatch, members)
    offered = set(ir.filter_labels())
    text = _text(ir.index_explain())
    for label in ALL_LABELS:
        short = ir.SHORT_LABELS.get(label, label)
        if label in offered:
            continue
        assert label not in text and short not in text, f"{label} is named but the filter does not offer it"


def test_the_dow_jones_leaves_the_text_because_the_spine_has_no_source_for_it(monkeypatch):
    """The concrete case #266 was filed for: ``dow`` is in ``LABELS`` but no spine source carries it."""
    _spine(monkeypatch, {"sp500": {"S0001"}, "sp600": {"M0001"}})
    assert "dow" in ir.LABELS and "Dow Jones" not in ir.filter_labels()
    assert "Dow Jones" not in ir.index_explain()


def test_the_explanation_credits_the_spine_and_not_unusual_whales(monkeypatch):
    _spine(monkeypatch, {"sp500": {"S0001"}})
    html = ir.index_explain()
    assert "identity spine" in html
    assert "Unusual Whales" not in html and "index_constituents" not in html


# ── what it does say ──────────────────────────────────────────────────────────────────────────────────────────────
def test_it_names_each_offered_fund_index_and_the_nasdaq_exchange(monkeypatch):
    _spine(monkeypatch, {"sp500": {"S0001"}, "sp600": {"M0001"}})
    html = ir.index_explain()
    assert "<b>S&amp;P 500</b> and <b>S&amp;P SmallCap 600</b> are index constituents" in html
    assert "index funds' daily holdings files" in html
    # The Nasdaq facet is the exchange, not the Nasdaq-100: its short label is the one the filter's button shows.
    assert "<b>Nasdaq-listed</b> means listed on the Nasdaq exchange (not the Nasdaq-100)" in html
    assert "Nasdaq Composite" not in html
    assert ir.EXPLAIN_COUNTS in html


def test_one_offered_index_reads_as_one(monkeypatch):
    _spine(monkeypatch, {"sp500": {"S0001"}}, nasdaq=())
    assert "<b>S&amp;P 500</b> is an index constituent" in ir.index_explain()


def test_a_stored_sp600_joins_the_text_without_a_code_change(monkeypatch):
    _spine(monkeypatch, {"sp500": {"S0001"}})
    assert "S&amp;P SmallCap 600" not in ir.index_explain()
    _spine(monkeypatch, {"sp500": {"S0001"}, "sp600": {"M0001"}})
    assert "S&amp;P SmallCap 600" in ir.index_explain()


def test_an_empty_spine_still_explains_the_counts(monkeypatch):
    """No membership at all is a board with no Index buttons; the note about the counts is still true."""
    _spine(monkeypatch, {}, nasdaq=())
    html = ir.index_explain()
    assert ir.EXPLAIN_COUNTS in html
    for label in ALL_LABELS:
        assert label not in _text(html)


# ── the meta the boards pass to the component ─────────────────────────────────────────────────────────────────────
def test_filters_meta_carries_the_index_explanation(monkeypatch):
    _spine(monkeypatch, {"sp500": {"S0001"}})
    meta = rc.filters_meta("b")
    assert meta["explain"]["index"] == ir.index_explain()


def test_a_boards_own_explain_still_wins_and_keeps_the_index_text(monkeypatch):
    """13F overrides the market-cap text (``module_sec_13f/report.py``); that must not drop the index text, and the
    board's own key must not be overwritten by this change.

    A board overriding ``index`` itself already worked before this change, because ``filters_meta`` passed the
    board's ``explain`` straight through — so it is asserted here rather than in a test of its own, which would
    pass on the merge-base and prove nothing (``red-on-base``).
    """
    _spine(monkeypatch, {"sp500": {"S0001"}})
    meta = rc.filters_meta("sec13f", explain={"mc": "the board's own words"})
    assert meta["explain"]["mc"] == "the board's own words"
    assert "identity spine" in meta["explain"]["index"]
    assert rc.filters_meta("b", explain={"index": "mine"})["explain"]["index"] == "mine"


def test_the_meta_is_json_serialisable(monkeypatch):
    _spine(monkeypatch, {"sp500": {"S0001"}})
    assert "identity spine" in json.dumps(rc.filters_meta("b"))


# ── the component's remaining default ─────────────────────────────────────────────────────────────────────────────
def test_the_js_default_names_no_index_so_it_cannot_go_stale():
    """A cached payload written before #266 carries no ``explain.index``, so the JS default is what that page shows.
    It must therefore name no index at all, and no retired source."""
    js = (rc._STATIC / "rc_filters.js").read_text(encoding="utf-8")
    # The defaults map of ``explain()``: its ``index`` entry up to the next key. Anchored on ``var d = {`` because
    # "index: " also opens a predicate in the filter functions above it.
    defaults = js.split("var d = {", 1)[1]
    index_default = _text(defaults.split("index: ", 1)[1].split("\n      mc: ", 1)[0])
    for label in ALL_LABELS:
        assert label not in index_default, f"the JS default names {label}"
    assert "Unusual Whales" not in js and "index_constituents" not in js
    assert "Nasdaq-listed" in index_default                 # the exchange caveat is not an index name
