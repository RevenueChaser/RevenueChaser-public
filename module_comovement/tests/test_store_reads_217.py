"""#217 (F12): every read of ``boards/comovement.duckdb`` goes through ``module_comovement/store_reads.py``.

Two halves, as the News (PR #1195) and Relatedness (PR #1269) steps have them. The first is the invariant the
strangler step buys: no file outside the reader queries the Co-movement store, no module of the board carries one
of its table names of its own, and every table the schema files under ``db="comovement"`` has a name here — so
the SQL cannot creep back, and a table cannot be added to the store without a seam. The second is the behaviour
of each reader against a real temp store (``rawstore_tmp_db``), because a refactor that moves SQL is only safe if
the SQL's answers are pinned.

The read worth the test is the one that lived furthest from the tables: ``module_relatedness/engine.py`` picked
the run to enrich a peer row with, by the newest prices, then the board's default window (#95), then the latest —
the Co-movement board's own ordering rule, written in another board's file. It is the reader's now, so the two
boards cannot disagree about which run is "the current one".

No network and no real store: ``conftest.py`` redirects the roots and the autouse fixture gives each test its own
file.
"""
from __future__ import annotations

import re
from pathlib import Path

from revenuechaser.core import rawstore
from revenuechaser.module_comovement import store_reads as sr

REPO = Path(__file__).resolve().parents[2]
#: The four tables of the board's file, as the names a stray ``SELECT`` would spell.
TABLE_NAMES = (sr.RUNS, sr.NODES, sr.MEMBERS, sr.LAG)
HASH = "h1"


# ── the invariant ─────────────────────────────────────────────────────────────────────────────────────────────────
def _sources() -> list[Path]:
    """Every non-test Python file of the repository."""
    return [p for p in REPO.rglob("*.py")
            if "tests" not in p.parts and not p.name.startswith("test_") and ".git" not in p.parts]


def test_only_the_reader_queries_the_comovement_store():
    """A ``rawstore.query(..., db="comovement")`` anywhere else is embedded board SQL, which is what #217 is
    about. A write (``rawstore.atomic`` and the transaction's own ``execute``) is not a query and stays with the
    code that produces the rows; ``core/datasets.py`` names the db as the dataset's declaration, which is not a
    call.
    """
    call = re.compile(r"\.query\((?:[^()]|\([^()]*\))*db\s*=\s*[\"']comovement[\"']", re.S)
    offenders = [str(p.relative_to(REPO)) for p in _sources()
                 if p != Path(sr.__file__) and call.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"these files still query the Co-movement store directly: {offenders}"


def test_no_module_of_the_board_spells_a_comovement_table_name_itself():
    """The board's modules take the names from the reader, so a rename is a change to one file.

    That includes the writer: ``engine._persist`` names all four tables — in the write, in the two ``DELETE``
    sweeps and in the prune subquery — and was the largest block of names outside this seam.
    """
    offenders = {}
    for p in sorted((REPO / "module_comovement").glob("*.py")):
        if p == Path(sr.__file__):
            continue
        text = p.read_text(encoding="utf-8")
        # Only a string literal counts: the docstrings name the tables in prose on purpose.
        named = [t for t in TABLE_NAMES if f'"{t}"' in text or f"'{t}'" in text]
        if named:
            offenders[p.name] = named
    assert offenders == {}, f"these modules carry a co-movement table name of their own: {offenders}"


def test_every_comovement_table_in_the_schema_has_a_name_here():
    """A table added to the Co-movement store without a reader seam would reopen the hole this PR closes."""
    schema = {name for name, spec in rawstore.MANIFEST.items() if spec.get("db") == sr.DB}
    assert schema, "the schema should file some table under the co-movement store"
    assert schema == set(TABLE_NAMES), f"the reader names {sorted(TABLE_NAMES)}, the schema has {sorted(schema)}"


def test_the_peer_row_takes_the_run_from_the_boards_own_reader():
    """``module_relatedness/engine.py`` held the Co-movement board's run-picking rule (newest prices, then the
    default window, then the latest) and two member reads of its own. All three are the reader's now."""
    text = (REPO / "module_relatedness" / "engine.py").read_text(encoding="utf-8")
    for name in TABLE_NAMES:
        assert f'"{name}"' not in text and f"'{name}'" not in text, f"{name} is still spelled there"
    assert "prices_through DESC" not in text, "the run-picking order is the reader's one order"
    assert "store_reads" in text, "the peer row reads the board's seam"


def test_the_settings_record_accounts_for_the_runs_the_board_reads_back():
    """The record said the board reads back no board-file table of its own, and every Refresh does."""
    from revenuechaser.module_settings import boards as boards_mod
    row = next(b for b in boards_mod.BOARD_INPUTS if b["key"] == "module_comovement")
    assert set(row["tables"]) == set(TABLE_NAMES), row["tables"]


# ── rows ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _run(as_of: str, *, chash: str = HASH, null_json: str | None = None, prices_through: str | None = None,
         horizon: int = 1, benchmark: str = "SPY", window_days: int = 180) -> dict:
    return {"as_of": as_of, "generated_at": as_of, "window_days": window_days, "n_tickers": 2,
            "linkage": "average", "config_hash": chash, "horizon": horizon, "benchmark": benchmark,
            "benchmark_status": None, "prices_through": prices_through, "null_json": null_json}


