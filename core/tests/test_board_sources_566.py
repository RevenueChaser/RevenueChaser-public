"""#566: every board run records which build of which source DuckDB it actually opened, and Data/Health says which
boards are behind.

- ``serving.open_read`` notes each open in ``rcdata/opens``: the build, and the job (or thread) that opened it.
- ``board_sources.snapshot``: the files the run opened with their build; a declared file it did not open is
  ``not_opened`` (with the old-store reason when the boards fell back); two builds in one run is flagged.
- ``history.record_run`` keeps it in ``context["source_builds"]`` and never fails a run over it.
- ``history.last_runs``: the newest header per board.
- ``board_sources.freshness``: current / behind / rolled back / missing / old store / not opened / not recorded.
- ``freshness_tab.section``: the Health tab part, the boards to look at first.
Temp stores only.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import duckdb
import pytest

from RevenueChaser.core import prices
from RevenueChaser.module_settings import freshness_tab
from RevenueChaser.rcdata import opens, serving
from RevenueChaser.rcdata.tests.conftest import market_roots  # noqa: F401  (fixture)

BUILT = datetime(2026, 11, 9, 8, 52, tzinfo=timezone.utc).timestamp()      # 09:52 Amsterdam
RUN = datetime(2026, 11, 9, 9, 10, tzinfo=timezone.utc).timestamp()
LATER = datetime(2026, 11, 9, 15, 1, tzinfo=timezone.utc).timestamp()
BOARD = "module_swing_potential"


def _prices_file(build_id: str = "b1", built_at: float = BUILT, last: date = date(2026, 11, 6)):
    path = serving.live_path("prices")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("prices.tmp.duckdb")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute(f"CREATE TABLE {serving.VERSION_TABLE} (kind TEXT, version INTEGER, built_at DOUBLE, "
                "build_id TEXT, build_mode TEXT)")
    con.execute(f"INSERT INTO {serving.VERSION_TABLE} VALUES ('prices', 1, ?, ?, 'live')", [built_at, build_id])
    con.execute("CREATE TABLE price_bar_daily (security_id VARCHAR, session_date DATE)")
    con.execute("INSERT INTO price_bar_daily VALUES ('s1', ?), ('s1', DATE '2026-01-02')", [last])
    con.close()
    tmp.replace(path)                                    # a swap, as the builder does


def _read_prices():
    with serving.open_read("prices") as con:
        con.execute("SELECT count(*) FROM price_bar_daily").fetchone()




































def _run(sources):
    return {"board": BOARD, "run_id": "r", "run_at": RUN, "quality": "complete",
            "context": None if sources is None else {"source_builds": sources}}


REC = {"kind": "prices", "file": "prices.duckdb", "reads": "file", "build_id": "b1", "built_at": BUILT}






def test_the_part_lists_the_boards_to_look_at_first():
    boards = [{"board": "module_comovement", "run_at": RUN, "state": "current",
               "sources": [{**REC, "state": "current", "newest_day": "2026-11-06"}]},
              {"board": BOARD, "run_at": RUN, "state": "behind",
               "sources": [{**REC, "state": "behind", "live_built_at": LATER}]},
              {"board": "module_leaps", "run_at": RUN, "state": "not_recorded", "sources": []}]
    html = freshness_tab.section({"boards": boards}, {BOARD: "Swing Potential"})
    assert html.index("Swing Potential") < html.index("Leaps") < html.index("Comovement")
    assert "1 behind · 1 not recorded yet · 1 current" in html
    assert "live build now <b>9 Nov 16:01</b>" in html                  # Amsterdam, not UTC
    assert "read build <b>9 Nov 09:52</b>" in html and "newest day 6 Nov 2026" in html
    assert "The next Fetch of the board records them" in html


def test_the_part_says_what_it_could_not_read():
    assert "Could not be read: OSError: x" in freshness_tab.section({"error": "OSError: x"})
    assert "No board run is recorded yet" in freshness_tab.section({"boards": []})
