"""A write to a live dashboard needs ``X-RC-Panel`` (#231).

The unit tests call ``_local_only`` in a request context; this sends the requests over a
real socket to the real server process. The harness client carries the header (as every
page does), so each refused request here is made with a bare ``httpx`` call on purpose.
"""
from __future__ import annotations

import httpx

REFUSED = {"ok": False, "error": "panel header required: reload this board"}


def _jobs(dashboard) -> list:
    return dashboard.get("/api/jobs").json()["jobs"]










def test_a_cancel_without_the_header_is_refused(dashboard):
    r = httpx.post(dashboard.url + "/api/job/nope/cancel")
    assert r.status_code == 403 and r.json() == REFUSED
    assert dashboard.client.post("/api/job/nope/cancel").status_code == 404


def test_reads_need_no_header(dashboard):
    assert httpx.get(dashboard.url + "/api/jobs").status_code == 200