def _node(as_of: str, cut: int, cluster_id: str, n: int, label: str = "") -> dict:
    return {"as_of": as_of, "cut": cut, "cluster_id": cluster_id, "label": label, "n": n, "mean_corr": 0.5}


def _member(as_of: str, cut: int, cluster_id: str, ticker: str, core: bool | None = None) -> dict:
    return {"as_of": as_of, "cut": cut, "cluster_id": cluster_id, "ticker": ticker, "core": core}


def _lag(as_of: str, cut: int, lag_id: str, ticker: str, held: bool | None = True) -> dict:
    return {"as_of": as_of, "cut": cut, "lag_id": lag_id, "ticker": ticker,
            "oos_r": 0.4, "oos_base": 0.1, "held": held}


# ── the persisted Fetch run a Refresh reuses ──────────────────────────────────────────────────────────────────────
def test_an_empty_store_reads_as_no_persisted_run(rawstore_tmp_db):
    assert sr.persisted_source(HASH) is None
    assert sr.persisted_null_json(HASH) is None
    assert sr.latest_run_with_lag(HASH) is None
    assert sr.latest_run_as_of() is None
    assert sr.run_row("2026-11-21T00:00:00") is None


def test_only_a_run_that_stored_a_null_counts_as_the_persisted_fetch(rawstore_tmp_db):
    """A Refresh stores no null, so a Refresh must not become the source of the next Refresh's verdicts."""
    rawstore.write_rows(sr.RUNS, [_run("2026-11-20T00:00:00", null_json='{"2": 0.3}', prices_through="2026-11-19"),
                                  _run("2026-11-21T00:00:00", prices_through="2026-11-20")])
    assert sr.persisted_source(HASH) == "2026-11-19"
    assert sr.persisted_null_json(HASH) == '{"2": 0.3}'


def test_the_newest_persisted_run_of_that_hash_wins_and_another_hash_is_not_read(rawstore_tmp_db):
    rawstore.write_rows(sr.RUNS, [
        _run("2026-11-19T00:00:00", null_json='{"2": 0.1}', prices_through="2026-11-18"),
        _run("2026-11-20T00:00:00", null_json='{"2": 0.2}', prices_through="2026-11-19"),
        _run("2026-11-21T00:00:00", chash="other", null_json='{"2": 0.9}', prices_through="2026-11-20")])
    assert sr.persisted_null_json(HASH) == '{"2": 0.2}'
    assert sr.persisted_source(HASH) == "2026-11-19"
    assert sr.persisted_null_json("other") == '{"2": 0.9}'
    assert sr.persisted_null_json("missing") is None


def test_the_lagged_test_comes_from_the_newest_run_that_has_one(rawstore_tmp_db):
    """A run without ``comov_lag`` rows must not shadow an older run that has them: cards would lose their
    persistence verdict for a quarter."""
    rawstore.write_rows(sr.RUNS, [_run("2026-11-19T00:00:00"), _run("2026-11-20T00:00:00"),
                                  _run("2026-11-21T00:00:00")])
    rawstore.write_rows(sr.LAG, [_lag("2026-11-19T00:00:00", 2, "g0", "AAA"),
                                 _lag("2026-11-20T00:00:00", 2, "g1", "BBB")])
    assert sr.latest_run_with_lag(HASH) == "2026-11-20T00:00:00"
    assert [r["ticker"] for r in sr.lag_rows("2026-11-20T00:00:00")] == ["BBB"]
    assert sr.lag_rows("2026-11-21T00:00:00") == []


