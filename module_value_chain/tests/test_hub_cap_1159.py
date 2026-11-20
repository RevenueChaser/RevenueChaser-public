"""#1159: a hub's board stays readable once the profile edges are served.

Rendered on real data at head `8f96757`, the page opened on AMZN and drew every one of the several hundred
filers that name it: the sankey's labels overlapped into a solid block at every width, and the evidence list
made the page 29,221 px tall at 1187 px and 40,820 px at 411 px. The same render showed two different link
counts side by side -- "18966 Links drawn" and "labels cover 194 of 7795 links" -- which are the served rows and
the distinct pairs, two numbers the word "links" hid.

Both halves are in the page's own JavaScript and its tiles, so these are assertions on the rendered HTML.
"""
from __future__ import annotations

from RevenueChaser.module_value_chain import report


def _payload(**over):
    p = {"as_of": "2026-11-20", "filings": [], "edges": [],
         "precision": {"n": 194, "tp": 166, "fp": 28, "precision": 0.8557, "lower_bound": 0.7993,
                       "passes": True, "status": "pass", "links": 7795, "covered": 194}}
    p.update(over)
    return p


def test_the_chart_and_the_evidence_list_cap_a_hub():
    html = report.render_value_chain_dashboard(_payload())
    # The chart draws the strongest links only, and says so under itself rather than silently dropping any.
    assert "var SANKEY_MAX = 40;" in html
    assert 'id="sankey-note"' in html
    assert "Showing the " in html and "Every one is in the evidence below." in html
    # A hub is nearly all one direction, so a flat cap would draw one colour and could hide the other side of a
    # mixed company: the real render of AMZN drew 40 suppliers and no customer. Each direction gets half the
    # budget and whatever the other leaves, so 200 suppliers and 5 customers still draw all 5.
    assert "function capForChart(links){" in html
    assert "var nSup = Math.min(sup.length, SANKEY_MAX - Math.min(cus.length, half));" in html
    assert "var nCus = Math.min(cus.length, SANKEY_MAX - nSup);" in html
    assert "links = capForChart(links);" in html
    assert "both directions kept" in html
    # The evidence list puts one page in the DOM and keeps the rest behind a button, which is what brought the
    # page height down; the rows are built by the same renderer either way.
    assert "var EVIDENCE_PAGE = 25;" in html
    assert 'Show the other " + rest.length + " links"' in html
    assert "function edgeRows(links){" in html
    assert "el.innerHTML = edgeRows(links.slice(0, EVIDENCE_PAGE));" in html
    # One ranking, read by both halves, so the chart and the list agree on what "strongest" means.
    assert "function rankLinks(links){" in html
    assert "links = rankLinks(links);" in html
    # The button is a 44 px full-width target (phone rule), not a text link.
    assert ".more{display:block;width:100%;min-height:44px" in html


def test_the_two_link_counts_say_what_they_count():
    html = report.render_value_chain_dashboard(_payload())
    # The Precision tile counts distinct pairs and now names them; the banner tile counts served rows and says
    # how many pairs they make, so neither number can be read as the other.
    assert "labels cover 194 of 7,795 distinct pairs" in html
    assert "supplier / customer links served · 7,795 distinct pairs" in html
    assert "of 7795 links" not in html
    # With nothing measured the banner says only what it knows. Asserted here rather than as a test of its own,
    # because it already holds on the merge-base and ``red_on_base.py`` asks every new test to be red there.
    bare = report.render_value_chain_dashboard(_payload(precision=None))
    assert "supplier / customer links served</div>" in bare
    assert "distinct pairs" not in bare
