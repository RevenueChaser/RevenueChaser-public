"""Settings / Data health HTML renderer: table, Fetch buttons, help, empty state."""
from __future__ import annotations

import pytest

from RevenueChaser.module_settings import report






















def _run_verdicts(js: str, cases: list) -> list:
    """Extract ``settingsJobVerdict`` from ``js`` and run it under node."""
    import json
    import re
    import shutil
    import subprocess
    import pytest
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    m = re.search(r"function settingsJobVerdict\(.*?\n}\n", js, re.S)
    assert m, "settingsJobVerdict not found in the Settings JS"
    script = m.group(0) + "\nvar cases = %s;\nconsole.log(JSON.stringify(cases.map(settingsJobVerdict)));\n" % json.dumps(cases)
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


class TestJobVerdict:
    def test_every_status_maps_truthfully(self):
        cases = [
            {"ok": True, "job": {"status": "queued"}},
            {"ok": True, "job": {"status": "running"}},
            {"ok": True, "job": {"status": "done", "message": "3 caps filled"}},
            {"ok": True, "job": {"status": "error", "error": "boom"}},
            {"ok": True, "job": {"status": "cancelled"}},
            {"ok": True, "job": {"status": "weird"}},
            {"ok": False, "error": "unknown job"},
            {},
        ]
        got = _run_verdicts(report.JS, cases)
        states = [g["state"] for g in got]
        assert states == ["poll", "poll", "done", "error", "error", "error",
                          "error", "error"], got
        assert got[0]["text"] == "Queued…"
        assert got[1]["text"] == "Running…"
        assert got[2]["text"] == "3 caps filled"
        assert got[3]["text"] == "boom"
        assert got[4]["text"] == "Cancelled"
        assert got[5]["text"] == "Unknown job status: weird"
        assert "Job not found" in got[6]["text"]
        assert "Job not found" in got[7]["text"]

    def test_done_and_error_fall_back_to_defaults(self):
        got = _run_verdicts(report.JS, [
            {"ok": True, "job": {"status": "done"}},
            {"ok": True, "job": {"status": "error"}},
        ])
        assert got == [{"state": "done", "text": "Done"},
                       {"state": "error", "text": "Error"}]

    def test_poller_uses_the_verdict(self):
        assert "settingsJobVerdict(d)" in report.JS


# ── Board inputs section + visible errors (slice 2) ──────────────────────────














# ── G6a (#124): the board inputs in the Data Flow artifact's language ────────
# One line per store table the board reads: provider → dataset → store file, with the dataset's
# coverage beside it. The facts come from the registry and from the rows ``collect()`` already
# built, so rendering asks the store nothing.




def test_every_provider_the_registry_can_name_is_written_in_words():
    """The copy rule: a source code such as ``finra/cftc`` never reaches the page."""
    from RevenueChaser.core import datasets

    for source in datasets.Source:
        words = report._provider_name(source)
        assert words and words != source.value, (source, words)
        assert words == report.source_words(source.value), (
            "the board rows, the dataset table and the diagram read one provider-name list")




















# ── editable Co-movement inputs (#40 Part B) ─────────────────────────────────
import re  # noqa: E402


def _field(key, label, value, default, kind="int", lo=None, hi=None, rng="",
           overridden=False, choices=None):
    return {"key": key, "label": label, "value": value, "default": default,
            "kind": kind, "lo": lo, "hi": hi, "range": rng,
            "overridden": overridden, "choices": choices}


def _settings_block(custom=False, **over):
    s = {
        "board": "module_comovement", "custom": custom,
        "inputs": [
            _field("WINDOW", "Default window (sessions)", 252, 252,
                   choices=[[21, "1m (21)"], [126, "6m (126)"], [252, "1y (252)"]],
                   rng="1m, 2m, 6m, 9m, 1y, 1.5y"),
            _field("MIN_OBS", "Minimum observations", 126, 126, lo=60,
                   rng="60–WINDOW"),
            _field("OOS_HOLDOUT", "Out-of-sample holdout (sessions)", 63, 63,
                   lo=42, hi=126, rng="42–126"),
        ],
        "fine": [
            _field("WINSOR_K", "Winsorize at (sigma)", 5.0, 5.0, kind="float",
                   lo=4.0, hi=8.0, rng="4–8"),
            _field("MIN_PERIODS", "Pairwise minimum overlap", 60, 60, lo=20,
                   rng="20–MIN_OBS"),
            _field("BENCH_STALE_SESSIONS", "Benchmark lag (sessions)", 2, 2,
                   lo=0, hi=5, rng="0–5"),
        ],
        "derived": {"key": "OOS_MIN_OBS",
                    "label": "Held-out observations needed (derived)", "value": 40},
    }
    s.update(over)
    return s


_NODE_STUB = r"""
var _els = {}, FETCHES = [], RESP = [];
function mk(id, extra){
  var a = {}, o = {id: id, textContent: "", innerHTML: "", disabled: false, value: "",
    open: false, hidden: false, style: {}, classList: {add(){}, remove(){}},
    setAttribute(k, v){ a[k] = String(v); }, getAttribute(k){ return k in a ? a[k] : null; },
    closest(){ return o._details || null; }, addEventListener(){}};
  return Object.assign(o, extra || {});
}
globalThis.document = {
  getElementById(id){ return _els[id] || (_els[id] = mk(id)); },
  querySelectorAll(sel){ return sel.indexOf("[data-setting]") >= 0 ? (globalThis.INPUTS || []) : []; },
  querySelector(){ return null; }
};
globalThis.location = {search: "", origin: "http://x"};
globalThis.parent = {postMessage(){}};
globalThis.fetch = function(url, opts){
  FETCHES.push({url: url, body: opts && opts.body ? JSON.parse(opts.body) : null});
  var r = RESP.shift() || {status: 200, body: {ok: true, job: {status: "running"}}};
  return Promise.resolve({status: r.status, ok: r.status < 400,
                          json(){ return Promise.resolve(r.body); }});
};
function input(key, orig, value){
  var a = {"data-setting": key, "data-orig": String(orig)};
  return {value: String(value), getAttribute(k){ return a[k] == null ? null : a[k]; }};
}
function saveBtn(){
  var b = mk("b"); _els["msg-set-module_comovement"] = mk("m");
  b.getAttribute = function(k){ return k === "data-board" ? "module_comovement" : null; };
  return b;
}
"""


