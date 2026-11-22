"""board_settings — overrides in the store, defaults always from config (#40)."""
from __future__ import annotations

import pytest

from revenuechaser.core import board_settings as bs
from revenuechaser.core import rawstore
from revenuechaser.module_comovement import config

B = "module_comovement"


def test_default_comes_from_config_at_call_time(rawstore_tmp_db, monkeypatch):
    assert bs.get(B, "WINSOR_K") == config.WINSOR_K
    monkeypatch.setattr(config, "WINSOR_K", 6.0)
    assert bs.get(B, "WINSOR_K") == 6.0          # not copied at import or on first read
    assert bs.values(B)["overridden"] == []












@pytest.mark.parametrize("change,needle", [
    ({"WINDOW": 100}, "WINDOW must be one of 21, 42, 126, 189, 252, 378"),
    ({"MIN_OBS": 59}, "MIN_OBS must be at least 60"),
    ({"MIN_OBS": 300}, "MIN_OBS must be between 60 and WINDOW (252)"),
    ({"OOS_HOLDOUT": 41}, "OOS_HOLDOUT must be between 42 and 126"),
    ({"OOS_HOLDOUT": 127}, "OOS_HOLDOUT must be between 42 and 126"),
    ({"WINSOR_K": 3.9}, "WINSOR_K must be between 4 and 8"),
    ({"WINSOR_K": 8.1}, "WINSOR_K must be between 4 and 8"),
    ({"MIN_PERIODS": 19}, "MIN_PERIODS must be at least 20"),
    ({"BENCH_STALE_SESSIONS": -1}, "BENCH_STALE_SESSIONS must be between 0 and 5"),
    ({"BENCH_STALE_SESSIONS": 6}, "BENCH_STALE_SESSIONS must be between 0 and 5"),
    ({"MIN_OBS": 63.5}, "MIN_OBS must be a whole number"),
    ({"WINSOR_K": "abc"}, "WINSOR_K must be a number"),
    ({"MIN_OBS": True}, "MIN_OBS must be a whole number"),
    ({"NOPE": 1}, "unknown setting 'NOPE'"),
])
def test_validate_every_bound_names_its_rule(rawstore_tmp_db, change, needle):
    msgs = bs.validate(B, change)
    assert any(needle in m for m in msgs), msgs


def test_cross_rule_min_periods_not_above_min_obs(rawstore_tmp_db):
    msgs = bs.validate(B, {"MIN_OBS": 80, "MIN_PERIODS": 90})
    assert any("MIN_PERIODS must be between 20 and MIN_OBS (80)" in m for m in msgs), msgs
    assert bs.validate(B, {"MIN_OBS": 80, "MIN_PERIODS": 80}) == []




def test_cross_rule_window_plus_holdout_fits_stored_sessions(rawstore_tmp_db):
    # 504 when SPY is not stored: the widest allowed pair (378 + 126) fits exactly
    assert bs.stored_sessions() == 504
    assert bs.validate(B, {"WINDOW": 378, "OOS_HOLDOUT": 126}) == []








def test_empty_change_set_is_invalid(rawstore_tmp_db):
    assert bs.validate(B, {}) and bs.validate(B, None)


def test_unknown_board_raises(rawstore_tmp_db):
    with pytest.raises(KeyError):
        bs.values("module_nope")
    assert bs.boards() == ["llm_writers", "module_comovement", "module_fundamentals", "module_relatedness",
                           "module_settings", "module_swing_potential"]




# ── PR 2: the type filter and Fundamentals' thresholds are settings ──────────────────────────────




# ── The control board's universe (design v28, Karar 86 A: a press drafts, Apply commits) ─────────────────────────

def test_the_universe_defaults_to_every_offered_set_and_every_named_group(rawstore_tmp_db):
    v = bs.values("module_settings")
    assert v["values"] == {"UNIVERSE_SETS": 7, "UNIVERSE_INCLUDE": 7} and v["overridden"] == []




def test_the_universe_masks_are_named_by_the_screens_own_lists():
    from revenuechaser.rcdata.needs import screen
    from revenuechaser.rcdata.build import base
    assert bs.UNIVERSE_SET_BITS == {s.key: 1 << i for i, s in enumerate(x for x in screen.UNIVERSE_SETS if x.offered)}
    assert bs.UNIVERSE_INCLUDE_BITS == {g: 1 << i for i, g in enumerate(base.SCOPE_GROUPS)}
