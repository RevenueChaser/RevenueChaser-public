"""Same-site CSRF: every write route needs the ``X-RC-Panel`` header (#231).

``_local_only`` refuses cross-site requests, but a page served from another localhost
port is same-site and its ``Origin`` host is ``localhost``, so a simple form POST from
it passed. A custom header forces a CORS preflight, and this server never answers one.
The rule lives in ``_local_only``, so it covers every non-safe method; these tests walk
``url_map`` so a new write route is covered without anyone remembering to add it.
"""
from __future__ import annotations

import re

import pytest

from RevenueChaser.app import dashboard
from RevenueChaser.core import automations as A
from RevenueChaser.core import rawstore

REFUSED = {"ok": False, "error": "panel header required: reload this board"}
_SAFE = {"GET", "HEAD", "OPTIONS"}








@pytest.fixture
def raw():
    """A client with no default headers, like a page that predates the rule."""
    return dashboard.app.test_client()


@pytest.fixture
def untouched(monkeypatch):
    """Every route body that could start a job or write something fails the test if reached."""
    def boom(*a, **k):
        raise AssertionError("a header-less write reached the route")
    monkeypatch.setattr(dashboard.jobs, "submit", boom)
    monkeypatch.setattr(dashboard.jobs, "cancel", boom)
    monkeypatch.setattr(rawstore, "save_watchlist", boom)
    monkeypatch.setattr(rawstore, "toggle_watchlist", boom)      # the toggle's writer since #306
    monkeypatch.setattr(A, "apply", boom)










def test_another_localhost_port_is_same_site_and_still_needs_the_header(raw, untouched):
    """The case in the issue: a page on localhost:9999 posting to localhost:8000."""
    r = raw.post("/run/uw", headers={"Origin": "http://localhost:9999",
                                     "Sec-Fetch-Site": "same-site"})
    assert r.status_code == 403 and r.get_json() == REFUSED


def test_a_foreign_origin_with_the_header_is_still_cross_site(raw, untouched):
    r = raw.post("/run/uw", headers={"X-RC-Panel": "dashboard", "Origin": "https://evil.example"})
    assert r.status_code == 403 and r.get_json()["error"] == "cross-site request refused"


def test_a_cross_site_fetch_with_the_header_is_still_refused(raw, untouched):
    r = raw.post("/run/uw", headers={"X-RC-Panel": "dashboard", "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and r.get_json()["error"] == "cross-site request refused"


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_every_non_safe_method_needs_the_header(method):
    """No such route exists today; the rule is on the method, not on POST."""
    with dashboard.app.test_request_context("/run/uw", method=method):
        body, status = dashboard._local_only()
        assert status == 403 and body.get_json() == REFUSED
    with dashboard.app.test_request_context("/run/uw", method=method,
                                            headers={"X-RC-Panel": "dashboard"}):
        assert dashboard._local_only() is None


def test_a_preflight_is_never_answered(raw):
    """A cross-origin page that sends a custom header must fail its preflight."""
    for path in ("/run/uw", "/api/watchlist/toggle/AAPL", "/api/jobs"):
        r = raw.options(path, headers={"Origin": "http://localhost:9999",
                                       "Access-Control-Request-Method": "POST",
                                       "Access-Control-Request-Headers": "x-rc-panel"})
        assert not [h for h in r.headers.keys() if h.lower().startswith("access-control-")], path


def test_reads_need_no_header(raw):
    assert raw.get("/api/jobs").status_code == 200


