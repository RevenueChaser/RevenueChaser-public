"""#446 step 8B: the Settings / Database part "Serving builds".

The part is drawn from a model, so these tests hand it models and read the HTML. What they pin is the wording and
the three rules the part exists to keep: an empty cell is not a zero, the mode is named as the **last** build's,
and one unreadable kind is one row rather than a failed page. The cell-grid and phone rules are pinned on the CSS,
which is where they live.
"""
from __future__ import annotations

import re

from RevenueChaser.module_settings import build_tab, report

LIVE = {"kind": "market", "built": True, "mode": "live", "built_at": 1763600000.0, "build_id": "b-2",
        "version": 7, "parquet_files": 812, "audit_dirty": 3,
        "audit": {"checked_at": 1763600500.0, "keys": 500, "differs": 2, "tables": ["market_series"]},
        "incremental": True, "by_hand": [], "datasets": ["market_series"]}
WHOLE = {**LIVE, "kind": "prices", "mode": "fresh", "build_id": "b-1", "by_hand": ["prices/serving"]}


def _text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def test_the_mode_is_drawn_as_the_last_builds_not_as_a_setting():
    html = build_tab.section({"kinds": [LIVE]})
    assert "live copy" in html
    words = _text(html)
    assert "last" in words.lower()
    # The part says in words that a later code change is not in this answer, so the chip is not read as a promise.
    assert "built whole next time" in words


def test_a_kind_built_whole_is_listed_first_and_says_so():
    html = build_tab.section({"kinds": [LIVE, WHOLE]})
    assert html.index("prices") < html.index("market")
    assert "whole" in _text(html)


def test_the_by_hand_chip_stands_on_the_kind_that_holds_its_whole_build():
    html = build_tab.section({"kinds": [WHOLE]})
    assert "by hand" in html
    assert "by hand" not in build_tab.section({"kinds": [LIVE]})


def test_a_table_the_file_does_not_carry_is_an_empty_cell_and_not_a_zero():
    row = {**LIVE, "parquet_files": None, "audit_dirty": None, "audit": {}}
    html = build_tab.section({"kinds": [row]})
    assert "no audit round yet" in html
    assert ">0<" not in html.replace(" ", "")
    assert "—" in html


def test_zero_differences_is_still_drawn_as_zero():
    """The other half of the rule above: a round that ran and found nothing says 0, not an empty cell."""
    html = build_tab.section({"kinds": [{**LIVE, "audit": {"checked_at": 1763600500.0, "keys": 500, "differs": 0,
                                                           "tables": []}}]})
    assert "0 differ" in _text(html)
    assert "no audit round yet" not in html


def test_nothing_built_yet_is_a_row():
    html = build_tab.section({"kinds": [{"kind": "spine", "built": False, "incremental": False,
                                         "by_hand": [], "datasets": ["spine/x"]}]})
    assert "nothing built yet" in html
    assert "whole every run" in html              # it declares no dirty set, so every run is a whole build


def test_one_unreadable_kind_is_one_row_and_the_others_are_drawn():
    html = build_tab.section({"kinds": [LIVE, {"kind": "options", "error": "IOError: x"}]})
    assert "could not be read" in html and "IOError: x" in html
    assert "live copy" in html                    # the readable kind is still there


def test_a_read_that_failed_whole_is_one_line():
    assert "Could not be read: OSError: x" in build_tab.section({"error": "OSError: x"})
    assert "No serving kind is registered" in build_tab.section({"kinds": []})


def test_every_value_is_escaped():
    html = build_tab.section({"kinds": [{"kind": "<script>", "error": "<img src=x>"}]})
    assert "<script>" not in html and "<img" not in html


def test_the_part_names_no_turkish_and_carries_no_hex_colour():
    """A board shows English only (avo, 19 Nov 2026), and a component uses token names, never a hex value."""
    html = build_tab.section({"kinds": [LIVE, WHOLE]})
    assert not re.search(r"[çğıöşüÇĞİÖŞÜ]", html)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", build_tab.BUILD_CSS)


def test_the_css_sizes_the_columns_not_the_rows_and_stacks_on_a_phone():
    css = build_tab.BUILD_CSS
    assert "table-layout:fixed" in css                       # one grid on the table; a row sizes nothing
    assert "td:first-child{text-align:left" in css.replace("\n", "").replace(" ", "")
    assert "td:last-child{text-align:right" in css.replace("\n", "").replace(" ", "")
    assert "max-width:760px" in css                          # the phone rule covers at least 760 px
    assert "thead{display:none}" in css.replace("\n", "").replace(" ", "")


def test_every_token_the_css_asks_for_is_one_the_frame_defines():
    """The silent failure of DESIGN.md section 1: ``var(--panel)`` renders its fallback and reports nothing, so a
    component can follow no theme at all for months. Every name the part asks for is either a theme token or one of
    the short aliases ``needs.css`` defines on ``#needs``."""
    from RevenueChaser.core.reporting_common import THEME_TOKENS
    from RevenueChaser.module_settings import needs_tab
    asked = set(re.findall(r"var\(--([a-z0-9-]+)", build_tab.BUILD_CSS))
    defined: set[str] = set()
    for scheme in THEME_TOKENS.values():
        defined |= {str(k) for k in scheme}
    defined |= set(re.findall(r"--([a-z0-9-]+):\s*var\(", needs_tab.NEEDS_CSS))
    missing = sorted(asked - defined)
    assert not missing, f"the part's CSS asks for tokens no scheme defines: {missing}"


def test_the_page_draws_the_part_and_its_css():
    html = report._database_more({"build_state": {"kinds": [LIVE]}, "needs": {"error": "skip"}})
    assert 'id="build-state"' in html
    assert "Serving builds" in html


def test_the_model_is_read_from_the_payload_when_a_caller_has_it():
    assert report._build_state({"build_state": {"kinds": []}}) == {"kinds": []}


def test_a_model_read_that_raises_is_an_error_model(monkeypatch):
    monkeypatch.setattr(build_tab, "collect", lambda: (_ for _ in ()).throw(OSError("no disk")))
    model = report._build_state({})
    assert model["error"].startswith("OSError")
