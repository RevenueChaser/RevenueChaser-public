"""``sec/nport`` (#354 C1): the SEC's Form N-PORT data sets, newest listed quarter only, streamed to disk and typed
to two Parquet files (the series, the holdings); no served table yet. Offline: the page and the zips are fixtures."""
from __future__ import annotations

import io
from datetime import date
from types import SimpleNamespace
import zipfile

import duckdb
import pytest

from revenuechaser.core.providers import sec_edgar
from revenuechaser.rcdata import ops
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.ownership import common, nport, sec
from revenuechaser.rcdata.build.spine import ncen

from . import ownership_fixture as ox

FOLDER = "/files/dera/data/form-n-port-data-sets/"
NEW, OLD = "2026q3_nport.zip", "2026q2_nport.zip"

TABLES = {
    "SUBMISSION": ("ACCESSION_NUMBER", "FILING_DATE", "SUB_TYPE", "REPORT_ENDING_PERIOD", "REPORT_DATE"),
    "REGISTRANT": ("ACCESSION_NUMBER", "CIK", "REGISTRANT_NAME"),
    "FUND_REPORTED_INFO": ("ACCESSION_NUMBER", "SERIES_NAME", "SERIES_ID", "TOTAL_ASSETS", "NET_ASSETS"),
    "FUND_REPORTED_HOLDING": ("ACCESSION_NUMBER", "HOLDING_ID", "ISSUER_NAME", "ISSUER_LEI", "ISSUER_TITLE",
                              "ISSUER_CUSIP", "BALANCE", "UNIT", "CURRENCY_CODE", "CURRENCY_VALUE", "PERCENTAGE",
                              "PAYOFF_PROFILE", "ASSET_CAT", "ISSUER_TYPE", "INVESTMENT_COUNTRY"),
    "IDENTIFIERS": ("HOLDING_ID", "IDENTIFIER_ISIN", "IDENTIFIER_TICKER"),
}
ROWS = {
    "SUBMISSION": [("0000001-26-000001", "28-AUG-2026", "NPORT-P", "31-DEC-2026", "30-JUN-2026")],
    "REGISTRANT": [("0000001-26-000001", "0000036405", "VANGUARD INDEX FUNDS")],
    "FUND_REPORTED_INFO": [("0000001-26-000001", "Vanguard Total Stock Market", "S000002848", "1,000.5", "990")],
    "FUND_REPORTED_HOLDING": [
        ("0000001-26-000001", "11", "Microsoft Corp", "INR2EJN1ERAN0W5ZP974", "Microsoft Corp", "594918104",
         "100", "NS", "USD", "40000", "4.04", "Long", "EC", "CORP", "US"),
        ("0000001-26-000001", "12", "Cash collateral", "N/A", "Cash", "N/A", "1", "PA", "USD", "5", "0.01", "Long",
         "STIV", "RF", "US"),
        ("0000001-26-000001", "13", "Odd Corp", "", "Odd", "000000000", "", "NS", "EUR", "x", "", "Short", "EC",
         "CORP", "DE")],
    "IDENTIFIERS": [("11", "US5949181045", "msft"), ("11", "US5949181045", "MSFT2"), ("13", "DE0000000001", "")],
}


def _zip(tables=TABLES, rows=ROWS) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for t, cols in tables.items():
            z.writestr(f"{t}.tsv", "\n".join("\t".join(r) for r in [cols, *rows.get(t, [])]) + "\n")
    return buf.getvalue()


@pytest.fixture
def sets(monkeypatch, http_mock):
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    http_mock.add(nport.INDEX_PATH, ox.sets_page([FOLDER + OLD, FOLDER + NEW]))
    http_mock.add(FOLDER + NEW, _zip(), headers={"last-modified": "Mon, 02 Nov 2026 10:00:00 GMT"})
    http_mock.add(FOLDER + OLD, _zip())
    return http_mock


def _run() -> tuple[base.RunContext, list]:
    ctx = base.RunContext(run_id="r1", dataset=nport.NAME, sleep=lambda s: None)
    out = nport.DATASET.to_parquet_all(ctx, nport.DATASET.fetch(ctx, nport.DATASET.default_as_of()))
    return ctx, out


def _issues() -> list[tuple]:
    return [(r["kind"], r["detail"]) for r in ops.rows("build_issues")]


