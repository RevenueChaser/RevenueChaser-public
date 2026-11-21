"""#1182 — a read the builder's swap catches mid-flight is read again on the new build, not a 500.

``serving.open_read`` resolves the live path, opens it read-only and hands the connection over; the caller then
makes a handful of queries on it. The builder swaps a kind in with ``os.replace``, so the file that connection
holds can go away between the open and any of those reads. Every reader in ``rcdata/read.py`` already answers
"no file yet" (``ServingFileMissing``) -- 82 call sites through ``_rows``, plus ``my_universe_tickers``, the
DataFrame read and the table summary -- and none of them had an answer for "the file went away under this
connection": the ``duckdb.Error`` reached the caller, which is a 500 on a board render or a traceback in a job.

#310 N13 gave the one Settings card an absence instead. For a board row an absence is not available: ``[]`` is
read as *data* (the WRDS cross-check row would print "the monthly comparison has not run yet", which is a claim),
so the shape here is one reopen, as the issue's second option. A swap is a rename and takes a moment, so the next
open gets the new build.
"""
from __future__ import annotations

import duckdb
import pytest

from RevenueChaser.rcdata import read, serving


def _serve_market(series: str) -> None:
    """A ``market`` serving file holding one ``market_series`` row named ``series``."""
    with serving.build("market") as b:
        b.con.execute("CREATE TABLE market_series (series_id TEXT)")
        b.con.execute("INSERT INTO market_series VALUES (?)", [series])
        b.swap({"market_series": 1})


def _swept_away(con) -> None:
    """What DuckDB raises when the file a read-only connection holds is not there any more."""
    raise duckdb.IOException("IO Error: Could not read from file: No such file or directory")


def test_a_read_caught_by_a_swap_is_read_again_on_the_new_build():
    _serve_market("first")
    seen = []

    def work(con):
        seen.append(con)
        if len(seen) == 1:
            _serve_market("second")               # the builder swaps a new file over the live name
            _swept_away(con)
        return con.execute("SELECT series_id FROM market_series").fetchone()[0]

    assert serving.read_live("market", work) == "second"
    assert len(seen) == 2, "one reopen, and the second connection is a new one"


def test_an_error_with_the_file_still_in_place_is_raised_not_retried():
    """A missing table or a bad query is the caller's own: a retry would read the same file and hide it."""
    _serve_market("first")
    seen = []

    def work(con):
        seen.append(con)
        return con.execute("SELECT * FROM not_a_table").fetchall()

    with pytest.raises(duckdb.Error):
        serving.read_live("market", work)
    assert len(seen) == 1, "no reopen: the live file is the one this read opened"


def test_a_second_failure_is_raised_even_when_the_file_moved_again():
    """One reopen, not a loop: a kind that is swapped over and over may not hold a reader for ever."""
    _serve_market("first")
    seen = []

    def work(con):
        seen.append(con)
        _serve_market(f"again-{len(seen)}")
        _swept_away(con)

    with pytest.raises(duckdb.IOException):
        serving.read_live("market", work)
    assert len(seen) == serving.SWAP_REOPENS + 1


def test_no_file_at_all_is_still_an_absence_the_caller_answers():
    with pytest.raises(serving.ServingFileMissing):
        serving.read_live("market", lambda con: None)


def test_a_board_read_caught_by_a_swap_answers_the_new_builds_rows(monkeypatch):
    """The reader every board uses, end to end: ``read._rows`` through a swap, no exception and no empty answer.

    The swap lands inside the open here, which is the narrower of the two windows: ``open_read`` resolves the path
    and checks that it exists before it connects. ``read_live`` marks the file before the open for that reason.
    """
    _serve_market("first")
    real_open, opens = serving.open_read, []

    def open_read(kind):
        con = real_open(kind)
        opens.append(con)
        if len(opens) == 1:
            _serve_market("second")
            # The file is gone from under this connection; the first query on it is what finds out.
            class Swept:
                def execute(self, *a, **k):
                    _swept_away(con)

                def close(self):
                    con.close()

                def __getattr__(self, name):
                    return getattr(con, name)
            return Swept()
        return con

    monkeypatch.setattr(serving, "open_read", open_read)
    rows = read._rows("market_series", "SELECT series_id FROM market_series", [])
    assert [r["series_id"] for r in rows] == ["second"]
    assert len(opens) == 2
