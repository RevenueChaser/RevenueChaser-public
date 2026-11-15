"""Runs tab: the read-only run log over ``job_runs`` (app/runview.py, /view/runs, /api/runs; #26 PL5-b).

Two writers have filled ``job_runs`` since #282 J4 and #129 A1, and nothing read it. This tab is the reader.
It shows what the row says and nothing more: a run whose writer recorded no trigger stays "not recorded"
rather than being guessed from the lane (the gap is #83), and a row left ``running`` by a skipped end write
(#82) shows as running with its age.
"""
from __future__ import annotations

import logging
import re

import pytest

from RevenueChaser.app import dashboard, logview, runview
from RevenueChaser.core import provenance, rawstore

TEMPLATE = dashboard.Path(dashboard.__file__).resolve().parent.parent / "templates" / "dashboard.html"


@pytest.fixture()
def client():
    dashboard.app.config["TESTING"] = True
    return dashboard.app.test_client()


def _row(run_id, **over):
    row = {"run_id": run_id, "job_id": run_id, "module": "rotation", "lane": "short",
           "trigger": None, "source": None, "pid": 4242, "registry_name": None,
           "params": {}, "queued_at": 1_792_700_000.0, "started_at": 1_792_700_001.0,
           "finished_at": 1_792_700_061.0, "status": "done", "error": None, "message": None,
           "counts": None}
    row.update(over)
    return row




# ── the reader ────────────────────────────────────────────────────────────────





























def test_a_long_filter_is_bounded():
    assert len(runview.clean_query("x" * 5_000)) == runview.MAX_QUERY
    assert runview.clean_query(None) == "" and runview.clean_query(12) == ""


def test_a_silly_limit_is_clamped_not_refused():
    assert runview.clamp_limit("0") == 1
    assert runview.clamp_limit(str(runview.MAX_LIMIT * 10)) == runview.MAX_LIMIT
    assert runview.clamp_limit("abc") == runview.DEFAULT_LIMIT
    assert runview.clamp_limit(None) == runview.DEFAULT_LIMIT


def test_an_empty_table_is_an_empty_page_not_an_error():
    got = runview.read()
    assert got["rows"] == [] and got["total"] == 0


# ── the route ─────────────────────────────────────────────────────────────────



def test_the_api_clamps_the_limit(client):
    data = client.get(f"/api/runs?limit={runview.MAX_LIMIT * 10}").get_json()
    assert data["limit"] == runview.MAX_LIMIT






def test_the_api_takes_no_write(client):
    assert client.post("/api/runs").status_code in (403, 405)


# ── the tab ───────────────────────────────────────────────────────────────────

def test_the_tab_is_out_of_the_menu_and_its_page_still_answers(client):
    """avo, 10 Nov 2026: Logs and Runs left the menu; 11 Nov: so did Activity. /view/runs still answers."""
    keys = [t.get("key") for t in dashboard.TABS]
    assert "runs" not in keys and "activity" not in keys
    html = client.get("/").get_data(as_text=True)
    assert 'data-tab="runs"' not in html and 'data-url="/view/activity"' not in html
    assert client.get("/view/runs").status_code == 200


def test_the_tab_is_a_read_only_view_with_no_fetch_or_refresh():
    """Not a board backed by its own downloaded data: no Fetch, no Refresh, no run route, no data date."""
    assert "runs" not in dashboard._MODEL_ONLY_RENDERERS
    assert "runs" not in dashboard._STORE_REFRESHABLE
    assert dashboard._module_file("runs") is None
    assert "runs" in provenance.RESOLVERS and provenance.RESOLVERS["runs"] is None
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "'runs'" not in html.split("var STORE_BACKED")[1].split("];")[0]
    assert "runs:" not in html.split("var RUN_URLS")[1].split("};")[0]
    show_tab = html.split("function showTab")[1].split("checkDataAsOf(key)")[0]
    refresh_line = next(ln for ln in show_tab.splitlines() if "rfBtn.style.display" in ln)
    assert "key==='runs'" in refresh_line, "the Refresh button must be hidden on the Runs tab"
    fetch_line = next(ln for ln in show_tab.splitlines() if "ftBtn.style.display" in ln)
    assert "runs" not in fetch_line
    assert "'runs': true" in html.split("var FILL_WIDTH")[1].split("};")[0], "the page fills the pane"


def test_the_page_renders_its_controls(client):
    resp = client.get("/view/runs")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert len(re.findall(r"<h1\b", html)) == 1
    for label in ("Problems only", "Pause", "Job", "Status", "Started", "Took"):
        assert label in html
    low = html.lower()
    for word in ("clear", "delete", "run now", "retry"):
        assert f">{word}" not in low, f"no {word} button: the tab is read-only"




