"""B (owner, 17 Nov 2026): the Value Chain links rebuild by themselves after the nightly SEC read.

The SEC engine runs first, then Value Chain (RC-ValueChain-Sync is chained on RC-SEC-Read). The rebuild reads the SEC
layer and the stored profiles: no download, no model call. It runs in the dashboard, the one writer: the task only
asks it, with the panel header, and waits.
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.app import activity
from revenuechaser.core import automations, datasets
from revenuechaser.module_value_chain import __main__ as cli


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code, self._payload = status_code, payload

    def json(self):
        return self._payload


@pytest.fixture
def seams(monkeypatch):
    """The dashboard at the HTTP boundary: a POST queues a job, ``/api/job/<id>`` reports it."""
    seen: dict = {"posts": [], "job": {"status": "done", "message": "Read 3 filings"}, "post_status": 202}
    monkeypatch.setattr(cli, "_POLL_S", 0)
    monkeypatch.setattr(cli.engine, "_reads_layer", lambda: True)

    def fake_post(url, data=None, headers=None, timeout=None):
        seen["posts"].append((url, headers))
        if seen["post_status"] != 202:
            return _Resp(seen["post_status"], {"ok": False, "error": "busy"})
        return _Resp(202, {"ok": True, "job_id": "j1"})

    def fake_get(url, timeout=None):
        assert url.endswith("/api/job/j1")
        return _Resp(200, {"ok": True, "job": seen["job"]})

    monkeypatch.setattr(cli.httpx, "post", fake_post)
    monkeypatch.setattr(cli.httpx, "get", fake_get)
    return seen


def _line(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_the_night_task_queues_the_rebuild_on_the_dashboard(seams, capsys):
    assert cli.main(["--nightly"]) == 0
    assert seams["posts"] == [("http://127.0.0.1:8000/run/module_value_chain", {"X-RC-Panel": "cli"})]
    assert _line(capsys) == {"status": "done", "job_id": "j1", "message": "Read 3 filings"}


def test_a_failed_refused_or_unreachable_rebuild_exits_1(seams, monkeypatch, capsys):
    seams["job"] = {"status": "error", "error": "boom"}
    assert cli.main(["--nightly"]) == 1 and _line(capsys)["message"] == "boom"
    seams["post_status"] = 409
    assert cli.main(["--nightly"]) == 1 and _line(capsys)["status"] == "refused"

    def down(*a, **k):
        raise cli.httpx.ConnectError("refused")

    monkeypatch.setattr(cli.httpx, "post", down)
    assert cli.main(["--nightly"]) == 1 and _line(capsys)["status"] == "dashboard_down"


def test_off_the_layer_the_task_asks_for_nothing(seams, monkeypatch, capsys):
    """Off the layer a board Fetch downloads from SEC; the night task never starts one."""
    monkeypatch.setattr(cli.engine, "_reads_layer", lambda: False)
    assert cli.main(["--nightly"]) == cli.EXIT_NOT_READY
    assert seams["posts"] == [] and _line(capsys)["status"] == "not_ready"


def test_the_task_runs_after_the_sec_read_and_is_the_value_chain_writer():
    e = automations.entry("RC-ValueChain-Sync")
    assert e.after == "RC-SEC-Read" and e.args == ("-m", "revenuechaser.module_value_chain", "--nightly")
    assert automations.system_unit(e) == "life-rc-valuechain-sync"      # the home-server unit pair's name
    assert next(s for s in datasets.REGISTRY if s.key == "value_chain").writer == e.name
    assert activity.BY_NAME[e.name] == "module_value_chain"