def test_a_lag_row_carries_the_six_columns_the_card_reads(rawstore_tmp_db):
    rawstore.write_rows(sr.LAG, [_lag("2026-11-20T00:00:00", 3, "g0", "AAA", held=False)])
    row = sr.lag_rows("2026-11-20T00:00:00")[0]
    assert set(row) == {"cut", "lag_id", "ticker", "oos_r", "oos_base", "held"}
    assert (row["cut"], row["lag_id"], row["held"]) == (3, "g0", False)


# ── the stored run a store-only run may serve ─────────────────────────────────────────────────────────────────────
def test_the_runs_of_a_hash_and_its_prices_read_newest_first(rawstore_tmp_db):
    """The order is part of the answer: the engine walks the list and stops at the first run that predates the
    engine epoch or the last store write, so an older run must never come first."""
    rawstore.write_rows(sr.RUNS, [
        _run("2026-11-19T00:00:00", prices_through="2026-11-18"),
        _run("2026-11-21T00:00:00", prices_through="2026-11-18"),
        _run("2026-11-20T00:00:00", prices_through="2026-11-18"),
        _run("2026-11-22T00:00:00", prices_through="2026-11-21"),
        _run("2026-11-23T00:00:00", chash="other", prices_through="2026-11-18")])
    assert [r["as_of"] for r in sr.runs_with_prices(HASH, "2026-11-18")] == [
        "2026-11-21T00:00:00", "2026-11-20T00:00:00", "2026-11-19T00:00:00"]
    assert sr.runs_with_prices(HASH, "2026-11-20") == []


def test_the_clustered_names_of_a_run_read_as_a_set_of_tickers(rawstore_tmp_db):
    """What a stored run has to match to be served again: the same names, at any cut."""
    rawstore.write_rows(sr.MEMBERS, [
        _member("2026-11-20T00:00:00", 2, "c0", "AAA"), _member("2026-11-20T00:00:00", 3, "c1", "AAA"),
        _member("2026-11-20T00:00:00", 2, "c0", "BBB"), _member("2026-11-21T00:00:00", 2, "c0", "CCC")])
    assert sr.clustered_tickers("2026-11-20T00:00:00") == {"AAA", "BBB"}
    assert sr.clustered_tickers("2026-11-19T00:00:00") == set()


# ── the run the board renders ─────────────────────────────────────────────────────────────────────────────────────
def test_the_latest_run_is_filtered_by_horizon_and_benchmark_and_an_unset_filter_matches_any(rawstore_tmp_db):
    rawstore.write_rows(sr.RUNS, [
        _run("2026-11-19T00:00:00", horizon=1, benchmark="SPY"),
        _run("2026-11-20T00:00:00", horizon=5, benchmark="SPY"),
        _run("2026-11-21T00:00:00", horizon=1, benchmark="none")])
    assert sr.latest_run_as_of() == "2026-11-21T00:00:00"
    assert sr.latest_run_as_of(horizon=1) == "2026-11-21T00:00:00"
    assert sr.latest_run_as_of(horizon=1, benchmark="SPY") == "2026-11-19T00:00:00"
    assert sr.latest_run_as_of(horizon=5) == "2026-11-20T00:00:00"
    assert sr.latest_run_as_of(horizon=7) is None


def test_the_run_header_reads_every_column_so_an_older_store_still_loads(rawstore_tmp_db):
    rawstore.write_rows(sr.RUNS, [_run("2026-11-21T00:00:00", prices_through="2026-11-20")])
    row = sr.run_row("2026-11-21T00:00:00")
    assert row["config_hash"] == HASH and row["prices_through"] == "2026-11-20"
    # ``SELECT *``: a column the writer left unset is present and NULL, not missing.
    assert "dropped_json" in row and row["dropped_json"] is None


