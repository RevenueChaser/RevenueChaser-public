"""``sec/13f_list`` (#926): the SEC's Official List of Section 13(f) Securities, one text file per quarter, a held
quarter not asked again, typed to one Parquet file. Offline: the page and the files are fixtures."""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from RevenueChaser.core.providers import sec_edgar
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.ownership import sec, sec13f_list

PAGE = sec13f_list.PAGE_PATH
Q2, Q3 = "/files/investment/13flist2026q2-txt.txt", "/files/investment/13flist2026q3.txt"
LIST = (b"037833100*APPLE INC                     COM                                    E\n"
        b"037833900 APPLE INC                     CALL                                   E\n"
        b"C10268AC1 BLACKBERRY LTD                DEBT  3.750%11/1           *D*         U\n")


@pytest.fixture
def sets(monkeypatch, http_mock):
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    page = (f'<a href="/files/investment/13flist2026q3.pdf">pdf</a><a href="{Q2}">q2</a>'
            f'<a href="{Q3}">q3</a><a href="{Q3}">again</a>').encode()
    http_mock.add(PAGE, page)
    http_mock.add(Q2, LIST)
    http_mock.add(Q3, LIST)
    return http_mock


def _run():
    ctx = base.RunContext(run_id="r1", dataset=sec13f_list.NAME, sleep=lambda s: None)
    return ctx, sec13f_list.DATASET.to_parquet_all(ctx, sec13f_list.DATASET.fetch(ctx, date(2026, 11, 17)))


def test_each_quarters_text_list_is_fetched_once_and_typed(sets):
    ctx, out = _run()
    assert sorted(p.name for p in sec13f_list.raw_dir().glob("*.txt")) == ["2026q2.txt", "2026q3.txt"]
    assert len(sets.calls("/files/investment/")) == 2 and len(out) == 1
    sql = f"SELECT * FROM read_parquet({base.sql_path(out[0])}) ORDER BY quarter, cusip"
    rows = duckdb.connect().execute(sql).fetchall()
    apple = [("037833100", True, "APPLE INC", "COM"), ("037833900", False, "APPLE INC", "CALL")]
    assert rows == [(q, *r) for q in ("2026q2", "2026q3") for r in apple]           # the *D* row is not on it
    sets.requests.clear()
    _run()
    assert not sets.calls("/files/investment/") and len(sets.calls(PAGE)) == 1     # held: the page only


def test_an_answer_that_is_not_the_list_is_not_kept(sets):
    sets.routes.insert(0, (Q3, b"<html>busy</html>", 200, {}))
    with pytest.raises(base.SourceError, match="not the fixed-width list"):
        _run()
    assert not (sec13f_list.raw_dir() / "2026q3.txt").exists()