def _run_settings_js(driver: str) -> dict:
    """Run the Settings board's own JS under node with a small DOM/fetch stub."""
    import json
    import shutil
    import subprocess
    import pytest
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    js = report.JS.replace("document.querySelectorAll('.fetch-btn').forEach", "[].forEach")
    js = js.replace("document.querySelectorAll('.set-save').forEach", "[].forEach")
    js = js.replace("document.querySelectorAll('.set-reset').forEach", "[].forEach")
    script = _NODE_STUB + js + "\n" + driver
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


class TestSaveHandler:


    def test_a_finished_job_reloads_with_refresh(self):
        got = _run_settings_js(r"""
globalThis.INPUTS = [input("MIN_OBS", 126, 200)];
RESP.push({status: 202, body: {ok: true, job_id: "J2", values: {}}});
RESP.push({status: 200, body: {ok: true, job: {status: "done", message: "ok"}}});
settingsSave(saveBtn());
setTimeout(function(){ console.log(JSON.stringify({search: location.search})); process.exit(0); }, 60);
""")
        assert got["search"] == "?refresh=1"

    def test_nothing_changed_sends_nothing(self):
        got = _run_settings_js(r"""
globalThis.INPUTS = [input("MIN_OBS", 126, 126)];
settingsSave(saveBtn());
setTimeout(function(){
  console.log(JSON.stringify({n: FETCHES.length,
    msg: _els["msg-set-module_comovement"].textContent}));
  process.exit(0); }, 20);
""")
        assert got["n"] == 0 and "No changes" in got["msg"]

    def test_reset_posts_reset_true_and_polls(self):
        got = _run_settings_js(r"""
RESP.push({status: 202, body: {ok: true, job_id: "J3", values: {}}});
settingsReset(saveBtn());
setTimeout(function(){ console.log(JSON.stringify({f: FETCHES})); process.exit(0); }, 40);
""")
        assert got["f"][0]["body"] == {"reset": True}
        assert got["f"][1]["url"] == "/api/job/J3"

    def test_one_shared_verdict_function(self):
        from RevenueChaser.core import reporting_common as rc
        assert "function settingsJobVerdict(" in rc.JOB_JS
        assert "function settingsJobVerdict(" in report.JS
        assert report.JS.count("function settingsJobVerdict(") == 1


# ── funnel note + type rows on the Board inputs card (#87) ───────────────────








def test_the_note_row_has_its_own_style():
    assert ".frow2.note" in report.CSS


# ── Identity health card (issue #89) ─────────────────────────────────────────
IDENTITY_IDS = ("identity-health", "identity-run", "identity-spdr", "identity-types",
                "identity-sources", "identity-conflicts", "identity-stale")




def _src(status="ok", rows=0, fetched=0, error=None, selected=True):
    return {"status": status, "selected": selected, "rows": rows, "fetched": fetched, "error": error}


def _identity(**over):
    ident = {
        "last_run": {
            "run_id": "r2", "status": "partial", "started_at": "2026-09-30T00:00:00Z",
            "finished_at": "2026-09-30T00:06:00Z",
            "sources": {"sec_exchange": _src(rows=10300), "nasdaq": _src("error", error="HTTP 503 <b>down</b>"),
                        "openfigi": _src(rows=120, fetched=120), "fdic": _src("skipped", selected=False)},
            "counts": {"tickers": 7366, "conflicts": 266, "spdr_checked": 480, "spdr_agree": 478}},
        "floor": 300_000_000.0,
        "type_mix": [{"type": "common", "all": 5200, "floor": 2900, "excluded": False},
                     {"type": "etp", "all": 213, "floor": 40, "excluded": True},
                     {"type": "unknown", "all": 3, "floor": 0, "excluded": False}],
        "source_mix": [{"bucket": "official", "all": 1501, "floor": 1501},
                       {"bucket": "provider", "all": 5100, "floor": 1200},
                       {"bucket": "SIC", "all": 325, "floor": 20},
                       {"bucket": "type rule", "all": 400, "floor": 60},
                       {"bucket": "unclassified", "all": 64, "floor": 12}],
        "conflicts": {
            "as_of": "2026-09-30T00:00:00Z",
            "by_kind": [{"kind": "sector", "count": 200}, {"kind": "spdr", "count": 3}],
            "top": [{"ticker": "AAPL", "kind": "spdr", "field": "sector", "side_a": "Technology",
                     "side_b": "Communication Services", "note": "SPDR XLC holdings",
                     "last_seen": "2026-09-30T00:00:00Z", "market_cap": 3.0e12},
                    {"ticker": "*", "kind": "source", "field": "uw_snapshot", "side_a": "previous snapshot",
                     "side_b": "new snapshot (1500 rows)", "note": "gated", "last_seen": "2026-09-30T00:00:00Z",
                     "market_cap": None}],
            "older": {"count": 12, "since": "2026-09-20T00:00:00Z"}},
        "stale": [{"source": "sec_exchange", "newest": "2026-09-30T00:00:00Z", "rows": 7000, "past_window": None,
                   "window": "every run"},
                  {"source": "sec_submissions", "newest": "2026-09-25T00:00:00Z", "rows": 6900, "past_window": 17,
                   "window": "30 days"},
                  {"source": "fdic", "newest": None, "rows": 0, "past_window": 0, "window": "90 days"}],
        "spdr": {"state": "ok", "checked": 480, "agree": 478, "date": "2026-09-30T00:00:00Z"},
    }
    ident.update(over)
    return ident






































