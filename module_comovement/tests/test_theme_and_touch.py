"""Co-movement on the shared theme (light and dark, like Fundamentals #840) with phone-sized touch targets.

The board used to carry its own dark-only palette, 24-26 px buttons and a phone rule at 520 px (Co-movement review,
17 Nov 2026, F8). ui-design: light and dark, 44 px targets, a single column below 760 px.
"""
from __future__ import annotations

import re

from RevenueChaser.core.reporting_common import THEME_CSS
from RevenueChaser.module_comovement import report
from RevenueChaser.module_comovement.tests.test_page_pack_379 import _payload


def test_the_page_uses_the_shared_theme():
    html = report.render_comovement_dashboard(_payload())
    assert THEME_CSS in html and "rcThemeApply" in html
    for old in ("#05111F", "#0EA5E9", "#12161e", "#0d1320", "rgba(14,165,233"):
        assert old not in report.CSS


def test_buttons_are_44px_and_the_phone_rule_is_760():
    css = report.CSS
    assert re.search(r"\.seg-btn\{[^}]*min-height:44px", css)
    assert re.search(r"\.linkbtn\{[^}]*min-height:44px", css)
    assert "@media (max-width:760px)" in css and "max-width:520px" not in css
