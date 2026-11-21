"""#310 — the three non-visual nits of the v28 review that were left open (N8, N11, N12).

N9 and N10 are the screen itself and belong to the v2 redesign, so they are not here.
N13 was closed by #1164 (``newdata._serving_facts`` guards its reads); ``test_newdata_mid_swap_310.py`` holds it.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from RevenueChaser.module_settings import control, control_render
from RevenueChaser.module_settings.tests.test_control_view import control_nd

NOW = datetime(2026, 10, 30, 17, 31, tzinfo=timezone.utc)


def test_the_storage_map_is_on_the_view_once_and_not_on_every_file():
    """N8: each of the six file views carried the whole ``storage["datasets"]`` map -- six references to one map,
    and a view that looks like it holds its own file's folders while holding every dataset's.

    It sits on the view once now, and the journey table of each file is handed it.
    """
    view = control.build(control_nd(), now=NOW)
    files = view["files"]
    assert files, "the fixture has file views"
    for f in files:
        assert "storage" not in f, f'{f["kind"]} still carries a copy of the whole datasets map'
        assert "roots" in f and "walked_at" in f, "what the journey table reads off the file itself stays"
    assert view["storage"] == (control_nd()["storage"]["datasets"]), "the one copy is the view's"
    assert "52 files" in control_render.render_data(view), "and the journey table still reads it"


def test_the_bars_calendar_states_no_universe_size():
    """N11: ``_cal_bars`` passed ``"universe": size`` and nothing has read it since the M1 fix; the page colours
    the cells from the applied sets in the browser (``onSets()`` / ``uniN()``)."""
    view = control.build(control_nd(), now=NOW)
    cal = view["calendars"]["alpaca/bars"]
    assert "universe" not in cal, "a dead field is a field the next reader believes"
    assert cal["names_per_session"] and cal["page"], "what the calendar really plans off stays"


def test_a_folder_the_walk_never_reached_says_so_rather_than_zero():
    """N12: the walk's budget runs out and a folder reports ``files: 0, capped: True``, which the journey table
    printed as "0+ files" -- the one thing it does not mean is an empty folder.

    The ``N+`` floor of a folder the walk *did* count part of is asserted here too, in the same test: on its own it
    passes on the base and would prove nothing (``red-on-base``).
    """
    walked = control_render.render_data(control.build(control_nd(), now=NOW))
    assert "52 files" in walked and "not counted" not in walked

    nd = copy.deepcopy(control_nd())
    nd["storage"]["datasets"]["alpaca/bars"]["raw"] = {"path": "/r/alpaca/bars", "files": 0, "bytes": 0,
                                                       "capped": True}
    out = control_render.render_data(control.build(nd, now=NOW))
    assert "not counted" in out, "a capped folder with nothing counted says so"
    assert "0+ files" not in out

    nd = copy.deepcopy(control_nd())
    nd["storage"]["datasets"]["alpaca/bars"]["raw"] = {"path": "/r/alpaca/bars", "files": 7, "bytes": 1_000,
                                                       "capped": True}
    floor = control_render.render_data(control.build(nd, now=NOW))
    assert "7+ files" in floor and "not counted" not in floor, "a part-counted folder keeps its floor"