def _read(name: str, sql: str) -> list[tuple]:
    path = nport.parquet_dir() / "quarter=2026q3" / name
    return duckdb.connect().execute(sql.replace("{t}", f"read_parquet('{path}')")).fetchall()


def test_only_the_newest_set_is_fetched_and_typed(sets):
    ctx, out = _run()
    assert [str(r.url).rsplit("/", 1)[1] for r in sets.calls(FOLDER)] == [NEW]
    assert (nport.raw_dir() / NEW).exists() and not (nport.raw_dir() / (NEW + ".tmp")).exists()
    assert nport.typed(NEW) and len(out) == 2
    assert _read("fund.parquet", "SELECT quarter, cik, registrant, series_id, form, filed, report_date, total_assets, "
                                 "net_assets, run_id FROM {t}") == [
        ("2026q3", "36405", "VANGUARD INDEX FUNDS", "S000002848", "NPORT-P", date(2026, 8, 28),
         date(2026, 6, 30), 1000.5, 990.0, "r1")]
    rows = _read("holdings.parquet", "SELECT holding_id, cusip, isin, ticker, balance, currency_value, "
                                     "pct_of_net_assets, asset_cat FROM {t} ORDER BY holding_id")
    assert rows == [("11", "594918104", "US5949181045", "MSFT", 100.0, 40000.0, 4.04, "EC"),
                    ("12", None, None, None, 1.0, 5.0, 0.01, "STIV"),              # N/A is no CUSIP
                    ("13", None, "DE0000000001", None, None, None, None, "EC")]    # nor all zeros; "x" no number
    assert any("3 holdings (2 without a CUSIP)" in n for n in ctx.notes)
    assert nport.DATASET.tables == (nport.TABLE, nport.HISTORY)


def test_a_held_set_is_not_asked_again_and_one_not_typed_is_typed(sets):
    _run()
    (nport.parquet_dir() / "quarter=2026q3" / "fund.parquet").unlink()
    sets.requests.clear()
    ctx, out = _run()
    assert not sets.calls(FOLDER) and len(sets.calls(nport.INDEX_PATH)) == 1
    assert nport.typed(NEW) and any("typed now" in n for n in ctx.notes)
    sets.requests.clear()
    assert _run()[1] == [] and not sets.calls(FOLDER)


def test_an_answer_that_is_not_a_zip_is_not_kept(sets):
    sets.routes.insert(0, (FOLDER + NEW, b"<html>busy</html>", 200, {}))
    with pytest.raises(base.SourceError, match="not a zip"):
        _run()
    assert not (nport.raw_dir() / NEW).exists() and not (nport.raw_dir() / (NEW + ".tmp")).exists()


def test_a_set_without_an_optional_column_still_types(sets):
    tables = {**TABLES, "FUND_REPORTED_HOLDING": tuple(c for c in TABLES["FUND_REPORTED_HOLDING"] if c != "PERCENTAGE")}
    rows = {**ROWS, "FUND_REPORTED_HOLDING": [r[:10] + r[11:] for r in ROWS["FUND_REPORTED_HOLDING"]]}
    sets.routes.insert(0, (FOLDER + NEW, _zip(tables, rows), 200, {}))
    _run()
    assert _read("holdings.parquet", "SELECT count(*), count(pct_of_net_assets), count(asset_cat) FROM {t}") == [
        (3, 0, 3)]


def test_the_served_table_keeps_the_spine_etfs_newest_report_and_their_mapped_positions(sets, monkeypatch):
    """C2 (avo, 16 Nov 2026, Q11): ETFs only, each series' newest report, positions whose CUSIP is a spine ticker."""
    _run()
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [("VTI", "S000002848"), ("SPY", "S000000001")])
    monkeypatch.setattr(common, "spine_cusips", lambda: {"594918104": "MSFT"})
    ctx = base.RunContext(run_id="b1", dataset=nport.NAME)
    con = duckdb.connect()
    counts = nport.DATASET.build(ctx, con)
    assert counts[nport.TABLE] == 1
    assert con.execute(f"SELECT etf_ticker, series_id, ticker, cusip, currency_value, quarter FROM {nport.TABLE}"
                       ).fetchall() == [("VTI", "S000002848", "MSFT", "594918104", 40000.0, "2026q3")]
    assert any("1 holdings of 1 spine ETFs, quarter 2026q3" in n for n in ctx.notes)