# --- Automations panel (#130) ------------------------------------------------------

def _autos():
    from RevenueChaser.core import automations
    return automations.static_rows()








def test_an_empty_automations_list_says_so():
    html = _render_rows([])
    assert "No scheduled tasks are registered." in html
    assert "<details" not in html


def test_the_panel_uses_rcesc_and_never_the_drill_escaper():
    start = report.AUTOMATIONS_JS
    assert "rcEsc(" in start and "tcEsc" not in start
    assert "innerHTML" in start


def test_confirm_names_the_task_for_install_remove_and_run():
    js = report.AUTOMATIONS_JS
    for verb in ("install", "remove", "run"):
        assert f"'{verb}'" in js
    assert "confirm(" in js


def _render_rows(rows: list, available: bool = True) -> str:
    import json
    import shutil
    import subprocess
    import pytest
    from RevenueChaser.core import html_safe
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    script = (html_safe.ESC_JS + report.AUTOMATIONS_JS +
              "\nconsole.log(JSON.stringify(autoTableHtml(%s, %s)));\n"
              % (json.dumps(rows), json.dumps(available)))
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_renderer_escapes_every_field_of_a_hostile_row():
    bad = "<img src=x onerror=__x(1)>"
    row = {k: bad for k in ("name", "label", "schedule", "command", "settings", "log_path",
                            "description", "state", "result_text", "result_kind",
                            "last_run", "next_run", "last_success_age")}
    row.update(tables_written=[bad], log_tail=[bad], missed_runs=bad)
    html = _render_rows([row])
    assert "<img" not in html and "&lt;img" in html


def test_renderer_buttons_follow_the_state():
    rows = [dict(_autos()[0], state=s) for s in
            ("not_installed", "enabled", "disabled", "running", "unavailable", "weird")]
    out = [_render_rows([r]) for r in rows]
    acts = lambda h: sorted(set(__import__("re").findall(r'data-act="(\w+)"', h)))  # noqa: E731
    assert acts(out[0]) == ["install"]
    assert acts(out[1]) == ["disable", "remove", "run"]
    assert acts(out[2]) == ["enable", "remove"]
    assert acts(out[3]) == [] and acts(out[4]) == [] and acts(out[5]) == []


def test_renderer_shows_neutral_not_red_for_a_task_that_never_ran():
    row = dict(_autos()[0], state="enabled", result_kind="neutral", result_text="not run yet")
    html = _render_rows([row])
    assert "not run yet" in html and "st-bad" not in html
    red = _render_rows([dict(row, result_kind="red", result_text="failed (0x1)")])
    assert "st-bad" in red


def test_rows_without_live_state_show_checking():
    assert "checking" in _render_rows(_autos()).lower()



def test_renderer_escapes_a_hostile_name_inside_data_name():
    bad = 'x" onmouseover="__x(1)" y="<img src=x onerror=__x(2)>'
    html = _render_rows([dict(_autos()[0], name=bad, state="enabled")])
    assert 'data-name="x&quot; onmouseover=&quot;__x(1)&quot;' in html
    assert "<img" not in html


def test_error_state_is_red_and_offers_no_button():
    row = dict(_autos()[0], state="error", result_kind="red",
               result_text="unreadable scheduler answer")
    html = _render_rows([row])
    assert "st-bad" in html and "Scheduler error" in html
    assert "data-act" not in html


# --- G10 (#124): one line per automation, the rest behind a click -------------------

def _one_line(html: str) -> str:
    """The closed line of the first automation: the whole ``<summary>`` element."""
    start = html.index("<summary>")
    return html[start:html.index("</summary>", start) + len("</summary>")]


def _behind_the_click(html: str) -> str:
    """Everything after the first automation's closed line: what opening it shows."""
    return html[html.index("</summary>") + len("</summary>"):]


def _live_row(**fields) -> dict:
    """The first registry row as the poll returns it: installed, last run ok, next run known."""
    row = dict(_autos()[0], state="enabled", result_kind="ok", result_text="ok",
               last_run="2026-10-23T04:00:05", next_run="2026-10-24T04:00:00",
               missed_runs=0, last_success_age="8 h ago", log_tail=[])
    row.update(fields)
    return row


def test_the_automation_line_carries_its_name_schedule_state_result_and_next_run():
    line = _one_line(_render_rows([_live_row()]))
    first = _autos()[0]
    assert first["label"] in line and first["name"] in line
    assert first["schedule"] in line
    assert "Enabled" in line
    assert "last result: ok" in line
    assert "next run: 2026-10-24 04:00" in line


def test_a_task_that_is_not_installed_shows_its_state_and_no_dash_result():
    row = dict(_autos()[0], state="not_installed", result_kind="none", result_text="—",
               last_run=None, next_run=None, missed_runs=0, last_success_age="never")
    line = _one_line(_render_rows([row]))
    assert "Not installed" in line
    assert "last result" not in line and "next run" not in line


def test_the_automation_line_leaves_the_long_text_behind_the_click():
    auto = _autos()[0]
    line = _one_line(_render_rows([_live_row()]))
    assert auto["description"][:60] not in line
    assert auto["command"] not in line
    assert auto["settings"] not in line
    assert auto["log_path"] not in line




