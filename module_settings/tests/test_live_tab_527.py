"""#527, #715: the Grafana boards live inside the app. Fetch/Health frames the RC rows of Grafana's Jobs, Logs
those of Logs (avo, 21 Nov 2026; until then the boards rc-health and rc-logs; 12 Nov 2026: three tabs, no tab holds
another tab; the Live tab stays gone).

avo, 8 Nov 2026: "bunlarin ne isi var burada? bunlar revenue chaser app icine gomulu olmaliydi". Grafana runs on
the same host as the dashboard, port 3000, and allows only this app's origin to frame it (home-server units/
grafana-server.service.d/life.conf, CSP frame-ancestors). The frame loads only when the tab opens.
"""
from __future__ import annotations

import re

from RevenueChaser.module_settings import report


def _page() -> str:
    return report.render_settings_dashboard({"newdata": {"error": "not read in this test"}, "tickers": []})


def test_three_tabs_database_first_and_each_grafana_tab_frames_one_board():
    """#715 (avo, 12 Nov 2026): Database · Fetch/Health · Logs, and no tab holds another tab, so the board picker
    above the frame is gone: Fetch/Health is the one board rc-health, Logs is rc-logs. The watch lists' own tab
    (one day old) went to the Watch lists board on 13 Nov 2026."""
    html = _page()
    strip = html[html.index('id="settings-tabs"'):html.index("</nav>")]
    assert re.findall(r'role="tab" id="(tab-[a-z]+)"', strip) == ["tab-data", "tab-health", "tab-logs"]
    assert re.findall(r'aria-selected="(true|false)"', strip) == ["true", "false", "false"]
    assert re.findall(r">([^<]+)</button>", strip) == ["Database", "Fetch/Health", "Logs"]
    assert 'id="panel-watch"' not in html and "watch" not in report.SETTINGS_TABS["tabs"]
    assert 'id="panel-live"' not in html and "live" not in report.SETTINGS_TABS["tabs"]
    health = html[html.index('id="panel-health"'):html.index('id="panel-logs"')]
    logs = html[html.index('id="panel-logs"'):html.index("<script>", html.index('id="panel-logs"'))]
    assert health.index('id="live-frame"') < health.index("<h1>Settings · Universe and fills</h1>")
    # avo, 21 Nov 2026: the RC rows of Grafana's Jobs and Logs, framed with ?part=rc (test_the_grafana_address)
    assert re.findall(r'data-board="([a-z-]+)"', health) == ["jobs"]
    assert re.findall(r'data-board="([a-z-]+)"', logs) == ["logs"]
    assert "<button" not in health[:health.index('id="live-frame"')], "no picker: a tab holds no other tab"
    assert re.search(r'<div[^>]*id="panel-logs"[^>]*role="tabpanel"[^>]*aria-labelledby="tab-logs"[^>]*hidden', html)
    assert "<button" not in logs and logs.count("<iframe") == 1


def test_the_frames_have_no_source_until_their_tab_opens():
    """A Database visit must not load Grafana: each frame gets its address from the script, on its tab's open."""
    html = _page()
    frames = re.findall(r"<iframe[^>]*>", html)
    assert len(frames) == 2
    for frame in frames:
        assert " src=" not in frame
        assert 'title="' in frame and 'loading="lazy"' in frame


def test_the_grafana_address():
    js = report.LIVE_JS
    assert "location.hostname" in js and "':3000/d/'" in js, "same host as the page, Grafana's port"
    assert "kiosk" in js and "theme=" in js and "&part=rc" in js, "only the board's RC rows (avo, 21 Nov 2026)"
    assert "panel.hidden" in js and "aria-labelledby" in js, "a frame loads only while its own tab is open"
    assert [(p, uid) for p, uid, _, _ in report.LIVE_BOARDS] == [("panel-health", "jobs"), ("panel-logs", "logs")]



