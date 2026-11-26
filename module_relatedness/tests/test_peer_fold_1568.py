"""#1568: the board opens with the first VISIBLE_PEERS related companies and folds the rest behind a button.

avo, 26 November 2026 16:47 Amsterdam, card option B: "10 göster, gerisi açılır". The fold is display only —
the payload still carries ``config.TOP_PEERS`` peers, which these tests also check, so a later change to the
fold cannot quietly shorten the stored list.
"""
from __future__ import annotations

from revenuechaser.module_relatedness import config
from revenuechaser.module_relatedness.report import render_relatedness_dashboard

PAYLOAD = {
    "as_of": "2026-11-26T04:32:00",
    "n": 2,
    "companies": [{"ticker": "AAPL", "name": "Apple Inc."}, {"ticker": "MSFT", "name": "Microsoft Corp"}],
    "peers": {"AAPL": [{"peer": f"P{i}", "score": 0.6, "percentile": 99} for i in range(config.TOP_PEERS)]},
}


def test_the_fold_size_is_smaller_than_the_stored_peer_count():
    assert 0 < config.VISIBLE_PEERS < config.TOP_PEERS


def test_the_page_carries_the_fold_size_from_config():
    html = render_relatedness_dashboard(PAYLOAD)
    assert f"var VISIBLE = {config.VISIBLE_PEERS};" in html


def test_the_page_folds_the_list_and_offers_one_button_for_the_rest():
    html = render_relatedness_dashboard(PAYLOAD)
    assert "list.slice(0, VISIBLE)" in html
    assert 'class="more" onclick="showAllPeers()"' in html
    assert "Show all ' + list.length +" in html


def test_the_button_is_a_phone_sized_target():
    html = render_relatedness_dashboard(PAYLOAD)
    css = html.split(".more{", 1)[1].split("}", 1)[0]
    assert "min-height:44px" in css and "width:100%" in css


def test_a_new_focal_company_opens_folded_again():
    html = render_relatedness_dashboard(PAYLOAD)
    assert "if(ticker && ticker !== FOCAL) EXPANDED = false;" in html


def test_the_payload_still_carries_every_peer():
    html = render_relatedness_dashboard(PAYLOAD)
    for i in range(config.TOP_PEERS):
        assert f'"peer": "P{i}"' in html or f'"peer":"P{i}"' in html


def test_the_help_text_names_both_numbers():
    html = render_relatedness_dashboard(PAYLOAD)
    assert f"top {config.TOP_PEERS} peers" in html and f"first {config.VISIBLE_PEERS} open with the board" in html
