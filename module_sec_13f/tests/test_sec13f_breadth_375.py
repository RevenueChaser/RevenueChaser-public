"""SEC 13F ownership breadth (#375 F4, Chen-Hong-Stein 2002) as the board and its history carry it.

Breadth is the share of a quarter's 13F filers that hold the name, ``holders / filers`` as a percentage with four
decimals, and ``breadth_chg`` its quarter-over-quarter change in percentage points. The builder computes both
(``rcdata/build/ownership/serve.py``, covered by ``rcdata/tests/test_ownership_serve.py``); what is tested here is
that they reach the board's column and the history row unchanged.

Offline: the ownership serving file and the history store are per-test temp DuckDBs, no SEC or UW request.
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import ledger, rawstore
from RevenueChaser.module_sec_13f import report
from RevenueChaser.rcdata.tests.ownership_fixture import serve_13f

Q1, Q2 = "2026-03-31", "2026-06-30"
RUN_AT = 1759701600.0        # a fixed instant after Q1/Q2 above, never "today"


def _cell(holders, breadth, breadth_chg, shares=100.0):
    return {"shares": shares, "value": shares * 10.0, "holders": holders, "new_holders": None,
            "exited_holders": None, "top10_pct": 100.0, "hhi": 10000.0, "buy_flow": None, "sell_flow": None,
            "breadth": breadth, "breadth_chg": breadth_chg}


# Q1 has two filers, Q2 four, as the builder counted them: AAA 1 then 2 holders (50.0, 50.0), BBB 1 both
# quarters (50.0, 25.0), CCC 2 then 2 (100.0, 50.0).
TOTALS = {"AAA": {Q1: _cell(1, 50.0, None), Q2: _cell(2, 50.0, 0.0)},
          "BBB": {Q1: _cell(1, 50.0, None, shares=50.0), Q2: _cell(1, 25.0, -25.0, shares=50.0)},
          "CCC": {Q1: _cell(2, 100.0, None, shares=20.0), Q2: _cell(2, 50.0, -50.0, shares=20.0)}}


@pytest.fixture
def store(rawstore_tmp_db):
    serve_13f(TOTALS)
    return rawstore_tmp_db


def _totals():
    return TOTALS






def test_the_board_shows_breadth_between_new_exit_and_top10_with_the_lag_legend():
    """Test 6: the column and the 'filed up to 45 days later' label the signal depends on."""
    totals = {"AAA": {Q1: {"shares": 100.0, "value": 1000.0, "holders": 1, "new_holders": None,
                           "exited_holders": None, "top10_pct": 100.0, "hhi": 10000.0,
                           "buy_flow": None, "sell_flow": None, "breadth": 50.0, "breadth_chg": None},
                      Q2: {"shares": 100.0, "value": 1000.0, "holders": 2, "new_holders": 1,
                           "exited_holders": 0, "top10_pct": 100.0, "hhi": 5000.0,
                           "buy_flow": 100.0, "sell_flow": 0.0, "breadth": 50.0, "breadth_chg": 0.0}}}
    payload = report.board_payload(totals, {"AAA": {"name": "Aaa"}}, {})
    cols = payload["cols"]
    assert cols.index("breadth") == cols.index("new_exit") + 1 == cols.index("top10") - 1
    cells = dict(zip(cols, payload["rows"][0][3]))
    assert cells["breadth"] == ["50.00% (+0.00)", 50.0, "zero", "as of 2026 Q2"]
    html = report.render_sec13f_dashboard(totals, {"AAA": {"name": "Aaa"}}, {})
    assert "<b>Breadth</b>" in html
    assert "filed up to 45 days later" in html
    assert "holders ÷ filers" in html


def test_a_row_without_breadth_renders_an_empty_cell():
    totals = {"AAA": {Q1: {"shares": 100.0, "value": 1000.0, "holders": 1,
                           "top10_pct": 100.0, "hhi": 10000.0}}}
    payload = report.board_payload(totals, {"AAA": {"name": "Aaa"}}, {})
    assert dict(zip(payload["cols"], payload["rows"][0][3]))["breadth"] == ["—", None, "zero", "as of 2026 Q1"]


