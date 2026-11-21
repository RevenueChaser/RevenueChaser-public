"""#446 steps 3 and 4 over the harder trees: a security's other share classes, a fund's aliases, the changes that
force a whole build, and the splits that restate the caps after them.

Each is the same metamorphic proof as ``test_prices_incremental.py`` -- the build on the live copy must serve what a
whole build serves (``prices_incremental_world._same_as_whole``) -- over the alphabet of classes, SPY's series, or a
split in the staging margin. Split from that file in #1153, because one file of 338 s set how short the unit tier
could run.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from RevenueChaser.rcdata import serving
from RevenueChaser.rcdata.build import base, dirty
from RevenueChaser.rcdata.build.prices import incremental, stage, wrds_history

from .prices_incremental_world import (
    GOOGL, OCT, SPINE, SPYX, _aapl_day, _build, _clock, _note, _q, _respine, _same_as_whole, _secd_rows, _serve,
    _snapshot, _spy, _spy_spine, _write_secd, alphabet, env, fake, live
)  # noqa: F401 (the shared world: its helpers, and every fixture a test's own fixtures ask for -- `env` is
#  autouse and runs only where it is in the namespace, `fake` is what `live` is built on)


def _alpaca_split(template: dict, rate: float) -> dict:
    return {**template, "action_id": "sp-1", "action_type": "forward_split", "symbol": "AAPL",
            "ex_date": date(2025, 6, 4), "process_date": date(2025, 6, 4), "effective_date": date(2025, 6, 4),
            "old_rate": 1.0, "new_rate": rate, "rate": None, "special": False, "foreign": False, "sub_type": None,
            "currency": None, "payload": "{}"}


@pytest.fixture
def no_split(fake, monkeypatch):
    """No Compustat split anywhere, so CRSP's split of AAPL is the cross-check's only one."""
    conn = fake[0]
    conn.data["comp.sec_split"] = []
    conn.data["comp.secd"] = [{**r, "ajexdi": 1.0} for r in conn.data["comp.secd"]]
    _build()
    monkeypatch.setenv(dirty.WHOLE_ENV, "1")
    _serve()
    monkeypatch.delenv(dirty.WHOLE_ENV)
    assert "built on the live file" in _note(_serve())
    return fake


@pytest.fixture
def december_split(fake, monkeypatch):
    """A CRSP-only 2:1 step of AAPL on 23 Dec 2024, with served bars on both sides."""
    from .test_prices_wrds import _secd
    conn = fake[0]
    conn.data["comp.sec_split"] = []
    conn.data["comp.secd"] = [{**r, "ajexdi": 1.0} for r in conn.data["comp.secd"]] + [
        _secd("001690", "01", d, "AAPL", c) for d, c in (("2024-12-19", 101.0), ("2024-12-20", 100.0),
                                                          ("2024-12-23", 50.0), ("2024-12-24", 50.5))]
    row = conn.data["crsp.dsf_v2"][0]
    conn.data["crsp.dsf_v2"] = conn.data["crsp.dsf_v2"] + [
        {**row, "dlycaldt": d, "dlyprc": c, "dlyret": 0.0, "dlycumfacpr": f}
        for d, c, f in (("2024-12-19", 101.0, 4.0), ("2024-12-20", 100.0, 4.0), ("2024-12-23", 50.0, 2.0),
                        ("2024-12-24", 50.5, 2.0))]
    _build()
    monkeypatch.setenv(dirty.WHOLE_ENV, "1")
    _serve()
    monkeypatch.delenv(dirty.WHOLE_ENV)
    assert "built on the live file" in _note(_serve())
    # The served closes jump across it (100.0 -> 50.0), so it is applied from CRSP and named as such (#661).
    assert ("split_applied_crsp", "001690:01:2024-12-23") in _snapshot()["open issues"]
    return fake


def test_a_class_whose_issuer_changes_restates_the_other_classes_issuer_cap(alphabet, monkeypatch):
    """GOOG moves to another CIK in the spine: its own caps keep their values, but GOOGL's issuer cap loses GOOG on
    every session, which only the closure over the issuer reaches (GOOGL itself changed nothing)."""
    from .prices_fixture import ALPHABET
    _respine(SPINE + [{**r, "cik": "9999999"} if r["ticker"] == "GOOG" else r for r in ALPHABET])
    row = _serve()
    caps = _q("SELECT market_cap, issuer_market_cap FROM market_cap_daily WHERE security_id = ? "
              "AND session_date = ?", [GOOGL, OCT[0]])
    assert caps[0]["issuer_market_cap"] == caps[0]["market_cap"]
    _same_as_whole(monkeypatch, row)


def test_a_new_day_of_one_class_counts_the_others_last_cap(alphabet, monkeypatch):
    day = date(2026, 10, 28)
    template = [r for r in _secd_rows(2026) if r["gvkey"] == "160329" and r["iid"] == "01"][-1]
    _write_secd(2026, _secd_rows(2026) + [{**template, "datadate": day, "source_as_of": day}])
    _clock(day)
    row = _serve()
    caps = _q("SELECT market_cap, issuer_market_cap FROM market_cap_daily WHERE security_id = ? "
              "AND session_date = ?", [GOOGL, day])
    assert caps[0]["issuer_market_cap"] > caps[0]["market_cap"]                    # GOOG's cap of the 27th
    _same_as_whole(monkeypatch, row)


def test_a_rebuilt_day_counts_a_class_whose_last_cap_is_older(alphabet, monkeypatch):
    """A cover of GOOGL as of the 26th rebuilds GOOGL and GOOG from that day only. GOOGL's issuer cap of the 26th
    still counts GOOG at its cap of the 23rd, a bar the rebuild does not reload."""
    from RevenueChaser.rcdata.build.prices import cover_shares
    path = cover_shares.partition_path(2026)
    rows = stage.read_rows(path) + [{
        "cik": "1652044", "accession": "0001652044-26-000099", "form": "8-K", "filed": date(2026, 10, 27),
        "period_end": date(2026, 9, 30), "class_member": "us-gaap:CommonClassAMember", "symbol": "GOOGL",
        "shares": 5_790_000_000.0, "as_of": OCT[3], "source_as_of": date(2026, 10, 27), "fetched_at": 9.0,
        "run_id": "c-googl"}]
    stage.write_rows(rows, cover_shares.SCHEMA, path)
    row = _serve()
    assert "rebuilt from 2026-10-28" in _note(row), _note(row)
    caps = _q("SELECT market_cap, issuer_market_cap FROM market_cap_daily WHERE security_id = ? "
              "AND session_date = ?", [GOOGL, OCT[3]])
    assert caps[0]["issuer_market_cap"] > caps[0]["market_cap"]
    _same_as_whole(monkeypatch, row)


def test_a_changed_exchange_history_forces_a_whole_build(live, monkeypatch):
    from RevenueChaser.rcdata.build.spine import wrds
    target = wrds.parquet_dir("wrds/sec_idhist") / "snapshot=2026-10-01" / "sec_idhist.parquet"
    stage.write_rows([{"gvkey": "001690", "iid": "01", "item": "EXCHG", "itemvalue": "14",
                       "efffrom": date(2000, 1, 3), "effthru": None, "source_as_of": date(2026, 10, 1),
                       "fetched_at": 1.0, "run_id": "x"}],
                     [("gvkey", "TEXT"), ("iid", "TEXT"), ("item", "TEXT"), ("itemvalue", "TEXT"),
                      ("efffrom", "DATE"), ("effthru", "DATE"), ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"),
                      ("run_id", "TEXT")], target)
    row = _serve()
    assert "built whole" in _note(row) and "sec_idhist" in _note(row), _note(row)


def test_a_new_split_snapshot_the_monthly_refresh_forces_a_whole_build(live):
    rows = [{"gvkey": "001690", "iid": "01", "datadate": date(2025, 6, 4), "split": 2.0,
             "source_as_of": date(2026, 10, 28), "fetched_at": 2.0, "run_id": "monthly"}]
    stage.write_rows(rows, wrds_history.SPLIT + wrds_history.PROVENANCE,
                     wrds_history.snapshot_path("sec_split", date(2026, 10, 28)))
    row = _serve()
    assert "built whole" in _note(row) and "monthly WRDS refresh" in _note(row), _note(row)


def test_every_prices_dataset_declares_a_dirty_set():
    assert dirty.incremental(base.kind_datasets("prices"))


def test_a_corrected_alpaca_split_ratio_restates_the_caps_after_it(live, monkeypatch):
    """Review S3: the same split on the same day with another ratio moves every cover cap after it."""
    from RevenueChaser.rcdata.build.prices import actions, cover_shares
    _write_secd(2025, [{**r, "cshoc": None} if r["gvkey"] == "001690" else r for r in _secd_rows(2025)])
    cpath = cover_shares.partition_path(2026)
    stage.write_rows(stage.read_rows(cpath) + [{
        "cik": "320193", "accession": "0000320193-25-000001", "form": "10-Q", "filed": date(2025, 5, 1),
        "period_end": date(2025, 3, 29), "class_member": "", "symbol": "AAPL", "shares": 7_500_000_000.0,
        "as_of": date(2025, 4, 18), "source_as_of": date(2025, 5, 1), "fetched_at": 9.0, "run_id": "c-x"}],
        cover_shares.SCHEMA, cpath)
    template = stage.read_rows(actions.partition_path(2026))[0]
    path = actions.partition_path(2025)
    stage.write_rows([_alpaca_split(template, 4.0)], actions.SCHEMA, path)
    monkeypatch.setenv(dirty.WHOLE_ENV, "1")
    _serve()
    monkeypatch.delenv(dirty.WHOLE_ENV)
    stage.write_rows([_alpaca_split(template, 2.0)], actions.SCHEMA, path)
    row = _serve()
    _same_as_whole(monkeypatch, row)


def test_a_dividend_moved_to_a_later_day_leaves_no_copy_on_the_old_one(live, monkeypatch):
    """Review S4: the rewritten year starts after the row it lost; the window starts at the partition's first day."""
    path = wrds_history.partition_path("sec_divid", 2025)
    rows = stage.read_rows(path)
    assert rows
    stage.write_rows([{**r, "datadate": date(2025, 6, 6)} for r in rows], wrds_history.DIVID + wrds_history.PROVENANCE,
                     path)
    row = _serve()
    _same_as_whole(monkeypatch, row)


