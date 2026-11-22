"""``wrds/audit``: Audit Analytics' restatement, late-filing and officer-change feeds against a fake worker (never
WRDS), step C of the WRDS plan (#1181). ``company_fkey`` is the CIK; this file is the pull, the staging and the
check note. What is served from them is ``test_fund_audit_flag.py``."""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from revenuechaser.rcdata import ops
from revenuechaser.rcdata.build import DATASETS
from revenuechaser.rcdata.build.fundamentals import common, wrds_fund
from revenuechaser.rcdata.build.spine import wrds as spine_wrds

from . import fund_fixture as fx

AUDIT = wrds_fund.AUDIT
AS_OF = date(2026, 10, 27)
RESTATEMENTS, LATE, OFFICERS = "feed39_financial_restatements", "feed20_nt", "feed17_director_and_officer_chan"


def _con(rows: dict[str, list[dict]], ciks=("0000789019", "0000046619", "0000001234")) -> duckdb.DuckDBPyConnection:
    """A scratch connection with the three staged feeds (``rows``: part -> rows, a row's missing columns NULL) and
    the companies the note counts."""
    con = duckdb.connect()
    con.execute("CREATE TABLE fundamental_company (ticker TEXT, cik TEXT)")
    for i, cik in enumerate(ciks):
        con.execute("INSERT INTO fundamental_company VALUES (?, ?)", [f"T{i}", cik])
    con.execute("INSERT INTO fundamental_company VALUES ('T0B', ?)", [ciks[0]])       # a second ticker of one company
    for part, (_, schema, _) in AUDIT.PARTS.items():
        cols = schema + wrds_fund.PROVENANCE
        con.execute(f"CREATE TEMP TABLE {AUDIT.STAGING[part]} ({', '.join(f'{c} {t}' for c, t in cols)})")
        for row in rows.get(part, []):
            full = {**{c: None for c, _ in schema}, **row, "source_as_of": AS_OF, "fetched_at": 1.0, "run_id": "w1"}
            con.execute(f"INSERT INTO {AUDIT.STAGING[part]} VALUES ({', '.join('?' for _ in cols)})",
                        [full[c] for c, _ in cols])
    return con


def test_the_note_counts_each_feeds_rows_keys_our_companies_and_newest_day():
    con = _con({
        RESTATEMENTS: [{"restatement_notification_key": "1", "company_fkey": "789019", "file_date": "2025-08-01"},
                       {"restatement_notification_key": "2", "company_fkey": "999999", "file_date": "2026-09-21"}],
        OFFICERS: [{"do_change_key": "5", "do_off_pers_key": "1", "company_fkey": "789019",
                    "file_date": "2026-09-24"},
                   {"do_change_key": "5", "do_off_pers_key": "2", "company_fkey": "789019",
                    "file_date": "2026-09-24"},
                   {"do_change_key": "6", "do_off_pers_key": "3", "company_fkey": "0000046619",
                    "file_date": "2025-02-03"}]})
    assert AUDIT.note(con) == (
        "WRDS audit feeds (company_fkey is the CIK): "
        "restatements 2 rows (2 keys), 1 of 3 Tier A companies, newest 2026-09-21; "
        "officer changes 3 rows (2 keys), 2 of 3 Tier A companies, newest 2026-09-24")


def test_company_fkey_meets_the_cik_with_or_without_leading_zeros():
    """WRDS answers the key as a number or as text; ours is zero-padded. One company either way."""
    con = _con({LATE: [{"nt_notify_key": "1", "company_fkey": "46619", "file_date": "2026-09-15"},
                       {"nt_notify_key": "2", "company_fkey": "0000046619", "file_date": "2026-09-01"},
                       {"nt_notify_key": "3", "company_fkey": "4661", "file_date": "2026-09-02"}]})   # another key
    assert "late filings 3 rows (3 keys), 1 of 3 Tier A companies, newest 2026-09-15" in AUDIT.note(con)


def test_no_snapshot_yet_says_so():
    assert AUDIT.note(_con({})) == "WRDS audit feeds: no snapshot yet"


def test_the_dataset_is_registered_attended_monthly_and_builds_no_table_itself():
    assert DATASETS[AUDIT.name] is AUDIT and AUDIT.name == "wrds/audit"
    assert AUDIT.cadence == "monthly" and AUDIT.starts_by_hand
    assert AUDIT.feeds == ("audit_flag",) and AUDIT.tables == ()     # ``fundamentals/tables`` builds it
    assert AUDIT.full_rebuild_reason(None) is None


def test_no_persons_name_and_no_disclosure_text_is_asked():
    """The feeds carry names and long texts; a flag needs neither, so no query names them."""
    asked = {c for _, schema, _ in AUDIT.PARTS.values() for c, _ in schema}
    assert not {c for c in asked if c.endswith("_name") or c.endswith("_text") or "narrative" in c}
    for part, (_, schema, key) in AUDIT.PARTS.items():
        names = [c for c, _ in schema]
        assert key in names and AUDIT.COMPANY in names and "file_date" in names, part
        assert AUDIT.sql(part) == f"SELECT {', '.join(names)} FROM audit_audit_comp.{part}"


@pytest.fixture
def fake(monkeypatch):
    fx.spine()
    conn = fx.FakeFundWrds()
    monkeypatch.setattr(spine_wrds, "_factory", lambda: conn)
    spine_wrds.reset()
    yield conn
    spine_wrds.reset()


def _snapshot(part: str, select: str) -> list[tuple]:
    path = common.parquet_dir(AUDIT.name) / "snapshot=2026-10-27" / f"{part}.parquet"
    return duckdb.sql(f"SELECT {select} FROM read_parquet('{path}')").fetchall()


def test_three_whole_table_queries_and_each_feed_is_typed(fake):
    check = fx.run(AUDIT.name, mode="backfill", to="2026-10-27")
    assert check["result"] == "changed", check["note"]
    assert len(fake.queries) == 3 and ops.calls_today("wrds") == 3
    assert [q.split(" FROM ")[1] for q in fake.queries] == [f"audit_audit_comp.{p}" for p in AUDIT.PARTS]
    assert not any("WHERE" in q for q in fake.queries)                       # the feeds are small: asked whole
    assert _snapshot(RESTATEMENTS, "count(*), count(res_fraud), max(file_date)") == [(2, 2, date(2026, 9, 21))]
    assert _snapshot(LATE, "company_fkey, form_fkey, pe_date_num") == [("46619", "NT 10-Q", "20260731")]
    # The officer row WRDS sent twice is kept once; two people of one change stay two rows.
    assert _snapshot(OFFICERS, "count(*), count(DISTINCT do_change_key)") == [(3, 2)]
    assert _snapshot(OFFICERS, "DISTINCT source_as_of, run_id IS NOT NULL") == [(date(2026, 10, 27), True)]
    assert "restatements 2 rows (2 keys), 1 of " in check["note"]             # 999999 is no company of ours
    assert "officer changes 3 rows (2 keys), 2 of " in check["note"]
    assert "late filings 1 rows (1 keys), 1 of " in check["note"]


def test_a_current_snapshot_is_not_asked_again(fake):
    fx.run(AUDIT.name, mode="backfill", to="2026-10-27")
    check = fx.run(AUDIT.name, "2026-11-10")
    assert len(fake.queries) == 3 and "snapshot of 2026-10-27 is current" in check["note"]
