"""The two system watch lists (avo, 17 Nov 2026: "sistem watch listleri ... sektör grupları içindeki ETF'leri oraya
ekleyelim. Hem de endüstri grupları içindeki ETF'ler de ayrı bir watch liste"). The code keeps them, from
``core/rotation_reference.py``: the board shows them read-only after avo's lists and the job lists, and a write to
one is refused.
"""
from __future__ import annotations

import pytest

from RevenueChaser.app import dashboard
from RevenueChaser.core.rotation_reference import INDUSTRY_GROUPS, SECTOR_ETF
from RevenueChaser.core.tests.panel_client import panel_test_client
from RevenueChaser.module_watchlists import board, store

pytestmark = pytest.mark.rawstore_schema_from_scratch


@pytest.fixture
def no_data(monkeypatch):
    import pandas as pd
    monkeypatch.setattr(board.read, "ticker_bars", lambda *a, **k: pd.DataFrame(
        columns=["ticker", "session_date", "close", "volume"]))
    monkeypatch.setattr(board.read, "latest_market", lambda *a, **k: {})
    monkeypatch.setattr(board.read, "market_series", lambda *a, **k: [])
    monkeypatch.setattr(board.read, "identity", lambda *a, **k: [])


def _symbols(data) -> list[str]:
    return [row["t"] for section in data["sections"] for row in section["rows"]]


def test_the_system_lists_follow_the_others_and_say_they_are_the_codes(no_data):
    own = store.create_list("Growth")
    lists = board.payload(own)["lists"]
    assert [r["id"] for r in lists] == [own, "jobs.option", "jobs.stock", "system.sectors", "system.industries"]
    assert [r["system"] for r in lists] == [False, False, False, True, True]
    for list_id in board.SYSTEM_LISTS:
        assert store.derive_id(list_id) != list_id                   # one of avo's lists can never take the id


def test_the_sector_list_is_the_11_spdrs_as_us_listings(no_data):
    store.create_list("Growth")
    data = board.payload("system.sectors")
    assert data["list"]["system"] is True and data["list"]["job"] == ""
    assert _symbols(data) == list(SECTOR_ETF.values()) and len(_symbols(data)) == 11
    assert {row["cov"] for s in data["sections"] for row in s["rows"]} == {"us_equity"}


def test_the_industry_list_has_a_section_per_sector_and_every_group_etf_once(no_data):
    store.create_list("Growth")
    data = board.payload("system.industries")
    assert [s["name"].split(" · ")[0] for s in data["sections"]] == list(SECTOR_ETF)
    want = list(dict.fromkeys(t for sector in SECTOR_ETF for _c, _g, s, etfs in INDUSTRY_GROUPS if s == sector
                              for t in etfs))
    assert _symbols(data) == want
    notes = {row["t"]: row["note"] for s in data["sections"] for row in s["rows"]}
    assert notes["KBE"] == "Banks" and notes["SMH"] == "Semiconductors & Semiconductor Equipment"
    industrials = next(s for s in data["sections"] if s["name"].startswith("Industrials"))
    assert "no ETF: Commercial & Professional Services" in industrials["name"]


def test_a_system_list_renders_read_only(no_data):
    store.create_list("Growth")
    html = board.render_html(board.payload("system.industries"))
    assert '<main class="wl wl-job wl-system">' in html and ">System</span>" in html
    assert ".wl-system .wl-add" in html


def test_a_write_to_a_system_list_is_refused(no_data):
    store.create_list("Growth")
    dashboard.app.config["TESTING"] = True
    client = panel_test_client(dashboard.app)
    r = client.post("/api/watchlists/system.sectors/symbol/add", json={"symbol": "NVDA"})
    assert r.status_code == 400
    assert _symbols(board.payload("system.sectors")) == list(SECTOR_ETF.values())