def test_no_spine_gives_an_empty_table_not_a_failed_build(sets, monkeypatch):
    _run()
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [])
    con = duckdb.connect()
    assert nport.DATASET.build(base.RunContext(run_id="b2", dataset=nport.NAME), con) == {nport.TABLE: 0,
                                                                                         nport.HISTORY: 0}


# ── C7: the older quarters (avo, 22 Nov 2026) ──────────────────────────────────────────────────────────────────

def _backfill(start, end=date(2026, 11, 22)) -> base.RunContext:
    ctx = base.RunContext(run_id="h1", dataset=nport.NAME, sleep=lambda s: None)
    nport.DATASET.backfill(ctx, start, end)
    return ctx


def _asked(sets) -> list[str]:
    return [str(r.url).rsplit("/", 1)[1] for r in sets.calls(FOLDER)]


def test_a_backfill_with_a_first_day_takes_every_quarter_that_reaches_it_oldest_first(sets):
    """C7: before this a backfill was the daily rule and the older quarters could not be asked at all."""
    ctx = _backfill(date(2026, 4, 1))
    assert _asked(sets) == [OLD, NEW]                       # oldest first, so a stopped run leaves a run of history
    assert nport.typed(OLD) and nport.typed(NEW)
    assert (nport.parquet_dir() / "quarter=2026q2" / "holdings.parquet").exists()
    assert any("2 listed quarter(s)" in n and "2 to go" in n for n in ctx.notes)


def test_a_quarter_whose_window_ends_before_the_first_day_is_not_asked(sets):
    ctx = _backfill(date(2026, 7, 1))
    assert _asked(sets) == [NEW] and not nport.typed(OLD)
    assert any("1 listed quarter(s)" in n for n in ctx.notes)


def test_only_a_first_day_asks_for_history_and_without_one_it_is_the_newest_quarter(sets):
    """Decision G (avo, 16 Nov 2026) is unchanged: only ``--from`` asks for history.

    The contrast is the rule, so both halves stand in one test: without a first day the run is the newest listed
    quarter, and the same dataset with one then takes the older quarter. The first half alone passes on the
    merge-base and would prove nothing about this change (``scripts/red_on_base.py``), because it is exactly the
    base's behaviour; the second half is what C7 adds.
    """
    nport.DATASET.backfill(base.RunContext(run_id="h0", dataset=nport.NAME, sleep=lambda s: None),
                           None, date(2026, 11, 22))
    assert _asked(sets) == [NEW]
    sets.requests.clear()
    _backfill(date(2026, 4, 1))
    assert _asked(sets) == [OLD]                             # NEW is held and typed, so only the older one is asked


def test_a_quarter_already_typed_is_not_asked_again_so_a_stopped_run_resumes(sets):
    _run()                                                   # 2026q3 held and typed
    sets.requests.clear()
    ctx = _backfill(date(2026, 4, 1))
    assert _asked(sets) == [OLD]
    assert any("1 already typed" in n for n in ctx.notes)


def test_at_most_a_runs_worth_of_quarters_and_the_note_says_how_many_are_left(sets, monkeypatch):
    monkeypatch.setattr(nport, "MAX_SETS_PER_RUN", 1)
    ctx = _backfill(date(2026, 4, 1))
    assert _asked(sets) == [OLD]
    assert any("1 quarter(s) left" in n for n in ctx.notes)


def test_a_full_disk_stops_the_run_before_the_download_and_keeps_what_is_held(sets, monkeypatch):
    """12 GB of raw zip must not fill the disk: a quarter is asked only while the raw disk keeps room for it."""
    monkeypatch.setattr(nport.shutil, "disk_usage",
                        lambda p: SimpleNamespace(total=0, used=0, free=nport.MIN_FREE_SETS - 1))
    ctx = _backfill(date(2026, 4, 1))
    assert _asked(sets) == [] and not nport.typed(OLD)
    assert any("stopped before" in n for n in ctx.notes)
    assert [k for k, _ in _issues()] == ["no_space"]


def test_room_for_a_quarter_lets_the_run_go_on(sets, monkeypatch):
    monkeypatch.setattr(nport.shutil, "disk_usage",
                        lambda p: SimpleNamespace(total=0, used=0, free=nport.MIN_FREE_SETS))
    _backfill(date(2026, 4, 1))
    assert _asked(sets) == [OLD, NEW] and not _issues()


