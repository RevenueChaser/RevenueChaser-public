"""Persistence & population tests — the DB is correctly filled after functions run.

Coverage model (plan Phase 6):
- Group A (illustrative): DB is correctly filled after a representative set of
  functions runs (mocked at the HTTP boundary).
- Group B: data is never "unwired" — durability across connections, round-trip
  integrity, write failures propagate, idempotency, and no module writes raw
  files directly anymore.
- Group C (gate): every table in the rawstore manifest has a population test.
- Group D: TTL / no_fetch behaviour preserved.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.core import rawstore


# ── Group A: DB filled after a function runs ─────────────────────────────────







def test_ticker_store_populated(rawstore_tmp_db):
    from RevenueChaser.core import ticker_store
    ticker_store.write_from_cards([{
        "ticker": "ETON", "name": "Eton", "sector": "Health Care", "market_cap": 1.8e9,
        "total_points": 9, "themes": ["Biotech"], "signals": [],
    }], asof="2026-08-22")
    assert ticker_store.count() == 1
    assert ticker_store.get("ETON")["themes"] == ["Biotech"]        # its as-of lived in raw.duckdb (#860)


def test_rotation_snapshot_populated(rawstore_tmp_db):
    from datetime import date
    from RevenueChaser.module_sector_rotation.models import ETFRotationSnapshot
    from RevenueChaser.module_sector_rotation import store as rs
    snap = ETFRotationSnapshot(as_of_date=date(2026, 8, 14), ticker="XLK", group_name="sector",
                               close_price=100.0, rs_1w=1.0, rs_1m=2.0, rs_3m=3.0,
                               rs_ratio=2.0, rs_momentum=1.0, rs_ratio_z=1.0, rs_momentum_z=0.5,
                               rrg_quadrant="LEADING")
    rs.save_snapshot([snap], as_of=date(2026, 8, 14))
    data = rs.load_snapshot(date(2026, 8, 14))
    assert data["etfs"][0]["ticker"] == "XLK"
    assert data["etfs"][0]["quadrant"] == "LEADING"
    # regression: quoted-identifier column ("group" is a SQL reserved word) must
    # round-trip — a NULL here blanks the RRG map's sector filter
    assert data["etfs"][0]["group"] == "sector"




def test_watchlist_populated(rawstore_tmp_db):
    rawstore.save_watchlist({"AAPL", "MSFT"})
    assert rawstore.load_watchlist() == {"AAPL", "MSFT"}


def test_swing_info_populated(rawstore_tmp_db, monkeypatch):
    from RevenueChaser.module_swing_potential import indicators
    import yfinance

    class _T:
        def __init__(self, ticker):
            self.info = {"sector": "Technology", "beta": 1.4}

    monkeypatch.setattr(yfinance, "Ticker", _T)
    assert indicators.load_ticker_info("NVDA")["sector"] == "Technology"
    row = rawstore.get("swing_info", "NVDA")
    assert row["payload"]["beta"] == 1.4
    assert row["cached_at"] > 0


def test_rotation_holdings_populated(rawstore_tmp_db):
    from datetime import date
    from RevenueChaser.module_sector_rotation import store as rs
    rs.save_holdings_cache("XLK", [{"ticker": "AAPL", "weight": 0.2}])
    row = rawstore.get("rotation_holdings", "XLK")
    assert row["date"] == date.today().isoformat()
    assert rs.load_holdings_cache("XLK") == [{"ticker": "AAPL", "weight": 0.2}]


































# ── Group B: data is never unwired ───────────────────────────────────────────









def test_same_day_snapshot_overwrites(rawstore_tmp_db):
    from datetime import date
    from RevenueChaser.module_sector_rotation.models import ETFRotationSnapshot
    from RevenueChaser.module_sector_rotation import store as rs

    def _snap(ticker):
        return ETFRotationSnapshot(as_of_date=date(2026, 8, 14), ticker=ticker, group_name="sector",
                                   close_price=100.0, rs_1w=1.0, rs_1m=2.0, rs_3m=3.0,
                                   rs_ratio=2.0, rs_momentum=1.0, rs_ratio_z=1.0, rs_momentum_z=0.5,
                                   rrg_quadrant="LEADING")

    rs.save_snapshot([_snap("XLK")], as_of=date(2026, 8, 14))
    rs.save_snapshot([_snap("XLF")], as_of=date(2026, 8, 14))
    rows = rawstore.query("SELECT ticker FROM rotation_snapshots WHERE as_of_date='2026-08-14'", db="sector_rotation")
    assert [r["ticker"] for r in rows] == ["XLF"]


# ── Group C: every table has a population test ───────────────────────────────
# table -> the pytest nodeid (file::function) that FILLS it. These are checked
# to resolve, so a prose placeholder can no longer pass the gate.
_HERE = "core/tests/test_db_persistence.py"

_ROOT = Path(__file__).resolve().parent.parent.parent

POPULATION: dict[str, str] = {
    "swing_info": f"{_HERE}::test_swing_info_populated",
    "rotation_holdings": f"{_HERE}::test_rotation_holdings_populated",
    "comov_runs": "module_comovement/tests/test_comovement.py"
                   "::test_engine_run_persists_and_clusters",
    "comov_nodes": "module_comovement/tests/test_comovement.py"
                    "::test_engine_run_persists_and_clusters",
    "comov_members": "module_comovement/tests/test_comovement.py"
                      "::test_engine_run_persists_and_clusters",
    "comov_lag": "module_comovement/tests/test_comovement.py"
                  "::test_fetch_persists_the_lagged_test_and_load_payload_returns_it",
    "chain_filings": "module_value_chain/tests/test_value_chain.py"
                      "::test_run_persists_corpus_and_edges",
    "chain_mentions": "module_value_chain/tests/test_value_chain.py"
                       "::test_run_persists_corpus_and_edges",
    "chain_meta": "module_value_chain/tests/test_value_chain.py"
                   "::test_run_persists_corpus_and_edges",
    "store_schema": "core/tests/test_store_schema_stamp.py::test_an_existing_unstamped_file_is_stamped_with_the_current_version",
    "rotation_snapshots": f"{_HERE}::test_rotation_snapshot_populated",
    "ticker_scores": f"{_HERE}::test_ticker_store_populated",
    "ticker_themes": "core/tests/test_ticker_themes.py::test_backfill_writes_legacy_rows",
    "fundamentals_scores": "module_fundamentals/tests/test_fundamental_scores.py::test_persist_writes_both",
    "fundamentals_gates": "module_fundamentals/tests/test_fundamental_scores.py::test_persist_writes_both",
    "swing_scores": "module_swing_potential/tests/test_swing_scores.py::test_persist_writes_both",
    "swing_gates": "module_swing_potential/tests/test_swing_scores.py::test_persist_writes_both",
    "llm_cache": "core/tests/test_relatedness_store.py::test_llm_cache_and_profiles",
    "relatedness_profiles": "core/tests/test_relatedness_store.py::test_llm_cache_and_profiles",
    "relatedness_embeddings": "core/tests/test_schema_v13_relatedness.py::test_the_new_columns_hold_json_and_the_vector_holds_bytes",
    "relatedness_attributes": "core/tests/test_relatedness_store.py::test_relatedness_attributes_and_scores",
    "relatedness_scores": "core/tests/test_relatedness_store.py::test_relatedness_attributes_and_scores",
    "theme_runs": "module_relatedness/tests/test_themes.py::test_build_shadow_writes_nested_themes",
    "relatedness_themes": "module_relatedness/tests/test_themes.py::test_build_shadow_writes_nested_themes",
    "relatedness_theme_tags": "module_relatedness/tests/test_themes.py::test_build_shadow_writes_nested_themes",
    "relatedness_theme_members": "module_relatedness/tests/test_themes.py::test_build_shadow_writes_nested_themes",
    "relatedness_theme_etfs": "module_relatedness/tests/test_themes.py::test_match_theme_etfs",
    "oipd_chain": "module_oipd/tests/test_engine.py::test_oipd_store_populated",
    "oipd_meta": "module_oipd/tests/test_engine.py::test_oipd_store_populated",
    "forecast_ledger": "core/tests/test_schema_v8_migration.py::test_forecast_ledger_first_write_wins_within_one_bulk_batch",
    "forecast_outcomes": "core/tests/test_outcomes.py::test_mfe_and_mae_are_high_and_low_over_exactly_the_window_from_the_next_open",
    "forecast_baselines": "core/tests/test_baselines_numbers_25.py::test_a_baselines_run_populates_forecast_baselines",
    "news_events": "module_news/tests/test_calendar.py::test_first_build_upserts_every_event_into_the_board_file",
    "news_earnings": "module_news/tests/test_earnings_886.py::test_the_pass_writes_one_row_a_watch_list_name_reporting_next_week",
    "news_highlight": "module_news/tests/test_calendar.py::test_the_highlight_is_the_most_important_live_event_earliest_on_a_tie",
    "news_meta": "module_news/tests/test_calendar.py::test_a_second_build_reads_only_new_rows_and_keeps_first_seen",
    "news_headlines": "module_news/tests/test_headlines.py::test_fetch_stores_clean_headlines_with_their_tickers_once",
    "welcome_snapshot": "module_welcome/tests/test_build.py::test_the_snapshot_keeps_the_last_close_its_change_and_a_20_day_line",
    "spx_raw_days": "module_spx_gamma/tests/test_store.py::test_a_raw_day_round_trips_byte_exact",
    "spx_raw_files": "module_spx_gamma/tests/test_store.py::test_a_replaced_day_keeps_no_old_file",
    "spx_brier": "module_spx_gamma/tests/test_store.py::test_a_scored_brier_record_is_never_changed",
    "spx_gex_daily": "module_spx_gamma/tests/test_store.py::test_every_gex_day_is_kept",
    "spx_meta": "module_spx_gamma/tests/test_store.py::test_meta_round_trips",
    "sec13f_board_cells": "module_sec_13f/tests/test_sec13f_board_file_732.py::test_a_sync_writes_the_builders_rows_and_the_board_then_reads_the_file",
    "sec13f_board_breaks": "module_sec_13f/tests/test_sec13f_board_file_732.py::test_a_sync_writes_the_builders_rows_and_the_board_then_reads_the_file",
    "sec13f_board_meta": "module_sec_13f/tests/test_sec13f_board_file_732.py::test_a_sync_writes_the_builders_rows_and_the_board_then_reads_the_file",
    "wl_list": "module_watchlists/tests/test_watchlist_store_786.py::test_a_new_list_gets_a_slug_id_a_description_and_a_default_section",
    "wl_section": "module_watchlists/tests/test_watchlist_store_786.py::test_sections_keep_avos_order_not_the_alphabet",
    "wl_item": "module_watchlists/tests/test_watchlist_store_786.py::test_a_symbol_is_stored_as_avo_wrote_it_split_into_its_parts",
    "wl_change": "module_watchlists/tests/test_watchlist_store_786.py::test_every_add_and_remove_leaves_a_change_row",
    "welcome_earnings":
        "module_welcome/tests/test_build.py::test_the_earnings_card_is_written_from_the_screeners_newest_session",
    "welcome_freshness":
        "module_welcome/tests/test_build.py::test_the_freshness_rows_are_the_builder_files_not_the_dashboard_jobs",
}


#: Board tables nothing writes. #643 PR 5b and PR 6 gave Welcome's earnings and freshness cards their new writers
#: (the options screener, and the builder's run ledger in ops), and emptied this set; a table that loses its writer
#: goes in here with the issue that will give it one.
#:
#: ``welcome_meta`` was in ``POPULATION`` instead, pointed at Welcome's **snapshot** test, which does not touch it:
#: nothing has ever written the table (``module_welcome/build``'s own docstring says why, and its dead ``_meta`` /
#: ``_set_meta`` helpers went with #643). The gate was therefore satisfied by an entry that could not be true, so
#: the table is named here, where the claim is the honest one.
UNWRITTEN: frozenset[str] = frozenset({"welcome_meta"})


def test_every_manifest_table_has_a_population_test():
    missing = [t for t in rawstore.MANIFEST if t not in POPULATION and t not in UNWRITTEN]
    assert not missing, f"tables without a population test: {sorted(missing)}"


def test_population_entries_point_at_tests_that_exist():
    """The gate has to bite: a free-text placeholder used to satisfy it."""
    broken = []
    for table, nodeid in sorted(POPULATION.items()):
        path, sep, func = nodeid.partition("::")
        f = _ROOT / path
        if not sep or not f.exists():
            broken.append(f"{table}: {nodeid} — file not found")
            continue
        if f"def {func}(" not in f.read_text(encoding="utf-8"):
            broken.append(f"{table}: {nodeid} — no such test function")
    assert not broken, "POPULATION must name real tests:\n" + "\n".join(broken)


def test_manifest_tables_start_empty_in_an_isolated_db(rawstore_tmp_db):
    """Sanity for the autouse isolation fixture: no test may see another's rows,
    and none may see the developer's real store."""
    for table in rawstore.MANIFEST:
        if table == "store_schema":     # #26 PL7: every ensure stamps each board file's own schema version
            for db in rawstore.BOARD_DBS:
                (row,) = rawstore.query("SELECT value FROM store_schema WHERE key = 'schema_version'", db=db)
                assert row["value"] == rawstore.schema_version()
            continue
        assert rawstore.count(table) == 0, f"{table} leaked state across tests"


# ── Group D: TTL / no_fetch behaviour ────────────────────────────────────────



def test_swing_info_ttl_from_cached_at(rawstore_tmp_db):
    import time
    from RevenueChaser.core import rawstore as rs
    rs.write_rows("swing_info", [{"ticker": "AAAA", "payload": {"sector": "Tech"},
                                  "cached_at": time.time() - 1000}])
    from RevenueChaser.module_swing_potential.indicators import load_ticker_info
    assert load_ticker_info("AAAA", no_fetch=True) == {"sector": "Tech"}
