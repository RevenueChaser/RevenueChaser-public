"""#150 (U13): the bulk readers give what the per-key readers give, in one query."""
from __future__ import annotations

import pytest

from revenuechaser.rcdata.tests import fund_store
from revenuechaser.core import rawstore, taxonomy
from revenuechaser.core.providers import sec_edgar
from revenuechaser.module_relatedness import themes


def _count_queries(monkeypatch):
    calls = []
    real = rawstore.query

    def counting(*a, **k):
        calls.append(a[0])
        return real(*a, **k)
    monkeypatch.setattr(rawstore, "query", counting)
    return calls










def test_stored_annual_many_matches_get_annual(rawstore_tmp_db):
    annual = [{"fiscal_year": 2023, "revenue": 5.0}]
    fund_store.put_edgar([
        {"ticker": "AAA", "annual": annual, "quarterly": [], "meta": {"entity_name": "Aaa", "is_us": True}},
        {"ticker": "BBB", "annual": [], "quarterly": [], "meta": {}},
    ])
    many = sec_edgar.stored_annual_many(["aaa", "BBB", "CCC"])
    assert many["AAA"] == sec_edgar.get_annual("AAA", no_fetch=True)
    assert many["BBB"] == sec_edgar.get_annual("BBB", no_fetch=True)
    assert "CCC" not in many


def _seed_themes():
    rawstore.write_rows("theme_runs", [{"id": "r1", "created_at": "x", "k_fine": 1, "k_medium": 1,
                                        "k_coarse": 1, "jaccard": 1.0, "is_current": 1}])
    rawstore.write_rows("relatedness_themes", [{"theme_id": "r1:m9", "level": "medium", "parent_id": None,
                                                "label": "Label From Catalog", "size": 3}])
    rawstore.write_rows("ticker_themes", [
        {"ticker": "AAA", "theme_id": "r1:m0", "theme": "Chips", "level": "medium", "theme_run_id": "r1"},
        {"ticker": "BBB", "theme_id": "r1:m9", "theme": "", "level": "medium", "theme_run_id": "r1"},
        {"ticker": "CCC", "theme_id": "r1:c0", "theme": "Coarse", "level": "coarse", "theme_run_id": "r1"},
    ])


def test_themes_for_tickers_match_themes_for_ticker(rawstore_tmp_db):
    _seed_themes()
    many = themes.themes_for_tickers(["aaa", "BBB", "CCC", "DDD"])
    assert many == {"AAA": ["Chips"], "BBB": ["Label From Catalog"]}
    for t in ("AAA", "BBB", "CCC", "DDD"):
        assert many.get(t, []) == themes.themes_for_ticker(t)


def test_themes_for_tickers_is_a_fixed_number_of_queries(rawstore_tmp_db, monkeypatch):
    _seed_themes()
    calls = _count_queries(monkeypatch)
    themes.themes_for_tickers(["AAA", "BBB"])
    small = len(calls)
    calls.clear()
    themes.themes_for_tickers([f"T{i}" for i in range(80)] + ["AAA", "BBB"])
    assert len(calls) == small


def test_themes_for_many_never_breaks_a_scan(monkeypatch):
    def boom(_t):
        raise RuntimeError("store down")
    monkeypatch.setattr(themes, "themes_for_tickers", boom)
    assert taxonomy.themes_for_many(["AAA"]) == {}