# ── #1441: long equity only, and every quarter in the history table (avo, 22 Nov 2026) ─────────────────────────────

def _holding(acc, hid, name, cusip, shares, value, pct, profile="Long", cat="EC", country="US"):
    return (acc, hid, name, "", name, cusip, shares, "NS", "USD", value, pct, profile, cat, "CORP", country)


Q3 = {**ROWS, "FUND_REPORTED_HOLDING": [
    _holding("0000001-26-000001", "11", "Microsoft Corp", "594918104", "100", "40000", "4.04"),
    _holding("0000001-26-000001", "21", "Microsoft Corp", "594918104", "50", "20000", "2.0", profile="Short"),
    _holding("0000001-26-000001", "22", "Microsoft Corp", "594918104", "9", "900", "0.1", cat="DBT"),
    _holding("0000001-26-000001", "23", "Banco Santander SA", "N/A", "212710002", "3000", "0.47", country="ES"),
    _holding("0000001-26-000001", "24", "Banco Santander SA", "N/A", "4", "1", "0.0", country="ES"),
    _holding("0000001-26-000001", "25", "Anthropic PBC Series G", "N/A", "10", "109", "0.01")],
    "IDENTIFIERS": [("11", "US5949181045", "MSFT"), ("23", "ES0113900J37", ""), ("24", "ES0113900J37", "")]}
Q2 = {**ROWS,
      "SUBMISSION": [("0000001-26-000002", "28-MAY-2026", "NPORT-P", "31-DEC-2026", "31-MAR-2026")],
      "FUND_REPORTED_INFO": [("0000001-26-000002", "Vanguard Total Stock Market", "S000002848", "900", "890")],
      "FUND_REPORTED_HOLDING": [_holding("0000001-26-000002", "31", "Microsoft Corp", "594918104", "90", "35000",
                                         "3.9")],
      "IDENTIFIERS": [("31", "US5949181045", "MSFT")]}


@pytest.fixture
def two_quarters(sets, monkeypatch):
    sets.routes.insert(0, (FOLDER + NEW, _zip(TABLES, Q3), 200, {}))
    sets.routes.insert(0, (FOLDER + OLD, _zip(TABLES, Q2), 200, {}))
    _backfill(date(2026, 1, 1))
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [("VTI", "S000002848")])
    monkeypatch.setattr(common, "spine_cusips", lambda: {"594918104": "MSFT"})
    con = duckdb.connect()
    ctx = base.RunContext(run_id="b3", dataset=nport.NAME)
    return ctx, con, nport.DATASET.build(ctx, con)


def test_the_served_table_keeps_long_equity_only(two_quarters):
    """A short and a bond line of a spine CUSIP were served as holdings (~3,950 rows on 22 Nov 2026)."""
    _ctx, con, counts = two_quarters
    assert con.execute(f"SELECT ticker, balance, asset_cat FROM {nport.TABLE}").fetchall() == [("MSFT", 100.0, "EC")]
    assert counts[nport.TABLE] == 1


def test_the_history_keeps_every_quarter_and_every_long_equity_holding_one_row_each(two_quarters):
    """#1441: every typed quarter; a foreign or private holding is kept by its ISIN or name with no ticker, and the
    lines of one security are summed (VXUS reports Banco Santander twice)."""
    ctx, con, counts = two_quarters
    rows = con.execute(f"SELECT quarter, ticker, cusip, isin, issuer_name, country, balance, currency_value, lines "
                       f"FROM {nport.HISTORY} ORDER BY quarter, currency_value DESC").fetchall()
    assert rows == [
        ("2026q2", "MSFT", "594918104", "US5949181045", "Microsoft Corp", "US", 90.0, 35000.0, 1),
        ("2026q3", "MSFT", "594918104", "US5949181045", "Microsoft Corp", "US", 100.0, 40000.0, 1),
        ("2026q3", None, None, "ES0113900J37", "Banco Santander SA", "ES", 212710006.0, 3001.0, 2),
        ("2026q3", None, None, None, "Anthropic PBC Series G", "US", 10.0, 109.0, 1)]
    assert counts[nport.HISTORY] == 4
    assert any("4 holdings over 2 quarters (2 without a spine ticker)" in n for n in ctx.notes)