def test_the_page_puts_every_stored_value_in_as_text(client):
    """A job message, an error and a params blob are stored text. The hostile fixture proves the server's
    escaping (core/tests/test_board_html_guard.py); this proves the page's own DOM writes, which that guard
    cannot see because they happen in the browser."""
    html = client.get("/view/runs").get_data(as_text=True)
    for sink in (".innerHTML", ".outerHTML", "insertAdjacentHTML", "document.write"):
        assert sink not in html, f"{sink} on the run log: values go in through textContent"


def test_the_page_says_why_a_trigger_can_be_missing(client):
    """An honest page: a dash is an older row; a lost run is named as such."""
    html = client.get("/view/runs").get_data(as_text=True)
    assert "an older row that recorded none" in html
    assert "<em>lost</em>" in html


def test_every_control_is_labelled(client):
    html = client.get("/view/runs").get_data(as_text=True)
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    inputs = re.findall(r"<input\b[^>]*>", html)
    assert inputs, "the page has controls to label"
    labels = re.findall(r'<label\b[^>]*\bfor="([^"]+)"', html)
    assert len(labels) >= len(inputs)
    for target in labels:
        assert target in ids, f"label points at a missing id: {target}"


def _request(path):
    return logging.LogRecord("werkzeug", logging.INFO, __file__, 1, '%s - - [x] "%s" %s -',
                             ("127.0.0.1", f"GET {path} HTTP/1.1", "200"), None)


def test_the_tabs_own_polling_stays_out_of_the_log_it_would_fill():
    """The Runs tab polls every few seconds; werkzeug's lines for it must not reach the Logs tab."""
    # The installer is called here rather than left to the import side effect, so the test says what it
    # needs. The path itself is NOT registered here: that is app/dashboard.py's wiring, under test.
    logview.quiet_polling()
    assert runview.POLL_PATH in logview.POLL_PATHS, "app/dashboard.py must register the Runs tab's path"
    werkzeug = logging.getLogger("werkzeug")
    assert not werkzeug.filter(_request("/api/runs"))
    assert werkzeug.filter(_request("/view/runs"))
    assert not werkzeug.filter(_request("/api/logs?src=server")), "the Logs tab's own filter still holds"
    assert werkzeug.filter(_request("/api/jobs"))


# ── the overlay (the other half of PL5-b) ─────────────────────────────────────

def test_the_overlay_names_the_running_job_instead_of_a_fixed_sentence():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="overlay-msg"' in html, "the overlay message needs an id to be written into"
    assert "function overlayText" in html, "one place decides what the overlay says"
    body = html.split("function overlayText")[1].split("\n}")[0]
    assert "phase" in body, "the phase /api/jobs already serves is rendered"
    assert "elapsed" in body or "started_at" in body, "a long run says how long it has been going"


def test_the_page_offers_the_server_side_page_sizes_beside_pause(client):
    """#131 item 2: the newest DEFAULT_LIMIT was all the page could reach; the control offers both sizes the
    server accepts, and takes them from runview so the page and the route cannot disagree."""
    html = client.get("/view/runs").get_data(as_text=True)
    m = re.search(r'<select\b[^>]*\bid="runs-limit"[^>]*>(.*?)</select>', html, re.S)
    assert m, "no page-size control"
    values = re.findall(r'<option\b[^>]*\bvalue="(\d+)"', m.group(1))
    assert values == [str(runview.DEFAULT_LIMIT), str(runview.MAX_LIMIT)]
    assert re.search(r'<option\b[^>]*value="%d"[^>]*\bselected' % runview.DEFAULT_LIMIT, m.group(1))
    assert 'for="runs-limit"' in html, "the control has a label"
    assert html.index('id="runs-limit"') < html.index('id="runs-pause"'), "it sits beside Pause"
    script = html.split("<script>")[-1]
    assert 'limit.addEventListener("change"' in script, "a new size is read at once, not at the next poll"


def test_the_page_size_control_is_not_restored_by_the_browser(client):
    """A reload must show the newest 200 the URL reads, not a size Firefox restored into the select."""
    html = client.get("/view/runs").get_data(as_text=True)
    select = re.search(r'<select\b[^>]*\bid="runs-limit"[^>]*>', html).group(0)
    assert 'autocomplete="off"' in select


def test_the_empty_row_spans_the_header_it_sits_under():
    """The column count comes from the one Jinja list the header is built from, not a literal."""
    from pathlib import Path
    source = (Path(dashboard.__file__).resolve().parent.parent / "templates" / "runs.html.j2").read_text(
        encoding="utf-8")
    assert not re.search(r"colSpan\s*=\s*\d", source), "a hard-coded column count"