def test_the_expanded_part_keeps_the_description_command_and_run_conditions_word_for_word():
    auto = _autos()[0]
    opened = _behind_the_click(_render_rows([_live_row()]))
    esc_js = lambda t: str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")  # noqa: E731
    assert esc_js(auto["description"]) in opened
    assert esc_js(auto["command"]) in opened
    assert esc_js(auto["settings"]) in opened
    assert esc_js(auto["schedule"]) in opened
    assert "What it does" in opened and "Command" in opened and "Run conditions" in opened


def test_every_automation_is_a_closed_details_row_with_its_own_id():
    html = _render_rows(_autos())
    for auto in _autos():
        assert f'<details class="auto-item" id="auto-{auto["name"]}">' in html
    assert html.count("<details") == html.count("</details>") == len(_autos())


def test_the_line_opens_from_the_keyboard_without_a_click_handler():
    line = _one_line(_render_rows([_live_row()]))
    assert line.startswith("<summary>") and "onclick" not in line and "onkeydown" not in line


def test_the_buttons_are_behind_the_click():
    html = _render_rows([_live_row()])
    assert "data-act" not in _one_line(html)
    assert 'data-act="run"' in _behind_the_click(html)




def test_the_automation_line_escapes_hostile_schedule_result_and_next_run():
    bad = "<img src=x onerror=__x(1)>"
    line = _one_line(_render_rows([_live_row(schedule=bad, result_text=bad, next_run=bad)]))
    assert "<img" not in line and line.count("&lt;img") == 3