def test_the_check_counts_a_change_in_the_history_too(two_quarters):
    """Grok xReview 22 Nov 2026: a live file whose served table matches but which has no history read as
    "unchanged", so a build that changes only the history was not seen."""
    from revenuechaser.rcdata import serving
    ctx, con, _ = two_quarters
    path = serving.live_path("ownership")
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"ATTACH '{path}' AS live_w")
    con.execute(f"CREATE TABLE live_w.{nport.TABLE} AS SELECT * FROM {nport.TABLE}")
    con.execute("DETACH live_w")
    got = nport.DATASET.check(ctx, con)
    assert (got["result"], got["added"], got["removed"], got["rows"]) == ("changed", 4, 0, 5)


def test_the_history_reader_names_a_cusip_by_the_13f_map_of_the_reports_quarter(two_quarters):
    """N-PORT and 13F name a CUSIP alike: the 13F map of the report's quarter wins over the spine's current owner
    (the spine holds XOM under another CUSIP than the funds report, #1444)."""
    from revenuechaser.rcdata import read, serving
    _ctx, con, _ = two_quarters
    path = serving.live_path("ownership")
    path.parent.mkdir(parents=True, exist_ok=True)
    live = duckdb.connect(str(path))
    try:
        live.execute(ox.CUSIP_MAP_DDL)
        live.execute("INSERT INTO sec13f_cusip_map (cusip, period, ticker, map_source) "
                     "VALUES ('594918104', DATE '2026-03-31', 'MSFTQ1', 'wrds/sec_idhist')")
        cols = ", ".join(f"{c} {t}" for c, t in nport.HISTORY_SERVED)
        live.execute(f"CREATE TABLE {nport.HISTORY} ({cols})")
        live.executemany(f"INSERT INTO {nport.HISTORY} VALUES ({', '.join('?' * len(nport.HISTORY_SERVED))})",
                         con.execute(f"SELECT * FROM {nport.HISTORY}").fetchall())
    finally:
        live.close()
    got = [(r["quarter"], r["ticker"], r["ticker_source"], r["name"], r["lines"])
           for r in read.etf_holdings_history("vti", ["2026Q3", "2026q2"])]
    assert got == [("2026q3", "MSFT", "spine", "Microsoft Corp", 1),
                   ("2026q3", None, None, "Banco Santander SA", 2),
                   ("2026q3", None, None, "Anthropic PBC Series G", 1),
                   ("2026q2", "MSFTQ1", "13f", "Microsoft Corp", 1)]
    assert [(q["quarter"], q["holdings"], q["no_ticker"]) for q in read.etf_nport_quarters("VTI")] == [
        ("2026q3", 3, 2), ("2026q2", 1, 0)]
    assert read.etf_holdings_history("SPY", ["2026q3"]) == []


def _serve_live(con) -> None:
    """The built tables as the live ownership file holds them."""
    from revenuechaser.rcdata import serving
    path = serving.live_path("ownership")
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"ATTACH '{path}' AS live_w")
    for t in (nport.TABLE, nport.HISTORY):
        con.execute(f"CREATE TABLE live_w.{t} AS SELECT * FROM {t}")
    con.execute("DETACH live_w")


def test_a_spine_etf_ticker_change_rebuilds_with_no_parquet_change(two_quarters, monkeypatch):
    """Ticker plan PR 4 (avo, 24 Nov 2026): the spine renamed SPLG to SPYM (S000006983) and N-PORT kept serving both,
    because only a Parquet change rebuilt it. A live ETF ticker or series the spine no longer pairs rebuilds whole."""
    ctx, con, _ = two_quarters
    _serve_live(con)
    ctx.changed = []
    assert nport.DATASET.dirty(ctx).clean
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [("VTIX", "S000002848")])
    assert not nport.DATASET.dirty(ctx).clean
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [("VTI", "S000009999")])
    assert not nport.DATASET.dirty(ctx).clean
    # a spine that cannot be read gives no ETFs; that must not read as every live ETF gone
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [])
    assert nport.DATASET.dirty(ctx).clean


# ── #1507 follow-up: a reorganised ETF keeps its holdings until its new series reports (avo's option A) ─────────────

