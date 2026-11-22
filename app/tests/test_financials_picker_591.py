"""The shell reads the Financials ticker from the board, not from its own header box (#591).

Financials kept a ``#quick-ticker`` box in the dashboard header while every other per-ticker board had the
shared kit's combobox inside its own page. The board now carries the picker, so Fetch and Refresh read it from
the frame, exactly as Implied Probability already does; the header box stays only as the fallback for the empty
state, before the first Fetch has written a board.
"""
from __future__ import annotations

import re

import pytest

from revenuechaser.app import dashboard


@pytest.fixture(scope="module")
def index_html() -> str:
    return dashboard.app.test_client().get("/").get_data(as_text=True)


def _fn_body(html: str, name: str) -> str:
    start = html.index(f"function {name}(")
    rest = html[start + 1:]
    end = rest.find("\nfunction ")
    body = rest[:end if end != -1 else len(rest)]
    return "\n".join(re.sub(r"//.*$", "", line) for line in body.splitlines())


def test_the_frame_reader_is_not_oipds_alone(index_html):
    assert "function comboTickerFromFrame(tab)" in index_html
    assert "function oipdTickerFromFrame(){ return comboTickerFromFrame('module_oipd'); }" in index_html


def test_refresh_reads_the_boards_picker_first(index_html):
    fin = _fn_body(index_html, "refreshTab")
    fin = fin[fin.index("module_financials"):]
    assert "comboTickerFromFrame('module_financials')" in fin
    assert fin.index("comboTickerFromFrame") < fin.index("quick-ticker"), "the box is the fallback, not the source"


def test_fetch_reads_the_boards_picker_first(index_html):
    handler = index_html[index_html.index("document.getElementById('btn-fetch').addEventListener"):]
    handler = handler[:handler.index("fetchTab(url, body);")]
    assert "comboTickerFromFrame('module_financials')" in handler
    assert handler.index("comboTickerFromFrame") < handler.index("quick-ticker")


def test_the_header_box_is_only_the_empty_states_fallback(index_html):
    """It used to be shown for the whole board; now it is shown only while the frame carries no picker."""
    assert "function syncQuickCtl(" in index_html
    assert "_frameHasCombo('module_financials')" in index_html
    assert "(key==='module_financials') ? 'flex' : 'none'" not in index_html
