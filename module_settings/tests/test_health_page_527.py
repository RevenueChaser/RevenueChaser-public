"""#527 step 9 (avo 6 Nov 2026): the Health page and the Catalog get the Data page's principles. What needs avo comes
first and open; what is fine is folded. The Catalog's problem groups lead and are open, a group head counts its
missing needs, the short columns never wrap and Read by wraps. The Data page has one "What am I looking at?", the top
bar (switches, IBKR gateway with its login link) heads both tabs, and the Health tab's order puts the queue, the
backups and the catalog before the reference parts, which are closed."""
from __future__ import annotations

import re

from revenuechaser.module_settings import control_render, needs_tab, report
from revenuechaser.module_settings.tests.test_needs_tab import _model, _summary
from revenuechaser.module_settings.tests.test_report import _panel


def _heads(html: str) -> list[tuple[str, str]]:
    return re.findall(r'<tbody class="cghead" data-file="([^"]+)"(?: data-bad)?><tr><td colspan="7">(.*?)</td></tr></tbody>', html,
                      flags=re.S)


def _state(bad: dict[str, str]):
    return lambda n: {**_summary(n), "state": bad.get(n, "fresh")}


def test_problem_groups_come_first_and_open_and_fresh_groups_stay_closed():
    m = _model()
    files = [f for f in needs_tab.SERVED_FILES if any(r["kind"] == f for r in m["catalog"])]
    last = files[-1]
    victim = next(r["need"] for r in m["catalog"] if r["kind"] == last)
    m = _model(summarize=_state({victim: "missing"}))
    html = needs_tab.render(m)
    heads = _heads(html)
    assert heads[0][0] == last, "the group holding a missing need leads"
    assert 'aria-expanded="true"' in heads[0][1] and "▾" in heads[0][1]
    assert f'<tbody class="cbody" id="cg-{last}">' in html, "its rows show at load"
    for f, head in heads[1:]:
        assert 'aria-expanded="false"' in head, f


def test_a_group_head_counts_its_missing_needs_and_its_problem_rows_lead():
    m = _model()
    rows = [r["need"] for r in m["catalog"] if r["kind"] == "prices"]
    m = _model(summarize=_state({rows[-1]: "missing"}))
    html = needs_tab.render(m)
    head = dict(_heads(html))["prices"]
    assert f"{len(rows)} needs · fresh {len(rows) - 1} · stale 0 · missing 1" in head
    body = html.split('id="cg-prices"', 1)[1].split("</tbody>", 1)[0]
    assert re.findall(r'data-need="([^"]+)"', body)[0] == rows[-1]


def test_the_catalogs_short_columns_never_wrap_and_read_by_wraps():
    css = needs_tab.NEEDS_CSS.split("#527", 1)[-1]
    for label in ("State", "Newest day", "Rows", "Fresh if"):
        assert f'#needs td[data-label="{label}"]' in css, label
    assert "white-space:nowrap" in css
    assert re.search(r'#needs td\[data-label="Read by"\]\{[^}]*min-width:0', css)








