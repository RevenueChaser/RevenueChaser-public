"""The served card answers from the file alone: no Parquet walk, no view counts, one computation per miss.

Measured on homesrv on 26 November 2026, two passes, which is what these tests pin (#1535, #1549):

===========  =========  ===========  ==================  ===============  ==================
kind         open       relations    ``_build_of`` cold  warm             slowest count(*)
===========  =========  ===========  ==================  ===============  ==================
sec_forms    1.40 s     0.63 s       **127.07 s**        0.73 s           0.001 s
ownership    0.45 s     0.23 s       **55.12 s**         1.45 s           view 3.82 s
prices       0.68 s     0.40 s       0.64 s              0.64 s           view 21.26 s
===========  =========  ===========  ==================  ===============  ==================

So the cost was never the row counts -- a table's ``count(*)`` is a millisecond, even at 14,014,752 rows, because
DuckDB answers it from metadata. It was ``_build_of`` calling ``dirty.scan``, which globs every ``*.parquet`` of
the kind and stats each one twice; ``sec_forms`` keeps one folder per CIK, so that is a cold directory traversal
inside a request the Grafana row gives 15 s. The expensive counts that remain are the **views**, whose count runs
the view's query (21.26 s cold and 11.63 s warm for ``price_bars_daily``).

Each test here states the behaviour, not an allowlist, so each is red on the base: the base walks the tree, counts
the views, and lets two misses compute in parallel.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import duckdb
import pytest

from revenuechaser.core.tests.panel_client import panel_test_client
from revenuechaser.module_settings import newdata
from revenuechaser.rcdata import serving
from revenuechaser.rcdata.build import dirty
from revenuechaser.rcdata.tests.conftest import market_roots  # noqa: F401 - a market root per test

NOW = datetime(2026, 11, 26, 3, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fresh_cache():
    newdata.clear_sample_cache()
    yield
    newdata.clear_sample_cache()


@pytest.fixture
def client():
    from revenuechaser.app.dashboard import app
    return panel_test_client(app)


def _market_file(rows: int = 9) -> None:
    """A served ``market`` file with a table, a view, a build manifest and the version row."""
    path = serving.live_path("market")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute(f"CREATE TABLE {serving.VERSION_TABLE} (kind TEXT, version INTEGER, built_at DOUBLE, "
                    "build_id TEXT, build_mode TEXT)")
        con.execute(f"INSERT INTO {serving.VERSION_TABLE} VALUES ('market', 7, 1764120000.0, 'b-1', 'live')")
        con.execute("CREATE TABLE build_manifest (path TEXT, size BIGINT, mtime DOUBLE)")
        con.execute("INSERT INTO build_manifest VALUES ('market/series/a.parquet', 10, 1.0), "
                    "('market/series/b.parquet', 20, 2.0)")
        con.execute("CREATE TABLE market_series (series_id TEXT, obs_date DATE, value DOUBLE)")
        con.execute("INSERT INTO market_series SELECT 's' || (i % 3), DATE '2026-01-01' + CAST(i AS INTEGER), i "
                    f"FROM range({int(rows)}) t(i)")
        con.execute("CREATE VIEW series_ids AS SELECT DISTINCT series_id FROM market_series")
    finally:
        con.close()


def _no_walking(monkeypatch) -> None:
    """``dirty.scan`` is the 127 s step: a test that reaches it has reached the defect."""
    def refuse(*_a, **_k):
        raise AssertionError("the served card walked the Parquet tree")
    monkeypatch.setattr(dirty, "scan", refuse)


def test_the_card_does_not_walk_the_parquet_tree_and_says_changed_is_unknown(monkeypatch):
    _market_file()
    _no_walking(monkeypatch)
    build = newdata.served("market", now=NOW)["build"]
    assert build["files"] == 2, "the manifest is inside the file and stays"
    assert build["changed"] is None, "a number this call did not take is not reported"
    assert build["changed_status"] == newdata.UNKNOWN, "unknown, never a zero that reads as 'nothing changed'"


def test_a_caller_that_asks_for_the_walk_still_gets_the_comparison(monkeypatch):
    """The comparison is not deleted, only taken off the request path: a builder or a CLI can still ask."""
    _market_file()
    monkeypatch.setattr(dirty, "scan", lambda *_a, **_k: {"market/series/a.parquet": (10, 1.0),
                                                          "market/series/c.parquet": (30, 3.0)})
    con = serving.open_read("market")
    try:
        names = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        build = newdata._build_of("market", con, names, scan_parquet=True)
    finally:
        con.close()
    assert build["changed"] == 2, "one file gone from the tree, one new one in it"
    assert build["changed_status"] == newdata.CHECKED


def test_tables_are_counted_and_views_are_not(monkeypatch):
    _market_file()
    _no_walking(monkeypatch)
    got = newdata.served("market", now=NOW)
    table = next(t for t in got["tables"] if t["name"] == "market_series")
    assert table["rows"] == 9 and table["rows_status"] == newdata.COUNTED
    view = next(v for v in got["views"] if v["name"] == "series_ids")
    assert view["rows"] is None, "a word in this column would be summed by the panel that draws it"
    assert view["rows_status"] == newdata.NOT_COUNTED
    assert [c["name"] for c in view["columns"]] == ["series_id"], "the definition is what the card can say cheaply"


def test_a_view_is_counted_on_its_own_call(monkeypatch, client):
    _market_file()
    _no_walking(monkeypatch)
    got = newdata.served_count("market", "series_ids", now=NOW)
    assert got == {"name": "series_ids", "rows": 3, "rows_status": newdata.COUNTED}
    body = client.get("/api/build/served/market/count/series_ids").get_json()
    assert body["ok"] is True and body["kind"] == "market" and body["rows"] == 3
    assert client.get("/api/build/served/market/count/nope").status_code == 404
    assert client.get("/api/build/served/market/count/build_manifest").status_code == 404, "bookkeeping is not data"


def test_two_callers_that_miss_the_same_key_compute_it_once(monkeypatch):
    """#1535's second finding: a call that started while the first was still running paid 80.5 s of its own."""
    _market_file()
    _no_walking(monkeypatch)
    started, release, calls = threading.Event(), threading.Event(), []
    real = newdata._read_served

    def slow(kind):
        calls.append(kind)
        started.set()
        assert release.wait(10), "the test never let the first read finish"
        return real(kind)

    monkeypatch.setattr(newdata, "_read_served", slow)
    threads = [threading.Thread(target=lambda: newdata.served("market", now=NOW)) for _ in range(2)]
    threads[0].start()
    assert started.wait(10), "the first reader never began"
    threads[1].start()
    # The second caller is inside the miss while the first still holds it; give it the moment it needs to get
    # there, then let the first one finish. Without the single-flight lock it reads the file itself meanwhile.
    time.sleep(0.2)
    release.set()
    for t in threads:
        t.join(10)
        assert not t.is_alive(), "a reader did not finish"
    assert calls == ["market"], f"the file was read {len(calls)} times for one cache key"
