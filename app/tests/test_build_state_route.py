"""#446 step 8: ``GET /api/build/state`` serves what each served file's last build did.

The reader itself is tested in ``rcdata/tests/test_build_state.py`` against real builds. What this file pins is
the route around it: a plain ``GET`` with no panel header, one row per kind even when nothing has been built, and
no write anywhere -- the dashboard holds the only writer there is, and a read must not take its lock. Every test
here gets its own empty market root from the root ``conftest``'s ``isolate_ops``, so "nothing built" is the truth.
"""
from __future__ import annotations

import duckdb

from RevenueChaser.core.tests.panel_client import panel_test_client
from RevenueChaser.rcdata import serving


def _app():
    from RevenueChaser.app.dashboard import app
    return app


def test_the_route_answers_a_row_per_kind_before_anything_is_built():
    body = panel_test_client(_app()).get("/api/build/state").get_json()
    assert body["ok"] is True
    rows = {r["kind"]: r for r in body["kinds"]}
    assert set(rows) == set(serving.KINDS)
    for row in rows.values():
        assert row["built"] is False, row
        assert "error" not in row, row
        assert isinstance(row["incremental"], bool) and isinstance(row["by_hand"], list)
    assert rows["prices"]["by_hand"] == ["prices/serving"]      # #446 step 8: its whole build waits for a person


def test_the_route_is_a_read_and_needs_no_panel_header():
    """Every non-GET request needs ``X-RC-Panel``; this one is a GET, so a bare client must get the same answer."""
    r = _app().test_client().get("/api/build/state")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_the_route_opens_no_serving_file_for_writing(monkeypatch):
    """A read-write open would take the writer's lock and could apply the schema manifest to the live file."""
    path = serving.live_path("market")
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(path)) as con:
        con.execute(f"CREATE TABLE {serving.VERSION_TABLE} "
                    "(kind TEXT, version INTEGER, built_at DOUBLE, build_id TEXT, build_mode TEXT)")
        con.execute(f"INSERT INTO {serving.VERSION_TABLE} VALUES ('market', 1, 100.0, 'b1', 'live')")

    opened: list[dict] = []
    real = duckdb.connect
    monkeypatch.setattr(duckdb, "connect", lambda *a, **kw: (opened.append(kw), real(*a, **kw))[1])
    rows = {r["kind"]: r for r in panel_test_client(_app()).get("/api/build/state").get_json()["kinds"]}

    assert opened, "the route opened no file at all"
    assert all(kw.get("read_only") is True for kw in opened), opened
    assert rows["market"]["mode"] == "live" and rows["market"]["build_id"] == "b1"
