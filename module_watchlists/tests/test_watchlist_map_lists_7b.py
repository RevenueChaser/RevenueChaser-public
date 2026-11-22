"""Plan v5 step 7b (#1031): the Sector Rotation map and its industry layer are two of avo's watch lists.

They were dicts in ``core/rotation_reference.py``, shown on this board as read-only "system" lists. Now they are
lists of ``watchlists.duckdb`` marked for the jobs (``feeds`` = ``map`` / ``industry``), made once from that seed,
edited here, and read by every job through ``rotation_reference`` strictly: no list is an error, never the seed.
The board shows a fund's hand-written short name beside the label its holdings give, so neither passes for the other.
"""
from __future__ import annotations

import pytest

from revenuechaser.app import dashboard
from revenuechaser.core import rotation_reference as ref
from revenuechaser.core.tests.panel_client import panel_test_client
from revenuechaser.module_watchlists import board, store
from revenuechaser.rcdata import read

pytestmark = [pytest.mark.rawstore_schema_from_scratch, pytest.mark.map_lists_from_store]


@pytest.fixture
def no_data(monkeypatch):
    import pandas as pd
    monkeypatch.setattr(board.read, "ticker_bars", lambda *a, **k: pd.DataFrame(
        columns=["ticker", "session_date", "close", "volume"]))
    monkeypatch.setattr(board.read, "latest_market", lambda *a, **k: {})
    monkeypatch.setattr(board.read, "market_series", lambda *a, **k: [])
    monkeypatch.setattr(board.read, "identity", lambda *a, **k: [])
    monkeypatch.setattr(board.read, "etf_class", lambda etfs=(), **k: [
        {"ticker": "SMH", "primary_class": "industry_group", "code": "4530",
         "label": "Semiconductors & Semiconductor Equipment"},
        {"ticker": "IWM", "primary_class": "diversified", "code": None, "label": None}])


@pytest.fixture
def client(no_data):
    dashboard.app.config["TESTING"] = True
    return panel_test_client(dashboard.app)


# ── the strict read ──────────────────────────────────────────────────────────────────────────────────────────────

def test_with_no_list_the_map_is_an_error_never_the_seed():
    with pytest.raises(read.JobListUnreadable):
        ref.rotation_etfs()
    store.create_list("Growth")                       # the file is there now, but no list is marked for the map
    with pytest.raises(read.JobListUnreadable):
        ref.rotation_etfs()
    with pytest.raises(read.JobListUnreadable):
        ref.industry_groups()


def test_the_seed_makes_both_lists_once_and_they_read_back_as_the_seed():
    first = store.seed_map_lists()
    funds = sum(1 for i in ref.SEED_ROTATION_ETFS.values() if i["group"] not in ref.MACRO_GROUPS)
    assert first["map"] == {"created": True, "seed": funds, "list": funds, "same": True}
    assert first["industry"]["created"] and first["industry"]["same"]
    assert first["industry"]["seed"] == sum(len(e) for *_x, e in ref.SEED_INDUSTRY_GROUPS)
    assert ref.rotation_etfs() == ref.SEED_ROTATION_ETFS                 # every fund, its group and short name
    assert ref.industry_groups() == ref.SEED_INDUSTRY_GROUPS             # the empty groups and each group's order
    assert ref.sector_etf()["Technology"] == "XLK" and len(ref.sector_etf()) == 11
    assert ref.industry_map_etfs()[:2] == ("XLE", "XLB")
    again = store.seed_map_lists()
    assert not again["map"]["created"] and again["map"]["same"] and len(store.lists()) == 2


def test_an_edit_on_the_board_reaches_every_reader_and_the_seed_does_not_come_back():
    store.seed_map_lists()
    assert "XLK" in ref.rotation_etfs()                                  # read once: the next read must not be stale
    store.add_symbol("jobs.map", "BOTZ", section_id="theme", note="Robots")
    store.remove_symbol("jobs.map", "XLK")
    now = ref.rotation_etfs()
    assert now["BOTZ"] == {"name": "Robots", "group": "theme"} and "XLK" not in now
    assert "Technology" not in ref.sector_etf()
    assert "US10Y" in now                                                # the macro indicators are not on a list
    assert store.seed_map_lists()["map"] == {"created": False, "seed": len(now) - len(ref.MACRO_INDICATORS),
                                             "list": len(now) - len(ref.MACRO_INDICATORS), "same": False}


