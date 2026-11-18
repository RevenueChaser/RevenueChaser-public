"""The strict reader a job uses for a watch list (plan v5 step 7c of the spine classification, avo's A).

``store``'s own readers answer ``[]`` for a missing file, a lock and a SQL error alike, which is right for a page
and wrong for a job: a build that reads "no names" drops its whole list. ``read.job_list`` raises on each.
"""
from __future__ import annotations

import duckdb
import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_watchlists import store
from RevenueChaser.rcdata import read

pytestmark = pytest.mark.rawstore_schema_from_scratch


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_a_job_reads_the_tickers_of_every_list_marked_for_it_and_no_other():
    option = store.create_list("Option chains", feeds="option")
    more = store.create_list("More option names", feeds="option")
    other = store.create_list("avo's own")
    store.add_symbol(option, "NASDAQ:SMH")
    store.add_symbol(option, "AMEX:SPY")
    store.add_symbol(more, "AMEX:SPY")
    store.add_symbol(other, "NYSE:XOM")
    store.add_symbol(option, "NASDAQ:SMH/AMEX:SPY")              # a spread: nothing a job can fetch
    assert read.job_list("option") == ["SMH", "SPY"]


def test_a_marked_list_with_no_ticker_is_the_only_empty_answer():
    store.create_list("Option chains", feeds="option")
    assert read.job_list("option") == []


def test_no_file_and_no_marked_list_are_errors_not_empty_lists():
    with pytest.raises(read.JobListUnreadable, match="no such file"):
        read.job_list("option")
    store.create_list("avo's own")
    with pytest.raises(read.JobListUnreadable, match="no list is marked for 'option'"):
        read.job_list("option")


def test_a_lock_that_stays_is_an_error(monkeypatch):
    """Measured on homesrv, 18 Nov 2026: the dashboard holds the file while it serves a watch-list request and a
    second process is refused at once. ``rawstore.connect`` waits it out; one that stays must not read as empty."""
    store.add_symbol(store.create_list("Option chains", feeds="option"), "AMEX:SPY")

    def locked(*a, **kw):
        raise rawstore.RawStoreError("watchlists.duckdb is locked by another process")

    monkeypatch.setattr(rawstore, "_connect_with_retry", locked)
    with pytest.raises(read.JobListUnreadable, match="RawStoreError: watchlists.duckdb is locked"):
        read.job_list("option")


def test_a_file_without_the_tables_is_an_error(tmp_path, monkeypatch):
    empty = tmp_path / "watchlists.duckdb"
    duckdb.connect(str(empty)).close()
    monkeypatch.setattr(rawstore, "board_db_path", lambda board: empty)
    with pytest.raises(read.JobListUnreadable, match="CatalogException"):
        read.job_list("option")


def test_a_list_a_job_reads_is_never_emptied_or_deleted():
    """Plan v5 step 7c: "empty" must only ever mean a list with no row, so the board cannot make one."""
    marked = store.create_list("Option chains", feeds="option")
    store.add_symbol(marked, "AMEX:SPY")
    store.add_symbol(marked, "NASDAQ:QQQ")
    assert store.remove_symbol(marked, "NASDAQ:QQQ") is True
    with pytest.raises(store.WatchlistError, match="last symbol"):
        store.remove_symbol(marked, "AMEX:SPY")
    with pytest.raises(store.WatchlistError, match="jobs read"):
        store.delete_list(marked)
    assert read.job_list("option") == ["SPY"]
    store.update_list(marked, feeds="")
    assert store.delete_list(marked) is True
