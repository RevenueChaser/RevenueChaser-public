"""#310 N13: a serving file replaced under a render must cost its own card, never the whole Database tab.

``newdata._serving_facts`` opens each kind's live file read-only and reads it in a handful of queries. The builder
swaps a file by replacing the path, so between the open and any one of those queries the file this connection holds
can go away -- and ``_session_counts`` attaches a *second* file, the live spine, inside the prices read. Before this
landed a DuckDB error anywhere in there left ``report._collect_newdata`` with nothing but ``{"error": ...}``, which
the page draws as one line in place of every card.

So: a kind that cannot be read contributes nothing, exactly as a kind whose file is not built yet does, and a spine
that cannot be attached leaves the Backfill calendar counting every bar as off the spine.
"""
from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pytest

from RevenueChaser.core import calendar
from RevenueChaser.module_settings import newdata, report
from RevenueChaser.rcdata import serving
from RevenueChaser.rcdata.tests.conftest import market_roots  # noqa: F401 - market roots per test

from RevenueChaser.module_settings.tests.test_newdata_control import _bars

NOW = datetime(2026, 10, 29, 3, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(calendar, "_now", lambda: NOW)
    newdata.clear_sample_cache()
    yield
    newdata.clear_sample_cache()


def test_a_spine_that_cannot_be_attached_counts_every_bar_as_off_the_spine(market_roots):
    """The spine's path exists but is not a readable DuckDB file, which is what a reader sees for the moment a
    swap takes. The calendar then says what it still knows -- the bars per session -- under ``-``."""
    _bars([("g1:01", "2026-10-27"), ("g1:01", "2026-10-28"), ("g2:01", "2026-10-28")])
    path = serving.live_path("spine")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a duckdb file")
    assert newdata.collect(NOW)["sessions"] == {"2026-10-27": {"-": 1}, "2026-10-28": {"-": 2}}


def test_a_spine_whose_group_by_fails_falls_back_to_the_same_counts(market_roots):
    """The attach can succeed and the one ``GROUP BY`` still fail -- here the attached file carries no ``security``
    table, as a spine does for the moment its first build is writing it -- so the fallback cannot hang off
    ``exists()`` alone."""
    path = serving.live_path("spine")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE something_else (i INTEGER)")
    finally:
        con.close()
    _bars([("g1:01", "2026-10-27"), ("g1:01", "2026-10-28")])
    assert newdata.collect(NOW)["sessions"] == {"2026-10-27": {"-": 1}, "2026-10-28": {"-": 1}}


def test_one_kinds_file_failing_leaves_every_other_kind_on_the_board(market_roots, monkeypatch):
    """One kind read mid-swap is one empty card, not the whole tab: the prices file's own rows go unsaid while the
    counts of every other kind, and the rest of ``collect``, still answer."""
    _bars([("g1:01", "2026-10-28")])
    real = newdata._build_of
    def build_of(kind, con, names):             # noqa: ANN001 - the last read of each kind in ``_serving_facts``
        if kind == "prices":
            raise duckdb.IOException("the prices file was swapped under this connection")
        return real(kind, con, names)
    monkeypatch.setattr(newdata, "_build_of", build_of)
    got = newdata.collect(NOW)
    assert "error" not in got
    assert got["builds"].get("prices") is None, "a kind that could not be read says nothing about its build"


def test_the_tab_still_renders_when_every_served_file_is_unreadable(market_roots):
    """The end of the chain: ``_collect_newdata`` answers with the section, not with its one-line error."""
    for kind in serving.KINDS:
        path = serving.live_path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not a duckdb file")
    got = report._collect_newdata()
    assert "error" not in got, got.get("error")
    assert got["tables"] == {} and got["sessions"] == {}
