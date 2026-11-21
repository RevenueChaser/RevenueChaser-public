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


def test_a_file_view_does_not_carry_the_whole_storage_map():
    """N8: every one of the six file views copied ``storage["datasets"]`` whole and nothing read it.

    The journey table reads the map it was given, not the file's copy of it, so the copies were five redundant
    references to the same dict -- and a reader of a file view would have found a map of every dataset on it,
    not of that file's own.
    """
    view = control.build(control_nd(), now=NOW)
    files = view["files"]
    assert files, "the fixture has file views"
    for f in files:
        assert "storage" not in f, f'{f["kind"]} still carries a copy of the whole datasets map'
    assert all("roots" in f and "walked_at" in f for f in files), "what the journey table does read stays"


def test_the_bars_calendar_states_no_universe_size():
    """N11: ``_cal_bars`` passed ``"universe": size`` and nothing has read it since the M1 fix; the page colours
    the cells from the applied sets in the browser (``onSets()`` / ``uniN()``)."""
    view = control.build(control_nd(), now=NOW)
    cal = view["calendars"]["alpaca/bars"]
    assert "universe" not in cal, "a dead field is a field the next reader believes"
    assert cal["names_per_session"] and cal["page"], "what the calendar really plans off stays"


def test_a_folder_the_walk_never_reached_says_so_rather_than_zero():
    """N12: the walk's budget runs out and a folder reports ``files: 0, capped: True``, which the journey table
    printed as "0+ files" -- the one thing it does not mean is an empty folder."""
    nd = control_nd()
    walked = control_render.render_data(control.build(nd, now=NOW))
    assert "52 files" in walked and "not counted" not in walked

    nd = copy.deepcopy(control_nd())
    nd["storage"]["datasets"]["alpaca/bars"]["raw"] = {"path": "/r/alpaca/bars", "files": 0, "bytes": 0,
                                                       "capped": True}
    out = control_render.render_data(control.build(nd, now=NOW))
    assert "not counted" in out, "a capped folder with nothing counted says so"
    assert "0+ files" not in out


def test_a_capped_folder_that_did_count_something_keeps_its_floor():
    """The ``N+`` floor is still the right word when the walk counted some of the folder before it ran out."""
    nd = copy.deepcopy(control_nd())
    nd["storage"]["datasets"]["alpaca/bars"]["raw"] = {"path": "/r/alpaca/bars", "files": 7, "bytes": 1_000,
                                                       "capped": True}
    out = control_render.render_data(control.build(nd, now=NOW))
    assert "7+ files" in out and "not counted" not in out
