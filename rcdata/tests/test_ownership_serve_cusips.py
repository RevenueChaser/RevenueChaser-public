"""``ownership/serve``: how a 13F CUSIP is named -- Compustat's dated table, then the spine's current CUSIP, then
OpenFIGI behind the reused-ticker guard -- and what becomes of one that no source names or that two sources claim.

The world is ``ownership_serve_world`` (#1153); the served tables are ``test_ownership_serve.py``.
"""

from __future__ import annotations

import json
from datetime import date

import duckdb

from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.ownership import common, sec, sec13f, sec13f_list
from RevenueChaser.rcdata.build.spine import wrds

from . import ownership_fixture as ox
from .ownership_serve_world import (
    MSFT_OLD, NOBODY, OLD_VYLR, Q2, Q3, WFC_PC, _book, _book_day, _f, _h, _issues, _serve, _served, _thirteen_f,
    built, store
)  # noqa: F401 (the shared world: its helpers and the fixtures a test asks for by name)


def test_the_openfigi_map_asks_the_newest_quarters_13f_cusips_no_other_source_holds(store, built):
    asked = {j["idValue"] for c in built.calls("figi.test/v3/mapping") for j in json.loads(c.content)}
    assert asked == {OLD_VYLR, NOBODY, WFC_PC}         # not MSFT's 2001 CUSIP: only the two newest periods


def test_the_recent_cusips_read_only_the_holdings_filed_after_the_older_of_the_two_periods(store, monkeypatch):
    """Review S5: the weekly OpenFIGI run asks the two newest quarters' CUSIPs; it must not scan every holdings
    partition ever written (about 50 million rows after the 2025 fill) to find them."""
    read_days = []
    real = common.files_sql

    def spy(files):
        read_days.extend(f.parent.name for f in files if f.parent.parent.name == "holdings")
        return real(files)
    monkeypatch.setattr(common, "files_sql", spy)
    cusips = sec13f.recent_cusips()
    assert {"594918104", OLD_VYLR, WFC_PC} <= cusips and MSFT_OLD not in cusips
    assert sorted(read_days) == ["day=2026-08-14", "day=2026-10-27"]          # not 2001-11-14


def test_the_recent_cusips_keep_a_report_filed_on_the_older_periods_own_end_day(store):
    """Delta review D5: the partition cut keeps the older period's end day itself; a holding filed that day is
    still one of the period's CUSIPs for OpenFIGI to name."""
    holdings = sec13f.DATASET.parquet_dir() / "holdings"
    (holdings / "day=2026-06-30").mkdir()
    con = duckdb.connect()
    try:
        con.execute(f"COPY (SELECT * REPLACE ('99999X101' AS cusip) "
                    f"FROM read_parquet({base.sql_path(holdings / 'day=2026-08-14' / 'part-0.parquet')}) "
                    f"WHERE period = DATE '{Q2}' LIMIT 1) "
                    f"TO {base.sql_path(holdings / 'day=2026-06-30' / 'part-0.parquet')} (FORMAT parquet)")
    finally:
        con.close()
    assert "99999X101" in sec13f.recent_cusips()


def test_each_cusip_is_named_with_its_source_and_none_is_dropped(store):
    assert _served("SELECT cusip, period, ticker, map_source, candidate_ticker, value, holders "
                   "FROM sec13f_cusip_map ORDER BY period, cusip") == [
        (MSFT_OLD, date(2001, 9, 30), "MSFT", "wrds/sec_idhist", None, 6_000.0, 1),
        ("594918104", Q2, "MSFT", "spine/security", None, 520_000.0, 2),
        ("G29183103", Q2, "ETN", "spine/security", None, 180_000.0, 2),
        ("422806109", Q3, "HEI", "spine/security", None, 20_000.0, 1),
        ("422806208", Q3, "HEI-A", "wrds/sec_idhist", None, 16_000.0, 1),
        ("594918104", Q3, "MSFT", "spine/security", None, 620_000.0, 2),
        ("62944T105", Q3, "NVR", "spine/security", None, 250_000.0, 1),
        (OLD_VYLR, Q3, None, "refused", "VYLR", 1_000.0, 1),
        ("949746101", Q3, "WFC", "spine/security", None, 10_000.0, 1),
        (WFC_PC, Q3, "WFC-PC", "openfigi/map", None, 250.0, 1),
        (NOBODY, Q3, None, None, None, 500.0, 1),
        ("G29183103", Q3, "ETN", "spine/security", None, 160_000.0, 1)]


