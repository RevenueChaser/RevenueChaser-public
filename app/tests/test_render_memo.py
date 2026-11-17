"""LEAPS and Watch lists re-use their last page while no data file changed (measured on homesrv 17 Nov 2026: Watch
lists ~1.9 s and LEAPS' payload ~1.06 s cold on every load, a 304 included)."""
from __future__ import annotations

import os

import pytest

from RevenueChaser.app import dashboard
from RevenueChaser.module_leaps import board as leaps_board
from RevenueChaser.module_watchlists import board as wl_board
from RevenueChaser.rcdata.tests.conftest import market_roots  # noqa: F401


@pytest.fixture
def builds(monkeypatch, market_roots):  # noqa: F811
    """Counts every payload build; the pages are tiny stand-ins so only the memo is under test."""
    dashboard._RENDER_MEMO.clear()
    count = {"module_leaps": 0, "module_watchlists": 0}

    def leaps_payload(session):
        count["module_leaps"] += 1
        return {"n": count["module_leaps"]}

    def wl_payload(list_id):
        count["module_watchlists"] += 1
        return {"n": count["module_watchlists"]}

    monkeypatch.setattr(leaps_board, "payload", leaps_payload)
    monkeypatch.setattr(leaps_board, "render_html", lambda d: f"<p>leaps {d['n']}</p>")
    monkeypatch.setattr(wl_board, "payload", wl_payload)
    monkeypatch.setattr(wl_board, "render_html", lambda d: f"<p>lists {d['n']}</p>")
    ssd, _ = market_roots
    ssd.mkdir(parents=True, exist_ok=True)
    yield count, ssd
    dashboard._RENDER_MEMO.clear()


@pytest.mark.parametrize("mod", ["module_leaps", "module_watchlists"])
def test_an_unchanged_board_is_not_built_again(builds, mod):
    count, _ = builds
    c = dashboard.app.test_client()
    first = c.get(f"/view/{mod}").get_data(as_text=True)
    second = c.get(f"/view/{mod}").get_data(as_text=True)
    assert count[mod] == 1
    assert first == second


@pytest.mark.parametrize("mod", ["module_leaps", "module_watchlists"])
def test_a_changed_serving_file_builds_the_page_again(builds, mod):
    count, ssd = builds
    c = dashboard.app.test_client()
    f = ssd / "options.duckdb"
    f.write_bytes(b"a")
    assert "1</p>" in c.get(f"/view/{mod}").get_data(as_text=True)
    f.write_bytes(b"ab")                                   # a build swap: new size
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 1_000_000_000))
    assert "2</p>" in c.get(f"/view/{mod}").get_data(as_text=True)
    assert count[mod] == 2


def test_another_session_or_list_is_built_for_itself(builds):
    count, _ = builds
    c = dashboard.app.test_client()
    c.get("/view/module_leaps?session=2026-11-13")
    c.get("/view/module_leaps?session=2026-11-14")
    c.get("/view/module_watchlists?list=a")
    c.get("/view/module_watchlists?list=b")
    assert count == {"module_leaps": 2, "module_watchlists": 2}
