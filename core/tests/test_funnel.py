"""Shared funnel format: one start, per-rule drops, one result."""
from __future__ import annotations

from RevenueChaser.core import funnel






def test_step_builder_shape():
    s = funnel.step("x", "X", 3, "drop", by_design=False,
                    fix={"route": "/run/a", "label": "A"}, tickers=["A", "B"])
    assert s == {"key": "x", "label": "X", "count": 3, "kind": "drop",
                 "by_design": False, "fix": {"route": "/run/a", "label": "A"},
                 "tickers": ["A", "B"]}
    start = funnel.step("s", "S", 1, "start")
    assert "by_design" not in start and start["fix"] is None














# ── a note: shown, never counted (#87) ──────────────────────────────────────
_LINK = {"tab": "module_settings", "anchor": "identity", "label": "Settings → Identity"}




def test_note_is_a_kind():
    assert "note" in funnel.KINDS








def test_step_builder_carries_a_link_only_when_given():
    s = funnel.step("untyped", "U", 3, "note", link=_LINK)
    assert s["link"] == _LINK and s["link"] is not _LINK       # a copy
    assert "link" not in funnel.step("x", "X", 1, "drop", by_design=True)