def test_the_clusters_read_by_cut_then_largest_first(rawstore_tmp_db):
    """The board shows them in this order, and ``load_payload`` builds the cards from the rows as they come."""
    rawstore.write_rows(sr.NODES, [
        _node("2026-11-21T00:00:00", 3, "c3", 4), _node("2026-11-21T00:00:00", 2, "c1", 2),
        _node("2026-11-21T00:00:00", 2, "c2", 9), _node("2026-11-20T00:00:00", 2, "old", 7)])
    assert [(r["cut"], r["cluster_id"]) for r in sr.node_rows("2026-11-21T00:00:00")] == [
        (2, "c2"), (2, "c1"), (3, "c3")]


def test_the_members_of_a_run_read_with_the_core_flag(rawstore_tmp_db):
    rawstore.write_rows(sr.MEMBERS, [
        _member("2026-11-21T00:00:00", 2, "c0", "AAA", core=True),
        _member("2026-11-21T00:00:00", 2, "c0", "BBB", core=False),
        _member("2026-11-21T00:00:00", 2, "c0", "CCC")])
    rows = {r["ticker"]: r["core"] for r in sr.member_rows("2026-11-21T00:00:00")}
    assert rows == {"AAA": True, "BBB": False, "CCC": None}
    assert sr.member_rows("2026-11-20T00:00:00") == []


# ── the run another board enriches a peer row with ────────────────────────────────────────────────────────────────
def test_the_default_run_is_the_newest_prices_then_the_default_window_then_the_latest(rawstore_tmp_db):
    """#95 stores other windows beside the board's default; a window of 60 must not displace the 180 one, and a
    run with newer prices wins over both (S7)."""
    rawstore.write_rows(sr.RUNS, [
        _run("2026-11-19T00:00:00", prices_through="2026-11-18", window_days=180),
        _run("2026-11-20T00:00:00", prices_through="2026-11-18", window_days=60),
        _run("2026-11-21T00:00:00", prices_through="2026-11-18", window_days=180),
        _run("2026-11-18T00:00:00", prices_through=None, window_days=180)])
    assert sr.default_run_as_of(1, "SPY", 180) == "2026-11-21T00:00:00"
    assert sr.default_run_as_of(1, "SPY", 60) == "2026-11-20T00:00:00"
    rawstore.write_rows(sr.RUNS, [_run("2026-11-17T00:00:00", prices_through="2026-11-19", window_days=60)])
    assert sr.default_run_as_of(1, "SPY", 180) == "2026-11-17T00:00:00", "newer prices beat the default window"
    assert sr.default_run_as_of(5, "SPY", 180) is None, "another horizon is another board default"


def test_a_run_with_no_prices_is_read_last_and_not_first(rawstore_tmp_db):
    """``prices_through DESC NULLS LAST``: a run written before the column existed must not look newest."""
    rawstore.write_rows(sr.RUNS, [_run("2026-11-21T00:00:00", prices_through=None),
                                  _run("2026-11-19T00:00:00", prices_through="2026-11-18")])
    assert sr.default_run_as_of(1, "SPY", 180) == "2026-11-19T00:00:00"


def test_the_cuts_of_a_run_read_coarsest_first(rawstore_tmp_db):
    """The caller maps them onto its own level names by position, so the order is the answer."""
    rawstore.write_rows(sr.NODES, [_node("2026-11-21T00:00:00", 5, "c5", 2),
                                   _node("2026-11-21T00:00:00", 2, "c2", 3),
                                   _node("2026-11-21T00:00:00", 2, "c2b", 1),
                                   _node("2026-11-20T00:00:00", 9, "old", 1)])
    assert sr.cuts_of_run("2026-11-21T00:00:00") == [2, 5]
    assert sr.cuts_of_run("2026-11-19T00:00:00") == []


def test_the_cluster_of_each_name_reads_as_the_three_columns_a_peer_row_needs(rawstore_tmp_db):
    rawstore.write_rows(sr.MEMBERS, [_member("2026-11-21T00:00:00", 2, "c0", "AAA", core=True),
                                     _member("2026-11-20T00:00:00", 2, "c9", "AAA")])
    rows = sr.cluster_members("2026-11-21T00:00:00")
    assert [set(r) for r in rows] == [{"cut", "cluster_id", "ticker"}]
    assert rows[0]["cluster_id"] == "c0"