def test_the_first_fund_of_a_group_is_the_one_on_the_map():
    store.seed_map_lists()
    assert dict((g, e) for _c, g, _s, e in ref.industry_groups())["Banks"] == ("KBE", "KRE")
    store.reorder("jobs.industry", "4010", ["KRE", "KBE"])
    assert "KRE" in ref.industry_map_etfs() and "KBE" not in ref.industry_map_etfs()


def test_the_prices_build_and_the_spine_read_the_list():
    from revenuechaser.rcdata.build import prices
    with pytest.raises(read.JobListUnreadable):
        prices.rotation()
    store.seed_map_lists()
    assert "XLK" in prices.rotation() and "US10Y" not in prices.rotation()
    assert ref.sector_etf()["Technology"] == "XLK"


def test_a_map_list_cannot_be_deleted_or_emptied():
    store.seed_map_lists()
    with pytest.raises(store.WatchlistError):
        store.delete_list("jobs.map")
    assert "jobs.map" in {r["list_id"] for r in store.lists()}


# ── the board ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_map_lists_sit_under_read_by_the_jobs_and_no_system_list_is_left(no_data):
    own = store.create_list("Growth")
    store.seed_map_lists()
    data = board.payload(own)
    assert [r["id"] for r in data["lists"]] == [own, "jobs.option", "jobs.stock", "jobs.map", "jobs.industry"]
    assert [r["fed"] for r in data["lists"]] == ["", "", "", "map", "industry"]
    html = board.render_html(data)
    assert ">Read by the jobs</span>" in html and ">System</span>" not in html
    assert not hasattr(board, "SYSTEM_LISTS")


def test_a_row_shows_the_hand_written_name_beside_the_label_from_holdings(no_data):
    store.seed_map_lists()
    data = board.payload("jobs.map")
    assert data["list"]["fed"] == "map" and data["list"]["job"] == ""    # edited like one of avo's own lists
    assert [s["id"] for s in data["sections"]][:2] == ["sector", "theme"]
    rows = {row["t"]: row for s in data["sections"] for row in s["rows"]}
    assert rows["SMH"]["note"] == "Semiconductors"
    assert rows["SMH"]["lab"] == "industry group · Semiconductors & Semiconductor Equipment"
    assert rows["IWM"]["note"] == "US Small Caps" and rows["IWM"]["lab"] == "diversified"
    assert rows["XLK"]["lab"] is None                                    # no label yet: said, not guessed
    assert {row["cov"] for row in rows.values()} == {"us_equity"}
    html = board.render_html(data)
    assert "function handHtml" in html and "from holdings: " in html


def test_one_of_avos_own_lists_has_no_second_line(no_data):
    own = store.create_list("Growth")
    store.add_symbol(own, "NASDAQ:NVDA")
    data = board.payload(own)
    assert data["list"]["fed"] == "" and "lab" not in data["sections"][0]["rows"][0]


def test_the_short_name_is_edited_on_the_board(client):
    store.seed_map_lists()
    r = client.post("/api/watchlists/jobs.map/symbol/note", json={"symbol": "SMH", "note": "Chips"})
    assert r.status_code == 200
    assert ref.rotation_etfs()["SMH"]["name"] == "Chips"
    assert store.changes("jobs.map")[0]["action"] == "note"
    assert client.post("/api/watchlists/jobs.map/symbol/note", json={"symbol": "NOPE", "note": "x"}).status_code == 400


def test_the_seed_route_makes_the_map_lists_beside_the_job_lists(client):
    answer = client.post("/api/watchlists/jobs/seed").get_json()
    assert answer["ok"] and answer["map"]["created"] and answer["map"]["same"] and answer["industry"]["same"]
    assert set(answer) >= {"option", "stock", "map", "industry"}
