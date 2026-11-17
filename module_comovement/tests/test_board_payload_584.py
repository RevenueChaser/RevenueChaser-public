"""#584: the Co-movement page carries no group or name; it fetches them from its K10 payload file.

The one-file page (``render_comovement_dashboard``) keeps its rows inline for the tests and the hostile guard. The
served page (``render_comovement_board``) returns ``(html, data)``: ``data`` is the packed rows plus ``schema``, and
``None`` for a board with no group, whose page keeps its server-rendered message. A Fetch that clusters nothing
ends with a message instead of "done" (#392, item 3).
"""
from __future__ import annotations

import pytest

from RevenueChaser.app import runners
from RevenueChaser.app.jobs import JobMessage
from RevenueChaser.core import reporting_common as rc
from RevenueChaser.module_comovement import engine, report
from RevenueChaser.module_comovement.tests.test_page_pack_379 import _payload


def test_the_served_page_fetches_its_groups():
    payload = _payload()
    html, data = report.render_comovement_board(payload)
    assert data["schema"] == report.PAYLOAD_SCHEMA == 1
    assert data == {"schema": 1, **report._pack_rows(report._member_rows(payload, applied=True))}
    assert "C </script>" not in html and '"AAA"' not in html          # no name record rides in the page
    assert "var FETCH = true;" in html and "rcPayload(" in html and "Loading the groups" in html


def test_the_one_file_page_keeps_its_rows_inline():
    html = report.render_comovement_dashboard(_payload())
    assert "var FETCH = false;" in html and '"AAA"' in html


def test_an_empty_board_has_no_payload_file():
    from RevenueChaser.module_comovement.tests.test_comovement import _report_payload

    html, data = report.render_comovement_board(_report_payload(clusters={}, cuts=[]))
    assert data is None and "No clusters yet" in html and "var FETCH = false;" in html


def _empty(**kw):
    return {"as_of": "2026-11-17T10:00:00+00:00", "generated_at": "x", "universe_total": 5, "eligible": 2,
            "dropped": [], "cuts": [], "clusters": {}, "fetch": {}, "config_hash": None, "horizon": 1,
            "benchmark": "spy", "benchmark_applied": False}


@pytest.fixture
def out(tmp_path, monkeypatch):
    monkeypatch.setattr(runners, "COMOVEMENT_LATEST", tmp_path / "comovement_latest.html")
    monkeypatch.setattr(runners, "COMOVEMENT_JSON", tmp_path / "comovement" / "comovement_latest.json")
    monkeypatch.setattr(runners, "_freeze_run_id", lambda: "run-1")
    return tmp_path


def test_a_fetch_that_clusters_nothing_says_why(out, monkeypatch):
    monkeypatch.setattr(engine, "run", _empty)
    monkeypatch.setattr(engine, "precompute", lambda **kw: pytest.fail("nothing to precompute"))
    with pytest.raises(JobMessage, match="2 names had enough daily prices"):
        runners.run_comovement(None)
    assert runners.COMOVEMENT_LATEST.exists()                         # the empty board is written first
    assert not rc.payload_path(runners.COMOVEMENT_LATEST).exists()
    # A Refresh is a GET with no job to carry a message: it stays quiet.
    assert runners.run_comovement(None, no_fetch=True) == runners.COMOVEMENT_LATEST


def test_a_refresh_writes_the_payload_file(out, monkeypatch):
    payload = _payload()
    monkeypatch.setattr(engine, "run", lambda **kw: payload)
    runners.run_comovement(None, no_fetch=True)
    pp = rc.payload_path(runners.COMOVEMENT_LATEST)
    import gzip
    import json
    assert json.loads(gzip.decompress(pp.read_bytes()))["schema"] == 1
