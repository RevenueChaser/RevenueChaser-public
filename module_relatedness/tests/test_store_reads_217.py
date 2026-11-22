"""#217 (F12): every read of ``boards/relatedness.duckdb`` goes through ``module_relatedness/store_reads.py``.

Two halves, as the News board's step (PR #1195) has them. The first is the invariant the strangler step buys: no
file outside the reader queries the Relatedness store, no module of the board carries one of its table names of
its own, and every table the schema files under ``db="relatedness"`` has a name here — so the SQL cannot creep
back, and a table cannot be added to the store without a seam. The second is the behaviour of each reader against
a real temp store (``rawstore_tmp_db``), because a refactor that moves SQL is only safe if the SQL's answers are
pinned.

The three reads this step pulled back from outside the board are the ones worth the test: ``core/universe.py``
held its own copy of "which run is pinned" and of the ``theme_id = ? OR starts_with(theme_id, ?)`` predicate that
means "the rows of this run", and ``module_sector_rotation`` a third. The board and the one Theme vocabulary now
cut a run the same way by construction.

No network and no real store: ``conftest.py`` redirects the roots and the autouse fixture gives each test its own
file.
"""
from __future__ import annotations

import re
from pathlib import Path

from revenuechaser.core import rawstore, universe
from revenuechaser.module_relatedness import store_reads as sr

REPO = Path(__file__).resolve().parents[2]
#: The eleven tables of the board's file, as the names a stray ``SELECT`` would spell.
TABLE_NAMES = (sr.PROFILES, sr.ATTRIBUTES, sr.EMBEDDINGS, sr.SCORES, sr.THEME_RUNS, sr.THEMES, sr.THEME_TAGS,
               sr.THEME_MEMBERS, sr.THEME_ETFS, sr.TICKER_THEMES, sr.LLM_CACHE)
NOW = 1_763_000_000.0
RUN = "r1"


# ── the invariant ─────────────────────────────────────────────────────────────────────────────────────────────────
def _sources() -> list[Path]:
    """Every non-test Python file of the repository."""
    return [p for p in REPO.rglob("*.py")
            if "tests" not in p.parts and not p.name.startswith("test_") and ".git" not in p.parts]


