"""#167 stage 1 (decisions C and J, avo 16 Nov 2026): the 13F board keeps its rows as data and puts 100 at a time in
the DOM; a sort and a filter work on the array; a row with no 13F shares in any quarter is hidden until asked for.
Run under node against the DOM stub.
"""
from __future__ import annotations

import shutil

import pytest

from RevenueChaser.core import universe
from RevenueChaser.core.tests.board_js import run_board_js
from RevenueChaser.module_sec_13f import report

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")


def _payload(n: int) -> dict:
    """``n`` rows with shares (value i, so the order is known), and one row with no shares at all."""
    rows = [[f"T{i:03d}", "", "Technology", [[str(i), float(i), "zero"], [str(i), float(i), "zero"]], []]
            for i in range(1, n + 1)]
    rows.append(["EMPTY", "", "", [["—", None, "zero"], ["—", None, "zero"]], []])
    return {"cols": ["sh_2026-06-30", "value"], "rows": rows, "fields": {}}


def _run(monkeypatch, tmp_path, tail):
    monkeypatch.setattr(universe, "filter_fields", lambda ts: {})
    monkeypatch.setattr(universe, "theme_catalog", lambda: {})
    html = report.render_sec13f_dashboard({"AAA": {"2026-06-30": {"shares": 1.0, "value": 1.0, "holders": 1}}},
                                          {"AAA": {"name": "A"}}, {})
    return run_board_js(html, tail, tmp_path, payload=_payload(250))


def test_a_hundred_rows_at_a_time_and_the_empty_row_hidden(monkeypatch, tmp_path):
    got = _run(monkeypatch, tmp_path, r"""
var first = {view: VIEW.length, shown: SHOWN, built: Object.keys(ROW_EL).length,
             empty: VIEW.some(function(r){ return r[0] === 'EMPTY'; })};
showMore(); var second = SHOWN;
showMore(); var third = SHOWN;
SHOW_EMPTY = true; applyFilters();
console.log(JSON.stringify({first: first, second: second, third: third, all: VIEW.length,
                            emptyNow: VIEW.some(function(r){ return r[0] === 'EMPTY'; })}));
""")
    assert got["first"] == {"view": 250, "shown": 100, "built": 100, "empty": False}
    assert (got["second"], got["third"]) == (200, 250)
    assert got["all"] == 251 and got["emptyNow"] is True


def test_a_sort_orders_the_whole_array_not_only_the_rows_shown(monkeypatch, tmp_path):
    got = _run(monkeypatch, tmp_path, r"""
var th = {classList: {add: function(){}}};
sortTable('value', th);                       // descending first
var desc = VIEW.slice(0, 2).map(function(r){ return r[0]; });
sortTable('value', th);                       // then ascending
console.log(JSON.stringify({desc: desc, asc: VIEW.slice(0, 2).map(function(r){ return r[0]; }), shown: SHOWN}));
""")
    assert got == {"desc": ["T250", "T249"], "asc": ["T001", "T002"], "shown": 100}


def test_the_search_filters_the_array(monkeypatch, tmp_path):
    got = _run(monkeypatch, tmp_path, r"""
SEARCH_Q = 'T12'; applyFilters();
console.log(JSON.stringify({n: VIEW.length, shown: SHOWN}));
""")
    assert got == {"n": 10, "shown": 10}      # T120-T129
