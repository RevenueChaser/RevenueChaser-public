"""SEC 13F board -> result history (#375, A3). Offline; the store is a temp DuckDB, no SEC or UW request.

``record`` hands ``core/history.record_run`` one ``sec13f_metrics_history`` row per board row, built from the same
entries the board renders. Quarter board: every run keeps its rows; ``sec13f_metrics_by_quarter`` takes each
quarter's last run without an error. Names not refreshed make the run partial; unmatched CUSIPs are a warning.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_sec_13f import engine, report
from RevenueChaser.rcdata.tests.ownership_fixture import serve_13f

Q1, Q2, Q3 = "2025-12-31", "2026-03-31", "2026-06-30"
COMPLETE = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc).timestamp()


def _cell(shares, **kw):
    return {"shares": shares, "value": shares * 10.0, "holders": 5, "new_holders": 2, "exited_holders": 1,
            "top10_pct": 40.0, "hhi": 900.0, "buy_flow": 30.0, "sell_flow": 10.0, **kw}


TOTALS = {"AAA": {Q1: _cell(100.0), Q2: _cell(150.0), Q3: _cell(300.0, holders=9)},
          "BBB": {Q1: _cell(500.0), Q2: _cell(400.0)}}
META = {"AAA": {"name": "Aaa Corp", "sector": "Technology"}, "BBB": {"name": "Bbb Inc", "sector": "Energy"}}
ENRICH = {"AAA": {"price": {Q1: 10.0, Q3: 15.0}, "shares_outstanding": 1000.0, "float_shares": 900.0,
                  "short_pct": 2.5, "insider_pct": 1.5}}
CUSIPS = {"AAA": ["222222222", "111111111"], "BBB": ["333333333"]}
SHOWN = {"totals": TOTALS, "meta": META, "enrichment": ENRICH}


@pytest.fixture(autouse=True)
def served():
    """The builder's tables the board and the history read (G9)."""
    serve_13f(TOTALS, cusips=CUSIPS)


@pytest.fixture
def store(rawstore_tmp_db):
    return rawstore_tmp_db




























def test_the_board_renders_the_same_entries():
    html = report.render_sec13f_dashboard(TOTALS, META, ENRICH)
    assert "AAA" not in html and "BBB" not in html            # rows live in the payload (#429)
    payload = report.board_payload(TOTALS, META, ENRICH)
    assert [row[0] for row in payload["rows"]] == ["AAA", "BBB"]
    aaa = dict(zip(payload["cols"], payload["rows"][0][3]))
    assert aaa["pct_out"] == ["30.0%", 30.0, "zero", "as of 2026 Q2"]
    assert aaa["price_delta"] == ["+50.0%", 50.0, "pos"]