def test_only_the_reader_queries_the_relatedness_store():
    """A ``rawstore.query(..., db="relatedness")`` anywhere else is embedded board SQL, which is what #217 is
    about. A write (``rawstore.execute``, ``atomic``, ``transaction``) is not a query and stays with the code that
    produces the rows; ``core/datasets.py`` names the db as the dataset's declaration, which is not a call.
    """
    call = re.compile(r"\.query\((?:[^()]|\([^()]*\))*db\s*=\s*[\"']relatedness[\"']", re.S)
    offenders = [str(p.relative_to(REPO)) for p in _sources()
                 if p != Path(sr.__file__) and call.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"these files still query the Relatedness store directly: {offenders}"


def test_no_module_of_the_board_spells_a_relatedness_table_name_itself():
    """The board's modules take the names from the reader, so a rename is a change to one file.

    That includes the writes: the cutover's three ``INSERT ... SELECT`` statements name four tables between them
    and were the largest block of names outside this seam.
    """
    offenders = {}
    for p in sorted((REPO / "module_relatedness").glob("*.py")):
        if p == Path(sr.__file__):
            continue
        text = p.read_text(encoding="utf-8")
        # Only a string literal counts: the docstrings name the tables in prose on purpose.
        named = [t for t in TABLE_NAMES if f'"{t}"' in text or f"'{t}'" in text]
        if named:
            offenders[p.name] = named
    assert offenders == {}, f"these modules carry a relatedness table name of their own: {offenders}"


def test_every_relatedness_table_in_the_schema_has_a_name_here():
    """A table added to the Relatedness store without a reader seam would reopen the hole this PR closes."""
    schema = {name for name, spec in rawstore.MANIFEST.items() if spec.get("db") == sr.DB}
    assert schema, "the schema should file some table under the relatedness store"
    assert schema == set(TABLE_NAMES), f"the reader names {sorted(TABLE_NAMES)}, the schema has {sorted(schema)}"


def test_the_board_and_the_theme_vocabulary_cut_a_run_the_same_way():
    """``core.universe`` held a second copy of the run predicate and of the pinned-run lookup; both are the
    reader's now, so the one Theme vocabulary (ADR-2) and the board cannot disagree about what a run's rows are."""
    text = (REPO / "core" / "universe.py").read_text(encoding="utf-8")
    assert "starts_with(theme_id" not in text, "the run predicate is the reader's one predicate"
    assert "theme_runs" not in text and "relatedness_theme" not in text
    assert "store_reads" in text, "core.universe reads the board's seam"


# ── theme_runs ────────────────────────────────────────────────────────────────────────────────────────────────────
def _run(run_id=RUN, current=0) -> dict:
    return {"id": run_id, "created_at": "2026-11-21T00:00:00Z", "k_fine": 2, "k_medium": 1, "k_coarse": 1,
            "jaccard": 0.9, "is_current": current, "run_at": NOW}


def test_no_pinned_run_reads_as_none_and_not_as_an_error(rawstore_tmp_db):
    assert sr.pinned_run_id() is None
    rawstore.write_rows(sr.THEME_RUNS, [_run("r1"), _run("r2")])
    assert sr.pinned_run_id() is None, "a stored run is not a pinned run"


def test_the_pinned_run_is_the_one_carrying_is_current(rawstore_tmp_db):
    rawstore.write_rows(sr.THEME_RUNS, [_run("r1"), _run("r2", current=1)])
    assert sr.pinned_run_id() == "r2"
    assert universe.current_theme_run() == "r2", "the one lookup reads this function"
    assert universe.current_theme_run(strict=True) == "r2"


# ── the theme tables of one run ───────────────────────────────────────────────────────────────────────────────────
def _theme(theme_id, level, parent="", label="", size=0) -> dict:
    return {"theme_id": theme_id, "level": level, "parent_id": parent, "label": label, "size": size}


def _member(theme_id, ticker, rank=None) -> dict:
    return {"theme_id": theme_id, "ticker": ticker, "weight": 1.0, "rank": rank}


def _tree() -> None:
    """One run: two fine themes under one medium under one coarse, and another run's rows beside them."""
    rawstore.write_rows(sr.THEMES, [
        _theme(f"{RUN}:c0", "coarse", label="Technology", size=3),
        _theme(f"{RUN}:m0", "medium", parent=f"{RUN}:c0", label="Semiconductors", size=3),
        _theme(f"{RUN}:f0", "fine", parent=f"{RUN}:m0", label="Foundries", size=2),
        _theme(f"{RUN}:f1", "fine", parent=f"{RUN}:m0", label="Fabless", size=1),
        _theme("other:c0", "coarse", label="Not this run", size=9),
    ])
    rawstore.write_rows(sr.THEME_MEMBERS, [
        _member(f"{RUN}:f0", "TSM", 2), _member(f"{RUN}:f0", "GFS", 1), _member(f"{RUN}:f1", "NVDA", 1),
        _member("other:f0", "AAPL", 1),
    ])


def test_a_run_reads_its_own_rows_and_no_other_runs(rawstore_tmp_db):
    """A theme id is the run id or ``<run>:<...>``: the prefix filter is the reader's one predicate."""
    _tree()
    assert {r["theme_id"] for r in sr.run_rows(sr.THEMES, RUN)} == {f"{RUN}:c0", f"{RUN}:m0", f"{RUN}:f0",
                                                                   f"{RUN}:f1"}
    assert [r["theme_id"] for r in sr.run_rows(sr.THEMES, RUN, "coarse")] == [f"{RUN}:c0"]
    assert {r["ticker"] for r in sr.run_rows(sr.THEME_MEMBERS, RUN)} == {"TSM", "GFS", "NVDA"}
    assert sr.run_rows(sr.THEMES, "nosuchrun") == []


def test_the_members_read_in_rank_order_so_the_prompt_sees_the_largest_names(rawstore_tmp_db):
    """#298: ``rank`` is the member's place in the cap-descending universe, and ``naming._aggregate`` keeps the
    first names of a theme as the prompt's example companies. A run written before the column falls back to the
    ticker order (``NULLS LAST``)."""
    rawstore.write_rows(sr.THEME_MEMBERS, [_member("rk:f0", "AAA", 3), _member("rk:f0", "ZZZ", 1),
                                           _member("rk:f0", "MMM", None), _member("rk:f0", "BBB", 2)])
    assert [r["ticker"] for r in sr.run_rows(sr.THEME_MEMBERS, "rk")] == ["ZZZ", "BBB", "AAA", "MMM"]


def test_the_tags_read_in_their_stored_rank_order(rawstore_tmp_db):
    """#20: without the order the offline label and the naming prompt could differ between two machines."""
    rawstore.write_rows(sr.THEME_TAGS, [{"theme_id": "tg:f0", "tag": "zinc", "rank": 2},
                                        {"theme_id": "tg:f0", "tag": "alpha", "rank": 1}])
    assert [r["tag"] for r in sr.run_rows(sr.THEME_TAGS, "tg")] == ["alpha", "zinc"]


def test_the_theme_vocabulary_reads_the_five_columns_it_needs(rawstore_tmp_db):
    """``core.universe.theme_catalog`` asked for these five by name in its own copy of the predicate."""
    _tree()
    rows = sr.catalog_rows(RUN)
    assert {r["theme_id"] for r in rows} == {f"{RUN}:c0", f"{RUN}:m0", f"{RUN}:f0", f"{RUN}:f1"}
    assert set(rows[0]) == {"theme_id", "level", "parent_id", "label", "size"}
    assert universe.theme_catalog(RUN)[f"{RUN}:m0"]["label"] == "Semiconductors"


def test_the_members_of_a_run_read_as_the_ticker_and_its_fine_theme(rawstore_tmp_db):
    _tree()
    rows = sr.member_tickers_of_run(RUN)
    assert set(rows[0]) == {"ticker", "theme_id"}
    assert {(r["ticker"], r["theme_id"]) for r in rows} == {("TSM", f"{RUN}:f0"), ("GFS", f"{RUN}:f0"),
                                                            ("NVDA", f"{RUN}:f1")}
    # The ids a ticker carries are its fine theme and its parents — the vocabulary's own walk over these rows.
    assert universe._theme_ids_by_ticker(universe.theme_catalog(RUN), RUN)["TSM"] == [
        f"{RUN}:c0", f"{RUN}:f0", f"{RUN}:m0"]


def test_the_coarse_labels_are_the_stored_ones_of_that_run_only(rawstore_tmp_db):
    """Sector Rotation's overlay reads the label ``relatedness_themes`` holds, not the catalog's (avo's card on
    the R2 review, 14 Oct 2026)."""
    _tree()
    assert sr.coarse_labels_of_run(RUN) == [{"theme_id": f"{RUN}:c0", "label": "Technology"}]
    assert sr.coarse_labels_of_run("other") == [{"theme_id": "other:c0", "label": "Not this run"}]


def test_the_cutover_counts_what_it_is_about_to_move(rawstore_tmp_db):
    """``member_count_of_run`` is the guard that refuses a run with no members; ``profiled_ticker_count`` counts
    the distinct tickers whose fine theme still exists, which is why it is a join."""
    assert sr.member_count_of_run(RUN) == 0
    assert sr.profiled_ticker_count(RUN) == 0
    _tree()
    assert sr.member_count_of_run(RUN) == 3
    assert sr.profiled_ticker_count(RUN) == 3
    rawstore.write_rows(sr.THEME_MEMBERS, [_member(f"{RUN}:fGONE", "ORPHAN", 1)])
    assert sr.member_count_of_run(RUN) == 4, "the guard counts every member row"
    assert sr.profiled_ticker_count(RUN) == 3, "a member whose fine theme is gone is not profiled"


def test_a_themes_etfs_read_best_rank_first(rawstore_tmp_db):
    rawstore.write_rows(sr.THEME_ETFS, [
        {"theme_id": f"{RUN}:c0", "etf": "SMH", "etf_name": "", "group_name": "", "overlap": 0.3, "rank": 2},
        {"theme_id": f"{RUN}:c0", "etf": "SOXX", "etf_name": "", "group_name": "", "overlap": 0.4, "rank": 1},
        {"theme_id": "other:c0", "etf": "XLF", "etf_name": "", "group_name": "", "overlap": 0.2, "rank": 1},
    ])
    assert [r["etf"] for r in sr.theme_etfs(f"{RUN}:c0")] == ["SOXX", "SMH"]
    assert sr.theme_etfs("nosuchtheme") == []


# ── ticker_themes: the cut-over run ───────────────────────────────────────────────────────────────────────────────
def _cut(ticker, theme_id, level, theme="", run_id=RUN) -> dict:
    return {"ticker": ticker, "theme_id": theme_id, "theme": theme, "level": level, "theme_run_id": run_id,
            "fetched_at": NOW}


def _cut_rows() -> None:
    rawstore.write_rows(sr.TICKER_THEMES, [
        _cut("TSM", f"{RUN}:f0", "fine", "Foundries"),
        _cut("TSM", f"{RUN}:m0", "medium", "Semiconductors"),
        _cut("TSM", f"{RUN}:c0", "coarse", "Technology"),
        _cut("NVDA", f"{RUN}:m0", "medium", ""),              # a label not copied on yet
        _cut("AAPL", "old:m0", "medium", "Phones", run_id="old"),
    ])


def test_only_the_asked_runs_rows_answer(rawstore_tmp_db):
    """Every older run's rows stay in the store (card 10, REL-1): a read names its run."""
    _cut_rows()
    assert [r["ticker"] for r in sr.ticker_theme_levels(RUN)].count("AAPL") == 0
    assert {r["ticker"] for r in sr.ticker_theme_levels("old")} == {"AAPL"}
    assert sr.ticker_theme_row_count(RUN) == 4
    assert sr.ticker_theme_row_count("old") == 1
    assert sr.ticker_theme_row_count("nosuchrun") == 0


def test_a_tickers_medium_themes_read_by_the_ticker_in_any_case(rawstore_tmp_db):
    _cut_rows()
    assert [r["theme_id"] for r in sr.medium_labels_for_ticker("tsm", RUN)] == [f"{RUN}:m0"]
    assert set(sr.medium_labels_for_ticker("TSM", RUN)[0]) == {"theme", "theme_id"}
    assert sr.medium_labels_for_ticker("TSM", "old") == []
    assert sr.medium_labels_for_ticker("NOSUCH", RUN) == []


def test_many_tickers_read_in_one_query_and_an_empty_ask_reaches_no_store(rawstore_tmp_db, monkeypatch):
    _cut_rows()
    got = sr.medium_labels_for_tickers(["tsm", "NVDA", "NOSUCH"], RUN)
    assert {(r["ticker"], r["theme_id"]) for r in got} == {("TSM", f"{RUN}:m0"), ("NVDA", f"{RUN}:m0")}

    def boom(*a, **k):
        raise AssertionError("an empty ask must not reach the store")
    monkeypatch.setattr(rawstore, "query", boom)
    assert sr.medium_labels_for_tickers([], RUN) == []


def test_the_medium_members_of_a_cut_over_run_are_its_medium_rows(rawstore_tmp_db):
    """The source side of a theme adoption: the mediums a run cut over, not the fine members."""
    _cut_rows()
    assert {(r["ticker"], r["theme_id"]) for r in sr.medium_members_of_run(RUN)} == {("TSM", f"{RUN}:m0"),
                                                                                    ("NVDA", f"{RUN}:m0")}


def test_a_rewrite_reads_back_the_whole_row_it_will_write(rawstore_tmp_db):
    """``naming`` copies its labels onto these rows with a whole-row ``write_rows``, so the read asks for the
    table's key and payload by name rather than ``*``."""
    _cut_rows()
    rows = sr.ticker_theme_rows(RUN)
    assert len(rows) == 4
    assert set(rows[0]) == {"ticker", "theme_id", "theme", "level", "theme_run_id", "fetched_at"}


def test_the_levels_read_carries_the_stored_label_as_the_fallback(rawstore_tmp_db):
    """The level comes from the store and the label from the one vocabulary; the stored ``theme`` is what a
    ticker shows when the catalog has no row for its theme."""
    _cut_rows()
    rows = {(r["ticker"], r["level"]): r for r in sr.ticker_theme_levels(RUN)}
    assert set(rows[("TSM", "coarse")]) == {"ticker", "level", "theme_id", "theme"}
    assert rows[("TSM", "coarse")]["theme"] == "Technology"
    assert rows[("NVDA", "medium")]["theme"] == ""


# ── llm_cache ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _cache(key, model) -> dict:
    return {"cache_key": key, "ticker": "AAPL", "cik": None, "model": model, "thinking": 0, "effort": "low",
            "prompt_version": "v1", "input_hash": key, "response": "{}", "fetched_at": NOW, "status": "ok"}


def test_the_cache_is_counted_per_model(rawstore_tmp_db):
    assert sr.llm_cache_rows_for_model("deepseek-chat") == 0
    rawstore.write_rows(sr.LLM_CACHE, [
        _cache("a", "deepseek-chat"), _cache("b", "deepseek-chat"), _cache("c", "evren"),
    ])
    assert sr.llm_cache_rows_for_model("deepseek-chat") == 2
    assert sr.llm_cache_rows_for_model("evren") == 1
    assert sr.llm_cache_rows_for_model("nosuchmodel") == 0