def test_an_old_companys_cusip_openfigi_gives_a_reused_ticker_is_refused_and_an_issue(store):
    """#236 in 13F: OpenFIGI names VYLR for the old company's CUSIP; Compustat gives that CUSIP to gvkey 123456,
    and VYLR is linked to 040001 today. The holding stays in the map unnamed, never VYLR's, and is one issue."""
    assert not _served("SELECT * FROM sec13f_ticker_period WHERE ticker = 'VYLR'")
    detail = _issues()[("cusip_owner_differs", OLD_VYLR)]
    assert "VYLR" in detail and "123456/01" in detail and "040001/01" in detail


def test_the_largest_unmapped_cusips_are_those_of_the_newest_complete_quarter(store):
    """Review N2: on 28 Oct 2026 the 30 Sep quarter is still filling (deadline 16 Nov); the list describes 30 Jun,
    where every CUSIP is named, as the plan's counts do. Once the deadline has passed it describes 30 Sep."""
    assert not [key for kind, key in _issues() if kind == "cusip_unmapped_large"]
    _serve("2026-11-17")
    issues = _issues()
    assert issues[("cusip_unmapped_large", NOBODY)].startswith("2026-09-30: NOBODY KNOWS INC")
    assert ("cusip_unmapped_large", OLD_VYLR) not in issues                   # refused, not unmapped


def test_a_current_cusip_compustat_gave_another_security_in_the_period_is_refused_there_only(store):
    """Review S1 (#236 on the current-CUSIP branch): Compustat's dated history gives MSFT's CUSIP to the old Vaylor
    security from January to July 2026. The spine's current CUSIP names MSFT; for 30 Jun 2026 that is refused, kept
    unnamed and one issue, and 30 Sep 2026 (after the other security's dates) stays MSFT's. The issue names the
    security that held the CUSIP in the refused period, not one that held it years before (delta review D3)."""
    folder = wrds.parquet_dir(wrds.SEC_IDHIST.name) / "delta=9999-12-31"
    folder.mkdir(parents=True)
    con = duckdb.connect()
    try:
        con.execute(f"COPY (SELECT '123456' AS gvkey, '01' AS iid, 'CUSIP' AS item, '594918104' AS itemvalue, "
                    f"DATE '2026-01-01' AS efffrom, DATE '2026-07-31' AS effthru "
                    f"UNION ALL SELECT '654321', '01', 'CUSIP', '594918104', DATE '2010-01-01', DATE '2012-12-31') "
                    f"TO {base.sql_path(folder / 'sec_idhist.parquet')} (FORMAT parquet)")
    finally:
        con.close()
    _serve(allow_shrink=True)                       # MSFT's 30 Jun 2026 row goes: more than the 1% the swap allows
    assert _served("SELECT period, ticker, map_source, candidate_ticker FROM sec13f_cusip_map "
                   "WHERE cusip = '594918104' ORDER BY period") == [(Q2, None, "refused", "MSFT"),
                                                                    (Q3, "MSFT", "spine/security", None)]
    detail = _issues()[("cusip_owner_differs", "594918104")]
    assert "the spine's current CUSIP names MSFT (012141/01)" in detail
    assert "Compustat gives the CUSIP to 123456/01 in those periods: 1 period(s), $520,000 kept unnamed" in detail
    assert _served("SELECT period FROM sec13f_ticker_period WHERE ticker = 'MSFT' ORDER BY period") == [
        (date(2001, 9, 30),), (Q3,)]


