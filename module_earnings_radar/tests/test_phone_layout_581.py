"""Earnings Radar on a phone (#581): what the page source promises below 640 px.

The 25 Oct 2026 audit called this the worst board on a phone — about 2600 px wide with no ``@media`` rule at
all, so inside the shell's clamped frame (``app/tests/test_phone_shell.py``) the table was simply cut off.
Below 640 px every row is a full-width card and each cell carries its column name.

The browser half (an exact 412 px realme viewport, no sideways scroll, 44 px controls) is
``module_testing/e2e/test_earnings_radar_phone.py``; this half pins the rules a regression would quietly drop.
"""
from __future__ import annotations

import re
from datetime import date

from revenuechaser.module_earnings_radar.models import TradeCard
from revenuechaser.module_earnings_radar.report import CSS, _COLUMNS, _COL_IDS, export_html

PHONE_QUERY = "@media (max-width: 640px)"


def _phone_css() -> str:
    """The body of the phone ``@media`` block."""
    i = CSS.find(PHONE_QUERY)
    assert i >= 0, f"no {PHONE_QUERY} block: the board has no phone layout"
    j = CSS.index("{", i) + 1
    depth, k = 1, j
    while depth:
        depth += {"{": 1, "}": -1}.get(CSS[k], 0)
        k += 1
    return CSS[j:k - 1]


def _card(ticker="AAPL", **overrides) -> TradeCard:
    defaults = {
        "ticker": ticker,
        "name": "Apple Inc.",
        "cluster": "Technology",
        "earnings_date": date(2026, 8, 11),
        "report_time_label": "PM",
        "direction_score": 20.0,
        "confidence_score": 65.0,
        "bias_label": "BULL",
        "expected_move_pct": 5.0,
        "eps_estimate": "1.25",
        "final_action": "OPTIONS_BULL",
        "rule_audit": {"rule2_guidance": {"reasons": [], "available": True}},
    }
    defaults.update(overrides)
    return TradeCard(**defaults)


def test_each_row_becomes_a_card_below_640_px():
    phone = _phone_css()
    assert re.search(r"table\.data-table\{[^}]*display:block", phone), "the table still lays out as a table"
    assert re.search(r"table\.data-table thead\{[^}]*display:none", phone), "the header rows stay"
    assert re.search(r"table\.data-table tbody tr\[data-ticker\]\{[^}]*display:grid", phone), "no card per row"
    assert re.search(r"table\.data-table td\{[^}]*display:block", phone)


def test_the_colgroups_pixel_widths_are_dropped():
    """``_colgroup`` writes the fitted desktop width of all 23 columns (~2600 px in total)."""
    phone = _phone_css()
    assert re.search(r"table\.data-table colgroup,table\.data-table col\{[^}]*display:none", phone)
    assert re.search(r"table\.data-table\{[^}]*table-layout:auto", phone)


def test_the_page_never_scrolls_sideways():
    phone = _phone_css()
    assert re.search(r"\.board\{[^}]*overflow-x:hidden", phone)
    assert re.search(r"\.app\{[^}]*display:block", phone), "the two panes stay side by side"
    for rule in (r"\.gex-track-wrap,\.gex-grid\{[^}]*min-width:0", r"\.name-cell\{[^}]*max-width:none"):
        assert re.search(rule, phone), f"missing: {rule}"


def test_nothing_in_the_phone_block_is_wider_than_a_realme_screen():
    """412 px is avo's phone (``module_testing/e2e/harness/devices.py``)."""
    too_wide = [m for m in re.findall(r"(?:min-)?width:\s*(\d+)px", _phone_css()) if int(m) > 412]
    assert not too_wide, f"a fixed width past the screen: {too_wide}"


def test_a_finger_gets_44_px_targets():
    phone = _phone_css()
    for rule in (r"\.seg button\{[^}]*min-height:44px", r"\.tb-search\{[^}]*min-height:44px",
                 r"\.chip\{[^}]*min-height:44px", r"\.colpick>summary\{[^}]*min-height:44px",
                 r"\.drawer-close\{[^}]*height:44px", r"\.dp\{[^}]*min-height:44px",
                 r"summary\{[^}]*min-height:44px"):
        assert re.search(rule, phone), f"missing: {rule}"


def test_the_methodology_tables_wrap_instead_of_running_off_the_edge():
    """Scoring formulas and Methodology are plain four-column text tables with no colgroup (#581 CI run 1)."""
    phone = _phone_css()
    assert re.search(r"table:not\(\.data-table\)\{[^}]*table-layout:fixed", phone)
    assert re.search(r"table:not\(\.data-table\) td,table:not\(\.data-table\) th\{[^}]*white-space:normal",
                     phone)


def test_the_drawer_covers_the_page_instead_of_taking_480_px_beside_it():
    phone = _phone_css()
    assert re.search(r"\.drawer\{[^}]*position:fixed", phone)
    assert re.search(r"\.drawer\{[^}]*display:none", phone), "a closed drawer must not sit past the right edge"
    assert re.search(r"\.drawer\.open\{[^}]*display:block", phone)
    assert re.search(r"\.drawer-in\{[^}]*width:100%", phone)
    # The board-wide content-fit rule forbids an ``auto`` width in the page (``test_report_table_fills_pane``).
    assert "width:auto" not in phone
    assert re.search(r"\.dcards\{[^}]*grid-template-columns:minmax\(0,1fr\)", phone)
    assert re.search(r"\.decision-split\{[^}]*grid-template-columns:minmax\(0,1fr\)", phone)


def test_the_toolbar_wraps_instead_of_scrolling_sideways():
    phone = _phone_css()
    assert re.search(r"\.toolbar\{[^}]*flex-wrap:wrap", phone)
    assert re.search(r"\.chips\{[^}]*flex-wrap:wrap", phone)
    assert re.search(r"\.tb-kbd\{[^}]*display:none", phone), "the j/k · Enter hint has no phone to be typed on"


def test_nothing_stays_sticky_in_a_card():
    phone = _phone_css()
    assert re.search(r"td\.sticky-tick,table\.data-table td\.sticky-name,"
                     r"table\.data-table td\.sticky-price\{[^}]*position:static", phone)


def test_every_data_cell_carries_its_column_name():
    """A card has no header row, so each value prints its own label (``data-label``)."""
    path = export_html([_card(), _card("MSFT", name="Microsoft Corp")], [], {})
    html = path.read_text(encoding="utf-8")
    labels = dict(re.findall(r'<td class="[^"]*" data-col="([^"]+)" data-group="[^"]*" data-label="([^"]*)"', html))
    assert set(labels) == set(_COL_IDS), f"cells without a label: {sorted(set(_COL_IDS) - set(labels))}"
    assert labels == {cid: label for cid, label, *_ in _COLUMNS}


def test_the_cards_head_prints_no_label_above_the_ticker_name_and_sector():
    phone = _phone_css()
    assert re.search(r'td\[data-col="ticker"\]::before,[^{]*td\[data-col="name"\]::before,\s*'
                     r'table\.data-table td\[data-col="sector"\]::before\{display:none', phone)
    assert re.search(r'td\[data-col="ticker"\]\{[^}]*grid-column:1/-1', phone)
    assert re.search(r'td\[data-label\]::before\{[^}]*content:attr\(data-label\)', phone)