def test_a_changed_permno_link_finds_the_crsp_issues_again(no_split, monkeypatch):
    """Review S5: the spine loses AAPL's CUSIP, so CRSP's PERMNO is no longer AAPL's by id; which CRSP split counts
    moves on old days, and so do the issues it decides."""
    _respine([{**r, "cusip": None} if r["ticker"] == "AAPL" else r for r in SPINE])
    row = _serve()
    _same_as_whole(monkeypatch, row)


@pytest.mark.parametrize("extra", [(), (SPYX,)], ids=["no-cik", "with-cik"])
def test_a_new_alias_moves_a_served_series_under_the_fund(fake, monkeypatch, extra):
    """Review B2: SPY's series is served under its gvkey until CRSP's link makes it the FIGI's alias; its old rows
    must go, whatever the series' issuer."""
    _spy(fake, monkeypatch, extra)
    assert _q("SELECT 1 FROM price_bar_daily WHERE security_id = '001000:01'")
    _spy_spine(date(1993, 1, 22), extra)
    row = _serve()
    assert not _q("SELECT 1 FROM price_bar_daily WHERE security_id = '001000:01'")
    _same_as_whole(monkeypatch, row)


def test_a_security_with_no_issuer_is_not_rebuilt_on_every_build(fake, monkeypatch):
    """Review S7: a served cap with no CIK is not an issuer change."""
    _spy(fake, monkeypatch)
    row = _serve()
    assert "0 securities whole" in _note(row), _note(row)


