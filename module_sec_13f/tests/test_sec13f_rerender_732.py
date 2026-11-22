"""#732 C: a cached 13F page is re-rendered once the board file has not taken the live build or the day, and the
chart route reads one ticker's rows, not the whole board file.
"""
from __future__ import annotations

import pytest

from revenuechaser.core import ownership
from revenuechaser.module_sec_13f import store

Q1, Q2 = "2026-03-31", "2026-06-30"


def _cell(shares, closed=None):
    c = {m: None for m in ownership.SEC13F_METRICS}
    c.update(shares=shares, holders=3, complete=True)
    if closed is not None:
        c["closed"] = closed
    return c


@pytest.fixture
def builder(monkeypatch):
    state = {"totals": {}, "stamp": "build-1", "asked": []}

    def totals(tickers=None):
        state["asked"].append(tickers)
        rows = state["totals"]
        return {t: p for t, p in rows.items() if tickers is None or t in tickers}
    monkeypatch.setattr(ownership, "sec13f_totals", totals)
    monkeypatch.setattr(ownership, "sec13f_filer_breaks", lambda tickers: {})
    monkeypatch.setattr(store, "source_stamp", lambda: state["stamp"])
    return state


def test_the_file_is_stale_after_a_new_build_and_not_without_a_store(builder):
    builder["totals"] = {"AAA": {Q1: _cell(100.0)}}
    store.sync()
    assert store.is_stale() is False
    builder["stamp"] = "build-2"
    assert store.is_stale() is True
    builder["stamp"] = None                               # no ownership store: never re-render for nothing
    assert store.is_stale() is False


def test_the_chart_reads_one_tickers_rows(builder):
    builder["totals"] = {"AAA": {Q1: _cell(100.0, closed=True)}, "BBB": {Q1: _cell(5.0, closed=True)}}
    store.sync()
    builder["asked"].clear()
    assert store.read_ticker("AAA") == {Q1: builder["totals"]["AAA"][Q1]}
    assert builder["asked"] == []                         # current: the builder is not asked
    builder["stamp"] = "build-2"
    builder["totals"] = {"AAA": {Q1: _cell(999.0), Q2: _cell(120.0)}, "BBB": {Q1: _cell(5.0)}}
    got = store.read_ticker("AAA")
    assert builder["asked"] == [["AAA"]]                  # stale: only AAA from the builder
    assert got[Q1]["shares"] == 100.0 and got[Q2]["shares"] == 120.0     # the closed quarter keeps its rows


def test_a_stale_page_is_dropped_before_it_is_served(monkeypatch, tmp_path):
    from revenuechaser.app import dashboard
    monkeypatch.setattr(store, "is_stale", lambda: True)
    assert dashboard._sec13f_stale() is True

    def boom():
        raise RuntimeError("board file locked")
    monkeypatch.setattr(store, "is_stale", boom)
    assert dashboard._sec13f_stale() is False             # a read error serves the page as it is


def test_a_stale_page_is_rendered_again_in_the_background_once(monkeypatch):
    """The day's first open took ~70 s rendering inside the request (17 Nov 2026): the old page is served and one
    re-render runs beside it; a second stale load while it runs starts none."""
    import threading
    from revenuechaser.app import dashboard, runners
    started, release, calls = threading.Event(), threading.Event(), []

    def render(_):
        calls.append(1)
        started.set()
        release.wait(5)
    monkeypatch.setattr(runners, "run_sec_13f_latest", render)
    assert dashboard._sec13f_rerender_in_background() is True
    assert started.wait(5)
    assert dashboard._sec13f_rerender_in_background() is False
    release.set()
    for t in threading.enumerate():
        if t.name == "sec13f-rerender":
            t.join(5)
    assert calls == [1] and dashboard._sec13f_rerender_in_background() is True     # free again
    for t in threading.enumerate():
        if t.name == "sec13f-rerender":
            t.join(5)
