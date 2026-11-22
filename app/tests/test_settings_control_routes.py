"""The Settings / Data control board's two writes and one read (design v28, 30 Oct 2026).

**Apply** saves the universe the board's presses ask for: a press on a tier set only drafts, and Apply posts the
draft to the boards' settings route (Karar 86 A), which stores it and re-renders the Settings card store-only. It
saves a choice and fetches nothing. **Refresh the example rows** (Karar 90 A) reads five rows of one serving table
again, read-only, and calls no provider.
"""
from __future__ import annotations

import pytest

from revenuechaser.core import board_settings as bs
from revenuechaser.core import rawstore
from revenuechaser.core.tests.panel_client import panel_test_client


@pytest.fixture
def client(rawstore_tmp_db, monkeypatch):
    from revenuechaser.app import dashboard
    submitted = []
    monkeypatch.setattr(dashboard.jobs, "submit",
                        lambda module, params=None: submitted.append((module, params)) or "job7")
    dashboard.app.config["TESTING"] = True
    c = panel_test_client(dashboard.app)
    c.submitted = submitted
    return c






# --- Refresh the example rows: one read-only SELECT of a serving table, no cache, no provider ------------------------

import duckdb  # noqa: E402

from revenuechaser.module_settings import newdata  # noqa: E402
from revenuechaser.rcdata import serving  # noqa: E402
from revenuechaser.rcdata.build.prices import serving as prices_serving  # noqa: E402
from revenuechaser.rcdata.tests.conftest import market_roots  # noqa: E402,F401 - market roots per test


def _bars(days):
    path = serving.live_path("prices")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        cols = ", ".join(f'"{c}" {t}' for c, t in prices_serving.SCHEMAS["price_bar_daily"])
        con.execute(f"CREATE TABLE price_bar_daily ({cols})")
        for i, day in enumerate(days):
            con.execute("INSERT INTO price_bar_daily (security_id, session_date, close, source) VALUES "
                        "(?, ?, ?, 'alpaca/bars')", [f"S{i}", day, float(i)])
    finally:
        con.close()


@pytest.fixture
def reads(monkeypatch):
    """Every serving file the route opens."""
    opened = []
    real = serving.open_read
    monkeypatch.setattr(serving, "open_read", lambda kind: opened.append(kind) or real(kind))
    newdata.clear_sample_cache()
    yield opened
    newdata.clear_sample_cache()


def _get(client, table):
    """GET the sample route with every DuckDB file it opens held to read-only."""
    connect = duckdb.connect

    def guarded(path=":memory:", read_only=False, **kw):
        assert read_only, f"the sample route opened {path} for writing"
        return connect(path, read_only=read_only, **kw)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(duckdb, "connect", guarded)
        return client.get(f"/api/settings/sample/{table}")


def test_refresh_reads_the_newest_five_rows_read_only(client, market_roots, reads):
    days = [f"2026-10-{d:02d}" for d in range(20, 29)]
    _bars(days)
    r = _get(client, "price_bar_daily")
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["ok"] is True and body["table"] == "price_bar_daily"
    names = [c["name"] for c in body["columns"]]
    assert names == [c for c, _ in prices_serving.SCHEMAS["price_bar_daily"]]
    day = names.index("session_date")
    assert [row[day] for row in body["rows"]] == sorted(days, reverse=True)[:newdata.SAMPLE_ROWS]
    assert reads == ["prices"], "one read-only handle on the table's own file, nothing else"
    assert client.submitted == [], "a read queues no job"


def test_refresh_reads_again_rather_than_answering_from_the_hourly_cache(client, market_roots, reads, monkeypatch):
    _bars(["2026-10-27", "2026-10-28"])
    monkeypatch.setattr(newdata, "_sample_key", lambda table, now: "this hour")
    stale = {"columns": [{"name": "close", "type": "DOUBLE"}], "rows": [[0.5]]}
    assert newdata._cached_sample("price_bar_daily", None, lambda t: stale) is stale
    fresh = _get(client, "price_bar_daily").get_json()
    assert len(fresh["rows"]) == 2, "the press reads the file, not the page's hourly sample"
    assert newdata._cached_sample("price_bar_daily", None, lambda t: stale)["rows"] == fresh["rows"], \
        "and the next render shows what the press read"




def test_a_file_never_built_is_409_and_says_so(client, market_roots, reads):
    r = _get(client, "price_bar_daily")
    assert r.status_code == 409
    assert r.get_json() == {"ok": False, "error": "the prices file has not been built yet"}