def test_a_cusip_is_named_through_compustats_owner_in_the_period(store):
    """#278: Compustat moved MSFT's CUSIP to it only on 1 Aug 2026; before that it was Wells Fargo's (008007/01, a
    spine row). The spine's current CUSIP is refused for 30 Jun and Compustat's owner names it WFC there; 30 Sep stays
    MSFT's. NOBODY's CUSIP no spine CUSIP holds is NVR's (025648/01) in Compustat's history: named NVR. Neither is
    a ``cusip_owner_differs`` issue any more."""
    folder = wrds.parquet_dir(wrds.SEC_IDHIST.name) / "delta=9999-12-31"
    folder.mkdir(parents=True)
    con = duckdb.connect()
    try:
        con.execute(f"COPY (SELECT '008007' AS gvkey, '01' AS iid, 'CUSIP' AS item, '594918104' AS itemvalue, "
                    f"DATE '2026-01-01' AS efffrom, DATE '2026-07-31' AS effthru "
                    f"UNION ALL SELECT '012141', '01', 'CUSIP', '594918104', DATE '2026-08-01', NULL "
                    f"UNION ALL SELECT '025648', '01', 'CUSIP', '{NOBODY}', DATE '2020-01-01', NULL) "
                    f"TO {base.sql_path(folder / 'sec_idhist.parquet')} (FORMAT parquet)")
    finally:
        con.close()
    _serve(allow_shrink=True)
    assert _served("SELECT cusip, period, ticker, map_source, candidate_ticker FROM sec13f_cusip_map "
                   "WHERE cusip IN ('594918104', ?) ORDER BY cusip, period", NOBODY) == [
        ("594918104", Q2, "WFC", "compustat/owner", None), ("594918104", Q3, "MSFT", "spine/security", None),
        (NOBODY, Q3, "NVR", "compustat/owner", None)]
    issues = _issues()
    assert ("cusip_owner_differs", "594918104") not in issues and ("cusip_unmapped_large", NOBODY) not in issues


def test_an_eight_digit_cusip_that_lost_its_leading_zero_gets_it_back_when_its_check_digit_agrees(monkeypatch,
                                                                                                   http_mock):
    """#937, live v4: 54,086 CUSIP rows under nine characters, none mapped; '37833100' is AAPL's 037833100."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    filers = [_f(f"000200000{i}-26-00000{i}", 2000000 + i, "2026-10-27", _book()) for i in range(1, 4)]
    short = _book()
    short[4] = _h("APPLE INC", "37833100", 23_000, 100)                                 # the zero dropped
    short.append(_h("NOT A CUSIP", "12345678", 1_000, 10))                             # check digit wrong: kept
    filers.append(_f("0002000004-26-000004", 2000004, "2026-10-27", short))
    e.add_day("2026-10-27", filers)
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")
    _serve()
    assert _served("SELECT holders FROM sec13f_cusip_map WHERE cusip = '037833100'") == [(4,)]
    assert _served("SELECT cusip FROM sec13f_cusip_map WHERE length(cusip) < 9") == [("12345678",)]


def test_a_quarters_cusips_not_on_the_13f_list_are_counted_not_dropped(monkeypatch, http_mock):
    """#926: the SEC's 13(f) list for the quarter marks a CUSIP it does not hold; nothing leaves the totals."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    _book_day(http_mock, {"2026-10-27": [(1.0, "09-30-2026")] * 4})
    _serve()
    held = _served("SELECT cusip, value FROM sec13f_cusip_map WHERE period = DATE '2026-09-30' ORDER BY value DESC")
    totals = _served("SELECT ticker, value FROM sec13f_ticker_period ORDER BY ticker")
    (top, top_value), rest = held[0], held[1:]
    sec13f_list.raw_dir().mkdir(parents=True, exist_ok=True)
    (sec13f_list.raw_dir() / "2026q3.txt").write_bytes(b"".join(
        f"{c} {'ISSUER':<30}{'COM':<39}E\n".encode() for c, _ in rest)
        + f"{top} {'DELETED':<30}{'COM':<20}*D*{'':<16}E\n".encode())
    sec13f_list.DATASET.to_parquet_all(base.RunContext(run_id="l1", dataset=sec13f_list.NAME), [])
    _serve()
    detail = _issues()[("cusip_not_listed", "2026-09-30")]
    assert detail.startswith(f"2026-09-30: 1 of {len(held)} CUSIP(s), ${top_value:,.0f} of ")
    assert f"; the largest {top} (" in detail
    assert _served("SELECT ticker, value FROM sec13f_ticker_period ORDER BY ticker") == totals
