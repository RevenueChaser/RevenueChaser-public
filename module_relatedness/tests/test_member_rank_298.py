"""#298: the naming prompt's example companies are the theme's largest names, not its first ones.

avo's B of 19 Nov 2026. The three steps of it: the rank itself
(:func:`themes.member_ranks`), the read order that carries it (``themes.ROW_ORDER``), and the prompt
``naming.name_themes`` actually sends, which is what changes the names a board shows.
"""
from __future__ import annotations

import pytest

from revenuechaser.core import rawstore
from revenuechaser.module_relatedness import naming, themes

CAPS = {"NVDA": 4.0e12, "AAPL": 3.0e12, "AVGO": 1.5e12, "AMAT": 1.6e11, "ADBE": 1.5e11, "ASML": 3.0e11}


def test_the_rank_is_the_cap_descending_place_and_a_name_with_no_cap_ranks_last():
    """The universe's own key: cap descending, NULLs last, ticker to break a tie
    (``core.universe._by_cap``). ``ZZZ`` and ``BBB`` have no cap, so they rank after every name that
    has one and alphabetically between themselves -- which is the order the table had before #298."""
    ranks = themes.member_ranks(["ADBE", "AAPL", "ZZZ", "NVDA", "BBB", "ASML"], caps=CAPS)
    assert [t for t, _r in sorted(ranks.items(), key=lambda kv: kv[1])] == [
        "NVDA", "AAPL", "ASML", "ADBE", "BBB", "ZZZ"]


def test_an_unreadable_universe_leaves_the_ticker_order_instead_of_failing_the_run(monkeypatch):
    """A rank is the prompt's order, never the run's success: with no caps to be had every name keeps
    its alphabetical place, which is what the table held before #298."""
    import revenuechaser.core.universe as universe

    def _boom(*_a, **_k):
        raise RuntimeError("no spine")

    monkeypatch.setattr(universe, "classification_universe_rows", _boom)
    assert themes.member_ranks(["NVDA", "AAPL", "ADBE"]) == {"AAPL": 1, "ADBE": 2, "NVDA": 3}


def _members(run_id: str, rows: list[tuple[str, int | None]]) -> None:
    rawstore.write_rows("relatedness_theme_members", [
        {"ticker": t, "theme_id": f"{run_id}:f1", "weight": 1.0, "rank": r} for t, r in rows])


def test_run_rows_reads_the_members_rank_first(rawstore_tmp_db):
    _members("rankA", [("ADBE", 4), ("NVDA", 1), ("AAPL", 2)])
    got = [r["ticker"] for r in themes.run_rows("relatedness_theme_members", "rankA")]
    assert got == ["NVDA", "AAPL", "ADBE"]


def test_a_stored_run_keeps_the_ticker_order_its_unranked_members_had(rawstore_tmp_db):
    """``rank`` is additive, so every member of a run written before #298 is NULL. ``NULLS LAST``
    keeps those rows together and the ``ticker`` tie-break gives them the order they had.

    The ranked half comes first on purpose: it is what this change does, and a test whose first
    assertion is the unchanged fallback would pass on the merge base and prove nothing
    (``scripts/red_on_base.py``). Both halves are one test id for the same reason.
    """
    _members("mixA", [("ADBE", None), ("AAPL", 2), ("NVDA", 1)])
    assert [r["ticker"] for r in themes.run_rows("relatedness_theme_members", "mixA")] == [
        "NVDA", "AAPL", "ADBE"]
    _members("oldA", [("NVDA", None), ("AAPL", None), ("ADBE", None)])
    assert [r["ticker"] for r in themes.run_rows("relatedness_theme_members", "oldA")] == [
        "AAPL", "ADBE", "NVDA"]


@pytest.fixture
def _named(rawstore_tmp_db):
    """One fine theme of six semiconductor names, ranked by cap, and the prompts naming sends."""
    rawstore.write_rows("relatedness_themes", [
        {"theme_id": "promptA:f1", "level": "fine", "parent_id": "", "label": "", "size": 6}])
    rawstore.write_rows("relatedness_theme_tags", [
        {"theme_id": "promptA:f1", "tag": t, "rank": i} for i, t in enumerate(("semiconductors", "foundry"))])
    ranks = themes.member_ranks(list(CAPS), caps=CAPS)
    _members("promptA", [(t, ranks[t]) for t in sorted(CAPS)])
    sent: list[str] = []

    def _complete(_system, user, **_kw):
        sent.append(user)
        return '{"name": "Semiconductors"}'

    naming.name_themes("promptA", complete=_complete)
    return sent


def test_the_naming_prompt_shows_the_theme_s_largest_names(_named):
    """The point of #298 (avo's B): ``AAPL, ADBE, AMAT, ...`` described a semiconductor theme worse
    than its biggest members do. The prompt is where it is decided -- the model is asked to name the
    cluster from these eight names (``naming.MAX_TICKERS``)."""
    line = next(l for p in _named for l in p.splitlines() if l.startswith("Example companies:"))
    assert line == "Example companies: NVDA, AAPL, AVGO, ASML, AMAT, ADBE"