def _ncen(*rows) -> None:
    """``sec/ncen`` Parquet as the spine's N-CEN step types it: ``(ticker, series_id, filing_date, accession)``."""
    folder = ncen.parquet_dir() / "quarter=2026q3"
    folder.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE t (ticker TEXT, series_id TEXT, is_etf BOOLEAN, filing_date DATE, accession TEXT)")
    con.executemany("INSERT INTO t VALUES (?, ?, TRUE, ?, ?)", rows)
    con.execute(f"COPY t TO '{folder / 'part-0.parquet'}' (FORMAT parquet)")
    con.close()


@pytest.fixture
def reorganised(sets, monkeypatch):
    """#1507 moved MAGA, YALL, EVNT and ARB to the SEC fund file's new series, which has filed no N-PORT yet; N-CEN
    still lists the ticker under its old series, whose reports the quarters hold (here: VTI, S000009999 new)."""
    sets.routes.insert(0, (FOLDER + NEW, _zip(TABLES, Q3), 200, {}))
    sets.routes.insert(0, (FOLDER + OLD, _zip(TABLES, Q2), 200, {}))
    _backfill(date(2026, 1, 1))
    _ncen(("VTI", "S000002848", date(2026, 3, 1), "0000002-26-000001"))
    monkeypatch.setattr(common, "spine_cusips", lambda: {"594918104": "MSFT"})
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [("VTI", "S000009999")])

    def build(run_id="b4"):
        con = duckdb.connect()
        ctx = base.RunContext(run_id=run_id, dataset=nport.NAME)
        nport.DATASET.build(ctx, con)
        return ctx, con
    return build


def test_a_spine_etf_whose_new_series_has_not_reported_keeps_its_old_series_holdings(reorganised):
    """220 live rows (MAGA 143, YALL 39, EVNT 21, ARB 17) would go on the next build, history with them."""
    ctx, con = reorganised()
    assert con.execute(f"SELECT etf_ticker, series_id, ticker FROM {nport.TABLE}").fetchall() == [
        ("VTI", "S000002848", "MSFT")]
    assert con.execute(f"SELECT DISTINCT etf_ticker, series_id, quarter FROM {nport.HISTORY} ORDER BY quarter"
                       ).fetchall() == [("VTI", "S000002848", "2026q2"), ("VTI", "S000002848", "2026q3")]
    assert any("VTI S000009999->S000002848" in n for n in ctx.notes)


def test_the_old_series_fallback_does_not_rebuild_every_run(reorganised):
    """#1516's rule (a live pair the spine does not hold rebuilds) reads the pairs the build used, so the served
    old series is not stale on every run."""
    ctx, con = reorganised()
    assert con.execute(f"SELECT DISTINCT etf_ticker, series_id FROM {nport.TABLE}").fetchall() == [
        ("VTI", "S000002848")]
    _serve_live(con)
    ctx.changed = []
    assert nport.DATASET.dirty(ctx).clean


def test_the_new_series_wins_once_it_reports(reorganised, monkeypatch):
    """Once the spine's series has a report it is read, whatever older series N-CEN still lists for the ticker."""
    _ncen(("VTI", "S000001111", date(2026, 3, 1), "0000002-26-000001"))
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [("VTI", "S000002848")])
    ctx, con = reorganised()
    assert con.execute(f"SELECT DISTINCT series_id FROM {nport.TABLE}").fetchall() == [("S000002848",)]
    assert not any("->" in n for n in ctx.notes)


def test_an_old_series_another_spine_etf_carries_is_never_taken(reorganised, monkeypatch):
    """SPLG's N-CEN series is SPYM's: a fallback there would serve one fund's holdings under two tickers."""
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [("VOO", "S000002848"), ("VTI", "S000009999")])
    _ctx, con = reorganised()
    assert con.execute(f"SELECT DISTINCT etf_ticker FROM {nport.TABLE}").fetchall() == [("VOO",)]
    assert con.execute(f"SELECT DISTINCT etf_ticker FROM {nport.HISTORY}").fetchall() == [("VOO",)]


def test_one_old_series_two_tickers_ask_for_is_taken_by_neither(reorganised, monkeypatch):
    _ncen(("VTI", "S000002848", date(2026, 3, 1), "0000002-26-000001"),
          ("VTIX", "S000002848", date(2026, 3, 1), "0000002-26-000001"))
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [("VTI", "S000009999"), ("VTIX", "S000009998")])
    _ctx, con = reorganised()
    assert con.execute(f"SELECT count(*) FROM {nport.TABLE}").fetchone() == (0,)