def test_a_table_missing_from_its_built_file_is_409(client, market_roots, reads):
    path = serving.live_path("prices")
    path.parent.mkdir(parents=True, exist_ok=True)
    duckdb.connect(str(path)).close()
    r = _get(client, "price_bar_daily")
    assert r.status_code == 409 and "price_bar_daily" in r.get_json()["error"]


def test_a_file_that_cannot_be_read_right_now_is_503_not_a_crash(client, market_roots, reads, monkeypatch):
    """Review S5: a press during a serving swap (the file locked or half-written) says so; it is not a 500."""
    _bars(["2026-10-28"])

    def locked(kind):
        raise duckdb.IOException("Could not set lock on file")
    monkeypatch.setattr(serving, "open_read", locked)
    r = _get(client, "price_bar_daily")
    assert r.status_code == 503
    body = r.get_json()
    assert body["ok"] is False and "could not be read right now" in body["error"] and "lock" in body["error"]


def test_a_blocks_first_open_answers_this_hours_sample_without_opening_the_file(client, market_roots, reads,
                                                                                monkeypatch):
    _bars(["2026-10-27", "2026-10-28"])
    monkeypatch.setattr(newdata, "_sample_key", lambda table, now: "this hour")
    hourly = {"columns": [{"name": "close", "type": "DOUBLE"}], "rows": [[0.5]]}
    newdata._cached_sample("price_bar_daily", None, lambda t: hourly)
    body = client.get("/api/settings/sample/price_bar_daily?cached=1").get_json()
    assert body["rows"] == [[0.5]] and reads == [], "the page already read it this hour"


def test_a_long_text_cell_is_cut_in_the_example():
    long = "x" * 5000
    assert newdata._cell(long) == "x" * newdata.SAMPLE_CELL_CHARS + "… (5,000 characters)"
    assert newdata._cell("short") == "short" and newdata._cell(3) == 3


def test_the_lookup_names_come_from_their_own_route(client, monkeypatch):
    from revenuechaser.module_settings import inventory
    monkeypatch.setattr(inventory, "_universe_tickers", lambda: ([{"ticker": "AAA", "name": "A Co"}], None))
    assert client.get("/api/settings/tickers").get_json() == {"ok": True, "tickers": [{"ticker": "AAA", "name": "A Co"}]}
    monkeypatch.setattr(inventory, "_universe_tickers", lambda: ([], "IOException: locked"))
    r = client.get("/api/settings/tickers")
    assert r.status_code == 503 and r.get_json()["ok"] is False


# --- #338: every served table the board draws the button for answers it, none is "unknown table" ---------------

from revenuechaser.rcdata.build import DATASETS as _DATASETS  # noqa: E402
from revenuechaser.rcdata.build.fundamentals import tables as fundamentals_tables  # noqa: E402

SERVED_TABLES = sorted({t for ds in _DATASETS.values() for t in ds.tables})


def test_every_served_table_answers_the_refresh_and_is_never_unknown(client, market_roots, reads):
    """The board draws "Refresh the example rows" for every table a dataset serves, so pressing it must never
    answer 404 "unknown table" (#338: seven tables did). With no serving file built the honest answer is 409.

    One test over the whole set rather than a case per table: the question is whether *any* served table is
    unknown to the route, and the set grows with the build registry.
    """
    assert SERVED_TABLES, "no dataset serves a table: the registry did not load"
    unknown = {t: _get(client, t).status_code for t in SERVED_TABLES}
    assert {t: code for t, code in unknown.items() if code != 409} == {}, \
        "a served table the route does not know: 404 is the board's button answering 'unknown table'"


def _peers(rows):
    path = serving.live_path("fundamentals")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        cols = ", ".join(f'"{c}" {t}' for c, t in fundamentals_tables.SCHEMAS["peer_group"])
        con.execute(f"CREATE TABLE peer_group ({cols})")
        for cik, ticker in rows:
            con.execute("INSERT INTO peer_group (cik, ticker, peer_cik, peer_ticker, rank, level) VALUES "
                        "(?, ?, '99', 'ZZZ', 1, 'gsubind')", [cik, ticker])
    finally:
        con.close()


def test_a_served_table_no_column_dates_is_read_unordered_and_not_refused(client, market_roots, reads):
    """``peer_group`` is rebuilt whole and carries no day: the press reads it with no ORDER BY, rather than 404."""
    _peers([("1", "AAA"), ("2", "BBB")])
    r = _get(client, "peer_group")
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["ok"] is True and len(body["rows"]) == 2
    assert [c["name"] for c in body["columns"]] == [c for c, _ in fundamentals_tables.SCHEMAS["peer_group"]]
    assert reads == ["fundamentals"]