def test_nothing_changed_rebuilds_no_security_whole(live):
    row = _serve()
    assert "0 securities whole" in _note(row), _note(row)


def test_the_first_build_on_a_file_without_its_bookkeeping_serves_what_a_whole_build_does(live, monkeypatch):
    """The live file on homesrv when this lands: no manifest, no rules, no identity. The build falls back to the
    file times and the served ids, once."""
    import duckdb
    import time
    con = duckdb.connect(str(serving.live_path("prices")))
    try:
        for t in (dirty.MANIFEST_TABLE, dirty.RULES_TABLE, incremental.IDENTITY_TABLE):
            con.execute(f"DROP TABLE IF EXISTS {t}")
    finally:
        con.close()
    time.sleep(1.2)
    day = date(2026, 10, 28)
    _write_secd(2026, _secd_rows(2026) + [_aapl_day(day, 203.0)])
    _clock(day)
    row = _serve()
    _same_as_whole(monkeypatch, row)


def test_an_open_issue_near_the_window_is_found_again_not_kept():
    sc = incremental.Scope(since=date(2026, 10, 28), margin={"split_only_crsp": 10})
    assert not sc.keep("split_only_crsp", "001690:01:2026-10-20")
    assert sc.keep("split_only_crsp", "001690:01:2026-10-17")
    assert sc.keep("price_gap_no_action", "001690:01:2026-10-20")


def test_an_alpaca_split_days_after_a_crsp_one_resolves_its_issue(no_split, monkeypatch):
    """Review S6: CRSP's split of AAPL is the cross-check's only one until Alpaca's split two days later; that
    rebuilds AAPL from its own ex-date, but the CRSP split it explains lies before it."""
    from RevenueChaser.rcdata.build.prices import actions
    crsp = [k for kind, k in _snapshot()["open issues"] if kind in ("split_only_crsp", "split_applied_crsp")]
    assert crsp, "the fixture has a CRSP-only split"
    day = date.fromisoformat(crsp[0].rsplit(":", 1)[1])
    template = stage.read_rows(actions.partition_path(2026))[0]
    split = {**_alpaca_split(template, 4.0), "ex_date": day + timedelta(days=2), "process_date": day + timedelta(days=2),
             "effective_date": day + timedelta(days=2)}
    stage.write_rows([split], actions.SCHEMA, actions.partition_path(day.year))
    row = _serve()
    _same_as_whole(monkeypatch, row)


def test_a_crsp_split_in_the_margin_before_the_staging_cut_is_staged(december_split, monkeypatch):
    """Delta review 1 of #564: AAPL rebuilt from 2 Jan 2025 (the cut is 1 Jan) looks for CRSP splits ten days
    before; the one of 23 Dec needs its rows from before the cut staged."""
    from RevenueChaser.rcdata.build.prices import actions
    template = stage.read_rows(actions.partition_path(2026))[0]
    div = {**template, "action_id": "cd-x", "ex_date": date(2025, 1, 2), "process_date": date(2025, 1, 2),
           "effective_date": date(2025, 1, 2), "rate": 0.05}
    stage.write_rows([div], actions.SCHEMA, actions.partition_path(2025))
    row = _serve()
    _same_as_whole(monkeypatch, row)