def _auto_poll(open_ids: list, focused_id: str | None) -> dict:
    """``autoRender`` against a fake DOM: which rows it left open, and whether it put focus back."""
    import json
    import shutil
    import subprocess
    import pytest
    from RevenueChaser.core import html_safe
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    script = (html_safe.ESC_JS + report.AUTOMATIONS_JS
              + "\nvar openIds = " + json.dumps(open_ids) + ";"
              + "\nvar focusedId = " + json.dumps(focused_id) + ";"
              + "\nvar focused = false;"
              + "\nvar head = {focus: function(){ focused = true; }};"
              + "\nvar made = {};"
              + "\nvar body = {innerHTML: '', querySelectorAll: function(){"
              + " return openIds.map(function(id){ return {id: id}; }); }};"
              + "\nglobalThis.document = {"
              + " activeElement: focusedId ? {closest: function(){ return {id: focusedId}; }} : null,"
              + " getElementById: function(id){"
              + " if(id === 'auto-body') return body;"
              + " if(!made[id]) made[id] = {id: id, open: false,"
              + " querySelector: function(){ return head; }};"
              + " return made[id]; }};"
              + "\nautoRender(" + json.dumps(_autos()) + ", true);"
              + "\nconsole.log(JSON.stringify({rendered: body.innerHTML.length, focused: focused,"
              + " open: openIds.map(function(id){ return made[id] ? made[id].open : null; })}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])






def _drill_rows(detail: dict) -> str:
    """``drillFill(payload)`` run in node: the helpers of ``DRILL_JS`` without the DOM wiring at its end."""
    import json
    import shutil
    import subprocess
    import pytest
    from RevenueChaser.core import html_safe
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    helpers = report.DRILL_JS[:report.DRILL_JS.index("function onDrillPick")]
    script = (html_safe.ESC_JS + helpers +
              "\nconsole.log(JSON.stringify(drillFill(%s)));\n" % json.dumps(detail))
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_lookup_shows_both_ends_of_each_range():
    """avo, 11 Nov 2026: "ne zamandan kaldigini" — the first day, not only the newest."""
    html = _drill_rows({"ticker": "MU", "name": "Micron", "files": [
        {"kind": "prices", "name": "prices.duckdb", "title": "Prices and shares", "looked_at": 4,
         "tables": [{"table": "price_bar_daily", "rows": 2, "first": "2021-01-04", "last": "2026-11-10"}]}]})
    assert '<span class="dlbl">price_bar_daily</span>' in html
    assert "2 rows · 2021-01-04 → 2026-11-10" in html
    assert "Prices and shares" in html, "the group is headed by what the file is for"


def test_a_table_with_no_date_shows_its_row_count_alone():
    html = _drill_rows({"ticker": "MU", "files": [
        {"kind": "ownership", "name": "ownership.duckdb", "title": "Who owns it", "looked_at": 2,
         "tables": [{"table": "ibkr_shortable", "rows": 1, "first": None, "last": None}]}]})
    assert "1 row · no date kept" in html


def test_a_file_that_holds_nothing_for_the_name_says_how_many_tables_were_asked():
    """#715, compact: the files holding nothing share one short group instead of a group each."""
    html = _drill_rows({"ticker": "MU", "files": [
        {"kind": "options", "name": "options.duckdb", "title": "Options", "looked_at": 7, "tables": []}]})
    assert 'id="drill-empty"' in html and "Options" in html
    assert "nothing stored · 7 tables asked" in html


def test_a_missing_file_is_a_line_not_an_empty_group():
    html = _drill_rows({"ticker": "MU", "files": [
        {"kind": "options", "name": "options.duckdb", "title": "Options", "looked_at": 0, "tables": [],
         "error": "no options.duckdb yet"}]})
    assert "no options.duckdb yet" in html


def test_a_table_that_could_not_be_read_says_so_by_name():
    html = _drill_rows({"ticker": "MU", "files": [
        {"kind": "prices", "name": "prices.duckdb", "title": "Prices", "looked_at": 1,
         "tables": [{"table": "price_bar_daily", "rows": None, "error": "IOError: locked"}]}]})
    assert "could not read — IOError: locked" in html


def test_the_lookup_shows_the_identifiers_on_one_line_and_skips_the_empty_ones():
    """avo, 11 Nov 2026 ("daha compact"): one wrapped line of chips, and no row for a field we do not have."""
    html = _drill_rows({"ticker": "MU", "cik": "0000723125", "figi": "BBG000BLNNH6",
                        "security_id": "sec:7", "cusip": None, "isin": None, "files": []})
    assert '<div class="dident">' in html
    assert '<span class="dlbl">CIK</span> 0000723125' in html
    assert '<span class="dlbl">FIGI</span> BBG000BLNNH6' in html
    assert '<span class="dlbl">id</span> sec:7' in html
    assert "CUSIP" not in html and "ISIN" not in html, "a field with no value takes no room"
    rich = _drill_rows({"name": "Micron", "sector": "Technology", "industry": "Semiconductors", "files": []})
    assert "Technology" in rich and "Semiconductors" in rich and "Micron" in rich


def test_the_lookup_escapes_a_hostile_identifier_and_table_name():
    bad = "<img src=x onerror=__x(1)>"
    html = _drill_rows({"ticker": "MU", "cik": bad, "figi": bad, "cusip": bad, "isin": bad, "files": [
        {"kind": "prices", "name": bad, "title": bad, "looked_at": 1,
         "tables": [{"table": bad, "rows": 1, "first": None, "last": None}]}]})
    assert "<img" not in html and html.count("&lt;img") >= 5


def test_the_lookup_errors_are_listed_once_and_only_when_there_are_any():
    assert 'id="drill-errors"' not in _drill_rows({"ticker": "MU", "files": [], "errors": []})
    html = _drill_rows({"ticker": "MU", "files": [], "errors": ["options: RuntimeError: disk gone"]})
    assert 'id="drill-errors"' in html and "options: RuntimeError: disk gone" in html


def test_panel_posts_send_the_panel_header():
    assert "'X-RC-Panel': 'automations'" in report.AUTOMATIONS_JS




# ── S5 of the Data Health plan (#124): Source / Coverage / Fresh and a detail row ────────────


def _thead_cells(html: str) -> list[str]:
    """The table's header cells as plain text (a header may hold a button, e.g. Source)."""
    import re
    # The inventory's own table, not the control board's tables above it.
    if 'table class="inv"' in html:
        html = html[html.index('table class="inv"'):]
    thead = re.search(r"<thead><tr>(.*?)</tr></thead>", html, re.S).group(1)
    return [h.split("<")[0].strip()
            for h in re.findall(r"<th[^>]*>(.*?)</th>", thead, re.S)]


def _main_row(html: str, key: str) -> str:
    start = html.index(f'id="row-{key}"')
    return html[start:html.index("</tr>", start)]


def _detail_row(html: str, key: str) -> str:
    start = html.index(f'id="det-{key}"')
    return html[start:html.index("</tr>", start)]


def _cells(row: str) -> list[str]:
    import re
    return [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]


















def test_the_detail_toggle_and_the_grouping_run_under_node(tmp_path):
    """The two handlers: a detail row opens and closes from its button, and grouping keeps a
    detail row with its dataset row and puts the worst-coverage order back."""
    import json
    import shutil
    import subprocess
    import pytest
    from RevenueChaser.core.tests.board_js import function_source
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    js = (function_source(report.JS, "settingsDetail")
          + function_source(report.JS, "settingsRowPairs")
          + function_source(report.JS, "settingsGroupRows")
          + r"""
var els = {det: {hidden: true}};
globalThis.document = {getElementById: function(id){ return els[id] || null; }};
function button(){
  var a = {"aria-controls": "det", "aria-expanded": "false"};
  return {getAttribute: function(k){ return a[k] == null ? null : a[k]; },
          setAttribute: function(k, v){ a[k] = String(v); },
          state: function(){ return a["aria-expanded"]; }};
}
var b = button();
settingsDetail(b);
var opened = {expanded: b.state(), hidden: els.det.hidden};
settingsDetail(b);
var closed = {expanded: b.state(), hidden: els.det.hidden};
function tr(kind, source, order){
  return {className: kind, attrs: {"data-source": source, "data-order": String(order)},
          getAttribute: function(k){ return this.attrs[k] == null ? null : this.attrs[k]; }};
}
function body(children){
  return {children: children, out: [],
          appendChild: function(el){ this.out.push(el.attrs["data-order"] +
                                                    (el.className === "detail" ? "d" : "r")); }};
}
var tbody = body([tr("row", "uw", 0), tr("detail", "", 0), tr("row", "sec", 1), tr("detail", "", 1),
                  tr("row", "derived", 2), tr("detail", "", 2)]);
settingsGroupRows(tbody, true);
var grouped = tbody.out.slice();
tbody.out = [];
settingsGroupRows(tbody, false);
console.log(JSON.stringify({opened: opened, closed: closed,
                            grouped: grouped, restored: tbody.out}));
""")
    path = tmp_path / "settings_handlers.js"
    path.write_text(js, encoding="utf-8")
    out = subprocess.run(["node", str(path)], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr[-2000:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["opened"] == {"expanded": "true", "hidden": False}
    assert got["closed"] == {"expanded": "false", "hidden": True}
    assert got["grouped"] == ["2r", "2d", "1r", "1d", "0r", "0d"], "source order, detail with its row"
    assert got["restored"] == ["0r", "0d", "1r", "1d", "2r", "2d"], "back to worst coverage first"


# ── G2 of the GUI redesign (#124): coverage bar, store chip, legend ──────────────────────────




















def test_a_legend_under_the_table_explains_each_pill_once():
    html = report._table([{"key": "quotes", "label": "Quotes", "tables": [], "note": ""}])
    assert html.index("</tbody></table>") < html.index('id="db-legend"'), "under the table"
    legend = html[html.index('id="db-legend"'):]
    assert "Store file" in legend
    for db in ("raw", "edgar", "history", "prices"):
        assert f'class="db db-{db}"' in legend, db


# ── S5b / G3 of the GUI brief (#124): the Fresh cell's named states ─────────────────────────
# The cells used to print a bare dash for four different situations. Each state now carries its
# own words, and a failed query is red and says it is not an empty dataset.



def _fresh_text(html: str, key: str = "quotes") -> str:
    """The Fresh cell's text (the fourth cell) of one row."""
    return _cells(_main_row(html, key))[3]


def _last_date_text(html: str, key: str = "quotes") -> str:
    """The Last data date cell's text (the fifth cell) of one row."""
    return _cells(_main_row(html, key))[4]




















def _sec_entry(**over) -> dict:
    """One ``sec_files.health_summary`` entry: stored rows, the file's figures and the last pull."""
    entry = {"present": 5, "members": 5, "floor": 3, "file_rows": 5,
             "last_modified": "Mon, 19 Oct 2026 20:30:00 GMT", "appended": 0, "absent": 0,
             "good_session": "2026-10-19", "session": "2026-10-19",
             "last_pull": "ok", "error": None}
    entry.update(over)
    return entry



# ── G4 of the GUI brief (#124): the filters above the table ──────────────────────────────────


def _filter_bar(html: str) -> str:
    """The filter bar alone: everything between it and the table it filters."""
    return html[html.index('id="inv-filters"'):html.index('id="inv-table"')]


def _chip_texts(bar: str, kind: str) -> list:
    import re
    return re.findall(r'data-chips="%s"[^>]*>(.*?)</button>' % kind, bar, re.S)
















def test_the_filters_run_under_node(tmp_path):
    """``settingsFilter`` against a DOM stub: the find box, the chips, the count line and the
    detail row that must collapse with its dataset. Nothing here is asserted from the source text."""
    import json as _json
    import shutil
    import subprocess
    import pytest
    from RevenueChaser.core.tests.board_js import function_source
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    js = (function_source(report.JS, "settingsRowPairs")
          + function_source(report.JS, "settingsFilter")
          + function_source(report.JS, "settingsFilterClear")
          + r"""
function el(attrs, cls){
  var o = {attrs: attrs || {}, hidden: false, className: cls || "", textContent: "",
           disabled: false, querySelector: function(){ return null; }};
  o.getAttribute = function(k){ return o.attrs[k] == null ? null : o.attrs[k]; };
  o.setAttribute = function(k, v){ o.attrs[k] = String(v); };
  return o;
}
function dataset(name, tables, db, source, state){
  var tr = el({"data-db": db, "data-source": source, "data-state": state}, "row");
  tr.button = el({"aria-expanded": "false"});
  tr.button.textContent = name;
  tr.querySelector = function(sel){ return sel === ".det-btn" ? tr.button : null; };
  tr.detail = el({}, "detail");
  tr.detail.hidden = true;
  tr.tbl = el({});
  tr.tbl.textContent = tables;
  tr.detail.querySelector = function(sel){ return sel === ".tbl" ? tr.tbl : null; };
  return tr;
}
var rows = [dataset("Equity universe", "equity_universe equity_universe_changes", "raw", "yfinance", ""),
            dataset("10-K / 20-F corpus", "chain_filings edgar_documents", "edgar", "sec", "no denominator"),
            dataset("CFTC E-mini Commitments of Traders", "cftc_cot", "raw", "finra/cftc",
                    "needs attention|no time column")];
var tbody = {children: []};
rows.forEach(function(tr){ tbody.children.push(tr, tr.detail); });
function chip(kind, value){
  var b = el({"aria-pressed": "false", "data-chips": kind, "data-value": value});
  return b;
}
var groups = {db: [chip("db", "raw"), chip("db", "edgar")],
              source: [chip("source", "yfinance"), chip("source", "sec"), chip("source", "finra/cftc")],
              state: [chip("state", "needs attention"), chip("state", "no time column"),
                      chip("state", "no denominator")]};
var box = el({}); box.value = "";
var count = el({}); var clear = el({}); clear.disabled = true;
globalThis.document = {
  getElementById: function(id){
    return id === "inv-find" ? box : id === "inv-count" ? count : id === "inv-clear" ? clear : null; },
  querySelector: function(sel){ return sel === "#inv-table tbody" ? tbody : null; },
  querySelectorAll: function(sel){
    if(sel === '#inv-filters button[aria-pressed="true"]'){
      var on = [];
      Object.keys(groups).forEach(function(k){ groups[k].forEach(function(b){
        if(b.attrs["aria-pressed"] === "true") on.push(b); }); });
      return on;
    }
    return [];
  }
};
function toggle(kind, value){
  groups[kind].forEach(function(b){
    if(b.attrs["data-value"] === value){
      b.attrs["aria-pressed"] = b.attrs["aria-pressed"] === "true" ? "false" : "true";
    }
  });
}
function reset(){
  Object.keys(groups).forEach(function(k){ groups[k].forEach(function(b){ b.attrs["aria-pressed"] = "false"; }); });
  box.value = "";
}
function visible(){ return rows.filter(function(tr){ return !tr.hidden; })
                                 .map(function(tr){ return tr.button.textContent; }); }
function state(){ return {shown: visible(), count: count.textContent, clear: !clear.disabled,
                         details: rows.map(function(tr){ return tr.detail.hidden; })}; }
var out = {};
settingsFilter();
out.none = state();
box.value = "COT";
settingsFilter();
out.byName = state();
box.value = "chain_filings";
settingsFilter();
out.byTable = state();
reset(); toggle("db", "raw"); toggle("source", "sec");
settingsFilter();
out.and = state();
reset(); toggle("db", "raw");
groups.db[1].attrs["aria-pressed"] = "true";       // two chips in one group: raw or edgar
settingsFilter();
out.or = state();
reset(); toggle("state", "needs attention");
settingsFilter();
out.stateChip = state();
reset(); toggle("state", "needs attention");
rows[2].button.setAttribute("aria-expanded", "true");
rows[2].detail.hidden = false;
box.value = "universe";
settingsFilter();
out.collapsed = {details: rows.map(function(tr){ return tr.detail.hidden; }),
                 expanded: rows[2].button.attrs["aria-expanded"]};
toggle("db", "raw");                               // a filter is on, then Clear filters is pressed
settingsFilterClear();
out.cleared = state();
console.log(JSON.stringify(out));
""")
    path = tmp_path / "settings_filters.js"
    path.write_text(js, encoding="utf-8")
    out = subprocess.run(["node", str(path)], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr[-2000:]
    got = _json.loads(out.stdout.strip().splitlines()[-1])

    all_three = ["Equity universe", "10-K / 20-F corpus", "CFTC E-mini Commitments of Traders"]
    assert got["none"] == {"shown": all_three, "count": "Showing 3 of 3 datasets",
                           "clear": False, "details": [True, True, True]}
    assert got["byName"]["shown"] == ["CFTC E-mini Commitments of Traders"], "the dataset name matches"
    assert got["byName"]["count"] == 'Showing 1 of 3 datasets · filtered by search "COT"'
    assert got["byName"]["clear"] is True
    assert got["byTable"]["shown"] == ["10-K / 20-F corpus"], "a store table name matches"
    assert got["and"]["shown"] == [], "raw AND sec is no row at all"
    assert got["and"]["count"] == ("Showing 0 of 3 datasets · filtered by store file raw · "
                                  "source sec")
    assert got["or"]["shown"] == all_three, "two chips in one group widen the result"
    assert got["stateChip"]["shown"] == ["CFTC E-mini Commitments of Traders"]
    assert got["stateChip"]["count"] == "Showing 1 of 3 datasets · filtered by state needs attention"
    assert got["collapsed"] == {"details": [True, True, True], "expanded": "false"}, \
        "a hidden dataset takes its detail row down and leaves it collapsed"
    assert got["cleared"] == {"shown": all_three, "count": "Showing 3 of 3 datasets",
                              "clear": False, "details": [True, True, True]}

# ── G5 of the GUI redesign (#124): the summary tiles above the table ────────────────────────────
def _tile_value(html: str, label: str) -> str:
    """The number the summary tile labelled ``label`` shows; fails when the tile is absent."""
    import re
    found = re.search(r'<div class="stile-n">([^<]*)</div><div class="stile-l" id="[^"]*">'
                      + re.escape(label) + "</div>", html)
    assert found, f"no summary tile labelled {label}"
    return found.group(1)


def _tile_row(key: str, **over) -> dict:
    """One row shaped the way ``inventory._collect`` builds it: healthy unless a field is replaced."""
    row = {"key": key, "label": key, "tables": [f"{key}_table"], "rows": 10,
           "last_date": "2026-09-18", "holes": None,
           "coverage": {"fraction": 1.0, "label": "10 / 10 (100%)"}}
    row.update(over)
    return row


def _tile_html(rows: list[dict], timing=None, errors=None) -> str:
    payload = {"generated_at": "2026-09-25T20:00:00+00:00", "rows": rows}
    if timing is not None:
        payload["timing"] = timing
    if errors is not None:
        payload["errors"] = errors
    return report.render_settings_dashboard(payload)













# ── S6 of the Data Health plan (#124): "Other store tables" ─────────────────────────────────
# Every MANIFEST table no dataset claims, with its row count and newest date only. Normally
# empty (S3 claims them all), so the section is the honest intermediate state and the backstop.
_OTHER_SENTENCE = ("These store tables are not claimed by any dataset yet, so they carry no "
                   "source and no coverage.")


def _other_section(html: str) -> str:
    start = html.index('id="other-tables"')
    return html[start:].split("</section>")[0]








def test_every_registry_source_is_spelled_out_in_words():
    """avo's copy rule: no 'uw' or 'sec' shorthand on the board. Every provider value the registry can carry has
    plain words, and none of them is the raw short form."""
    from RevenueChaser.core import datasets
    for source in datasets.Source:
        words = report.source_words(source.value)
        assert source.value in report.SOURCE_WORDS, source.value
        assert words != source.value
        assert len(words) > 3
    assert report.source_words("something-new") == "something-new"


# ── G11 of the GUI brief (#124): what is missing, and how it improves ───────────────────────
def _detail_text(html: str, key: str) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _detail_row(html, key))).strip()
























# ── G6b of the GUI redesign (#124): the Data Flow diagram ─────────────────────────────────────
# Provider → job → store file, built from the rows the table already collected. Pure: no store
# read, no second pass over the registry, so the diagram costs page weight and never query time.


def _flow_section(rows) -> str:
    """The page's own section, through the renderer's function."""
    return report._flow_section(rows)




def test_a_dataset_without_a_writer_joins_the_started_by_hand_node():
    graph = report.flow_graph([{"key": "x", "source": "sec", "writer": None, "db": "raw"}])
    assert [j["name"] for j in graph["jobs"]] == ["started by hand from the dashboard"]
    assert graph["providers"] == [{"name": "SEC EDGAR filings", "count": 1}]


@pytest.mark.parametrize("row,words", [
    # the registry does not know it: no source key, or an empty one
    ({"key": "x", "db": "raw"}, "unknown provider"),
    ({"key": "x", "source": "", "db": "raw"}, "unknown provider"),
    # the registry's own "no single provider" value keeps the words the dataset table uses for it
    ({"key": "x", "source": "unknown", "db": "raw"}, "more than one provider, or not known"),
])
def test_a_dataset_without_a_provider_says_unknown_provider_in_words(row, words):
    graph = report.flow_graph([row])
    assert [p["name"] for p in graph["providers"]] == [words]


def test_a_row_without_a_store_file_takes_the_registry_file_without_reading_the_store():
    from RevenueChaser.core import datasets
    spec = next(s for s in datasets.REGISTRY if s.db == "history")
    graph = report.flow_graph([{"key": spec.key, "source": spec.source.value, "writer": spec.writer}])
    assert [s["name"] for s in graph["stores"]] == ["history"]








def test_a_hostile_provider_or_job_name_is_escaped_in_text_and_in_an_attribute():
    bad = """<img src=x onerror=__x(1)>"&'"""
    section = report._flow_section([{"key": "x", "source": bad, "writer": bad, "db": "raw"}])
    assert "<img" not in section
    assert "&lt;img src=x onerror=__x(1)&gt;" in section
    assert 'data-provider="' in section and 'data-job="' in section
    assert bad not in section, "never raw, in text or inside a quoted attribute"


def test_a_name_too_long_for_its_column_is_cut_and_its_hover_title_keeps_all_of_it():
    """A layout guard, not a wording rule: the real providers and jobs all fit, so only a value
    that could not fit is cut, and the node's own title still carries every word of it."""
    long_name = "RC-" + "VeryLongTaskName" * 4
    section = _flow_section([{"key": "x", "source": "sec", "writer": long_name, "db": "raw"}])
    shown = long_name[:report.FLOW_TEXT_MAX - 1] + "…"
    assert f">{shown}</text>" in section
    assert f">{long_name}</text>" not in section, "the column cannot hold it"
    assert f"<title>{long_name} — 1 dataset</title>" in section, "the whole name is still there"




def test_two_flows_sharing_one_pair_draw_side_by_side_so_neither_colour_hides_the_other():
    """Two datasets from one provider, written by one job, landing in different store files take the
    same provider-to-job box pair. Drawn on one exact line, the second file's colour would cover the
    first and the picture would silently lose a flow."""
    graph = report.flow_graph([{"key": "a", "source": "sec", "writer": "W", "db": "raw"},
                               {"key": "b", "source": "sec", "writer": "W", "db": "edgar"}])
    svg = report._flow_svg(graph)
    shared = [tag for tag in re.findall(r'<path class="flow-edge"[^>]*>', svg)
              if 'data-a="provider:SEC EDGAR filings"' in tag and 'data-b="job:W"' in tag]
    assert len(shared) == 2
    assert len({re.search(r' d="([^"]+)"', tag).group(1) for tag in shared}) == 2, (
        "the two lines are the same line, so one store file's colour is hidden")
    assert any('stroke="#4f8cff"' in tag for tag in shared), "raw's line is still its own"
    assert any('stroke="#e0a030"' in tag for tag in shared), "edgar's line is still its own"


def test_a_store_file_outside_the_four_files_draws_in_muted_ink_and_says_so():
    svg = report._flow_svg(report.flow_graph([{"key": "x", "source": "sec", "writer": "W"}]))
    assert report.FLOW_NO_STORE in svg
    assert 'stroke="#8a93a6"' in svg
    section = _flow_section([{"key": "x", "source": "sec", "writer": "W"}])
    assert "names no store file" in section, "the legend explains the grey line"
    assert len(report.DB_PILLS) == 4 and "outside the four" in section, "the legend counts the files it lists"










def test_the_real_registry_diagram_stays_under_the_budget():
    """The ~60 datasets of the real registry, built from the registry alone (no store read)."""
    from RevenueChaser.core import datasets
    rows = [{"key": s.key, "source": s.source.value, "writer": s.writer, "db": s.db}
            for s in datasets.REGISTRY]
    svg = report._flow_svg(report.flow_graph(rows))
    assert len(svg.encode("utf-8")) < report.FLOW_MAX_BYTES, f"{len(svg)} bytes"
    assert '<details class="flow" open>' in _flow_section(rows)
# ── S7 of the Data Health plan (#124): "Identity coverage" ───────────────────────────────────
# Not on the page since PR 5 (D9): the spine's identity funnel replaced it
# (module_settings/tests/test_newdata_spine.py). The payload still carries the section until the old inventory goes.


# ── G7 of the GUI brief (#124): the drill below the table, and which boards can score the name ──
def _drill_section(html: str) -> str:
    """The drill's own block: its heading and search box, up to the closed detail panel."""
    return html[html.index('id="ticker-drill"'):html.index('id="drill"')]


def _panel(html: str, ident: str) -> str:
    start = html.index(f'id="{ident}"')
    nxt = html.find('role="tabpanel"', html.index(">", start))
    return html[start:nxt if nxt > 0 else len(html)]






def test_the_tabs_map_data_and_health_and_old_choices_land_on_them():
    assert report.SETTINGS_TABS["tabs"] == {"data": "panel-data", "health": "panel-health", "logs": "panel-logs"}
    assert report.SETTINGS_TABS["first"] == "data" and "show(start || FIRST, false)" in report.TABS_JS
    # a viewer whose remembered tab is the Watch lists one (12 Nov 2026 only) lands on Database
    assert report.SETTINGS_TABS["aliases"] == {"fetch": "data", "needs": "data", "live": "health", "watch": "data"}
    assert "CFG.aliases[name]" in report.TABS_JS






