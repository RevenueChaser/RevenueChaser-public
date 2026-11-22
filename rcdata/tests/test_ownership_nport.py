"""``sec/nport`` (#354 C1): the SEC's Form N-PORT data sets, newest listed quarter only, streamed to disk and typed
to two Parquet files (the series, the holdings); no served table yet. Offline: the page and the zips are fixtures."""
from __future__ import annotations

import io
from datetime import date
from types import SimpleNamespace
import zipfile

import duckdb
import pytest

from RevenueChaser.core.providers import sec_edgar
from RevenueChaser.rcdata import ops
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.ownership import common, nport, sec

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
    assert nport.DATASET.tables == (nport.TABLE,)


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
    assert counts == {nport.TABLE: 1}
    assert con.execute(f"SELECT etf_ticker, series_id, ticker, cusip, currency_value, quarter FROM {nport.TABLE}"
                       ).fetchall() == [("VTI", "S000002848", "MSFT", "594918104", 40000.0, "2026q3")]
    assert any("1 holdings of 1 spine ETFs, quarter 2026q3" in n for n in ctx.notes)


def test_no_spine_gives_an_empty_table_not_a_failed_build(sets, monkeypatch):
    _run()
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [])
    con = duckdb.connect()
    assert nport.DATASET.build(base.RunContext(run_id="b2", dataset=nport.NAME), con) == {nport.TABLE: 0}


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


def test_a_backfill_without_a_first_day_is_still_the_newest_quarter_only(sets):
    """Decision G (avo, 16 Nov 2026) is unchanged: only ``--from`` asks for history."""
    nport.DATASET.backfill(base.RunContext(run_id="h0", dataset=nport.NAME, sleep=lambda s: None),
                           None, date(2026, 11, 22))
    assert _asked(sets) == [NEW]


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
