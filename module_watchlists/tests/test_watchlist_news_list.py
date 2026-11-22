"""The News list (avo, 18 Nov 2026 21:53 Amsterdam: "Hepsini watchliste.duckdb ye bagla"): the large caps the News
board asked in code are now ``jobs.news``, a watch list marked ``feeds`` = ``news``, made once from its seed, edited on
this board under "Read by the jobs", and read by the News pass strictly beside the stock picks."""
from __future__ import annotations

import pytest

from revenuechaser.module_watchlists import board, store
from revenuechaser.rcdata import read

pytestmark = [pytest.mark.rawstore_schema_from_scratch]

SEED = board.NEWS_LISTS["jobs.news"]["seed"]


@pytest.fixture
def no_data(monkeypatch):
    import pandas as pd
    monkeypatch.setattr(board.read, "ticker_bars", lambda *a, **k: pd.DataFrame(
        columns=["ticker", "session_date", "close", "volume"]))
    monkeypatch.setattr(board.read, "latest_market", lambda *a, **k: {})
    monkeypatch.setattr(board.read, "market_series", lambda *a, **k: [])
    monkeypatch.setattr(board.read, "identity", lambda *a, **k: [])
    monkeypatch.setattr(board.read, "etf_class", lambda etfs=(), **k: pytest.fail("no holdings label on News"))


def test_with_no_list_the_news_read_is_an_error_never_the_seed():
    store.create_list("Growth")
    with pytest.raises(read.JobListUnreadable):
        read.job_list("news")


def test_the_seed_makes_the_list_once_and_it_reads_back_as_the_seed():
    first = store.seed_news_lists()
    assert first["news"] == {"created": True, "seed": len(SEED), "list": len(SEED)}
    assert read.job_list("news") == sorted(SEED)
    store.remove_symbol("jobs.news", "XOM")                # avo's edit
    again = store.seed_news_lists()                       # a second call never refills or remakes it
    assert again["news"] == {"created": False, "seed": len(SEED), "list": len(SEED) - 1}
    assert "XOM" not in read.job_list("news")


def test_the_news_list_sits_under_read_by_the_jobs_without_a_hand_written_line(no_data):
    own = store.create_list("Growth")
    store.seed_news_lists()
    data = board.payload("jobs.news")
    assert [r["id"] for r in data["lists"]] == [own, "jobs.option", "jobs.stock", "jobs.news"]
    assert data["list"]["fed"] == "news" and data["list"]["map"] is False
    assert all("lab" not in row for s in data["sections"] for row in s["rows"])
    assert ">Read by the jobs</span>" in board.render_html(data)


def test_the_stock_list_says_news_reads_it():
    assert "News" in board.JOB_LISTS["jobs.stock"]["name"]


def test_avos_own_lists_are_read_as_one_list_for_news():
    # avo, 18 Nov 2026 22:31: "Artik watchlist.duckbd den secmeliler": News reads his own lists (feeds "") too.
    store.seed_news_lists()
    own = store.create_list("Growth")
    store.add_symbol(own, "NASDAQ:NVDA")
    store.add_symbol(own, "RKLB")
    assert read.job_list("") == ["NVDA", "RKLB"]
