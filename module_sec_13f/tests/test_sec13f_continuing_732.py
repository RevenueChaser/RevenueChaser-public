"""#732 decisions B and H (avo 16 Nov 2026): Δ%, Streak and Net flow count only the filers that reported in both
quarters, Net flow as % of shares outstanding; the ⚠ marks a ticker only when its newest settled quarter's breaks
hold at least 5% of its 13F shares, while every listed quarter stays in the row detail.
"""
from __future__ import annotations

import pytest

from revenuechaser.module_sec_13f import report

Q1, Q2 = "2026-03-31", "2026-06-30"
META = {"AAA": {"name": "Alpha", "sector": "Technology"}}


def _cell(shares):
    return {"shares": shares, "value": 1.0, "holders": 3, "new_holders": 0, "exited_holders": 0, "buy_flow": 0.0,
            "sell_flow": 0.0, "complete": True, "closed": True}


def _row(totals, inputs):
    (row,) = report.board_payload(totals, META, inputs)["rows"]
    return dict(zip(report.board_payload(totals, META, inputs)["cols"], row[3])), row


def test_a_filer_that_stopped_reporting_is_not_a_sale():
    # 1,000 -> 900: a filer with 100 stopped filing; the others held still. Total -10%, continuing 0%.
    totals = {"AAA": {Q1: _cell(1000.0), Q2: _cell(900.0)}}
    inputs = {"AAA": {"shares_outstanding": 10_000.0,
                      "breaks": [{"period": Q2, "kind": "stopped", "shares": 100.0, "cik": "1", "filer_name": "F"}]}}
    cells, row = _row(totals, inputs)
    assert cells[f"ch_{Q2}"][1] == pytest.approx(0.0)
    assert cells["netflow"][1] == pytest.approx(0.0) and cells["streak"][1] == 0
    assert row[5] is True                       # the stopped filer held 10% of Q1's shares: marked


def test_net_flow_is_the_continuing_change_as_a_share_of_shares_outstanding():
    # 1,000 -> 1,250, of which 200 is a filer that started; the continuing filers added 50 (+5%).
    totals = {"AAA": {Q1: _cell(1000.0), Q2: _cell(1250.0)}}
    inputs = {"AAA": {"shares_outstanding": 10_000.0,
                      "breaks": [{"period": Q2, "kind": "started", "shares": 200.0, "cik": "1", "filer_name": "N"}]}}
    cells, _ = _row(totals, inputs)
    assert cells[f"ch_{Q2}"][1] == pytest.approx(5.0)
    assert cells["netflow"][0] == "+0.50%" and "+50 shares" in cells["netflow"][3]
    assert cells["streak"][1] == 1


def test_only_the_newest_settled_quarter_at_five_percent_carries_the_mark():
    totals = {"AAA": {Q1: _cell(1000.0), Q2: _cell(1000.0)}}
    old_break = {"period": Q1, "kind": "stopped", "shares": 300.0, "cik": "1", "filer_name": "Old"}
    small_new = {"period": Q2, "kind": "started", "shares": 40.0, "cik": "2", "filer_name": "Small"}     # 4%
    _, row = _row(totals, {"AAA": {"breaks": [old_break, small_new]}})
    assert row[5] is False and [b[0] for b in row[4]] == ["2026 Q2", "2026 Q1"]    # still listed, not marked
    big_new = {**small_new, "shares": 50.0}                                                             # 5%
    _, row = _row(totals, {"AAA": {"breaks": [old_break, big_new]}})
    assert row[5] is True
