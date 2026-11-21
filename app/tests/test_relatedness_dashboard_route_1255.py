"""#1255: the weekly Relatedness profiling run happens in the dashboard, not in a writer process of its own.

The timer's run of 21 Nov 2026 03:42 CET ended after 74 s with ``StoreLockedError``: it opened
``.store/boards/relatedness.duckdb`` itself while another RevenueChaser process held it, waited the ~29 s
``core.rawstore.brief_wait`` allows and exited 1, so the week's run was lost and the board kept serving the
previous payload. The documented single-writer route is the dashboard (CLAUDE.md, Data safety), and these are the
pieces that were missing for it: a registered runner for the whole-board Fetch, a ``POST /run/module_relatedness``
that refuses a second start, and the spend cap travelling from the task to the writer.
"""
from __future__ import annotations

import pytest

from RevenueChaser.app import dashboard, jobs, runners
from RevenueChaser.core.tests.panel_client import panel_test_client


class _FakeUW:
    """These route tests must not reach the network."""

    def verify(self):
        return True, None

    def close(self):
        pass


@pytest.fixture(autouse=True)
def queued_jobs_only(monkeypatch):
    """Submit without starting a worker and without a real UW probe; the registry starts empty."""
    monkeypatch.setattr(jobs, "_ensure_worker", lambda: None)
    monkeypatch.setattr(jobs, "_ensure_long_worker", lambda: None)
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(jobs, "_SEQ", {})
    monkeypatch.setattr(dashboard, "_uw", lambda: _FakeUW())


@pytest.fixture
def client():
    return panel_test_client(dashboard.app)


#: What the scheduled caller sends: ``scripts/board_fetch.py`` and home-server's ``bin/rc-dashboard-job`` both do.
CLI = {"X-RC-Panel": "cli"}


def _queued(module: str) -> list[dict]:
    return [j for j in jobs.list_jobs() if j["module"] == module]


# ── the runner the dashboard runs ────────────────────────────────────────────

def test_the_whole_board_fetch_has_a_registered_runner_on_the_long_lane():
    """Without a runner there is no route and no job: the only way left was a second writer process."""
    assert jobs._RUNNERS.get("module_relatedness") is runners.run_relatedness
    assert jobs._LANE["module_relatedness"] == "long"
    assert jobs._PRODUCES["module_relatedness"] == ["module_relatedness"]
    assert jobs._REQUIRES_UW["module_relatedness"] is False


@pytest.fixture
def writer_seam(monkeypatch, tmp_path):
    """``engine.run`` and the board files at their seams: the question here is what reaches the writer."""
    from RevenueChaser.module_relatedness import engine, report

    seen: dict = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return {"companies": [], "peers": {}, "n": 0, "pending": 0}

    monkeypatch.setattr(engine, "run", fake_run)
    monkeypatch.setattr(report, "render_relatedness_board", lambda payload: ("<html></html>", None))
    monkeypatch.setattr(runners, "RELATEDNESS_JSON", tmp_path / "relatedness.json")
    monkeypatch.setattr(runners, "RELATEDNESS_LATEST", tmp_path / "relatedness.html")
    monkeypatch.setattr(runners, "RELATEDNESS_PEERS_DIR", tmp_path / "peers" / "peers")
    monkeypatch.setattr(runners, "_write_board", lambda *a, **k: a[0])
    return seen


def test_the_runner_carries_the_task_s_spend_cap_to_the_writer(writer_seam):
    """``--cap 10`` was avo's ceiling (2 Nov 2026). The module's own default is 25, so the run has to say 10."""
    runners.run_relatedness(None, usd_cap=10.0)
    assert writer_seam["usd_cap"] == 10.0
    assert writer_seam["no_fetch"] is False


def test_a_run_without_one_leaves_the_module_s_own_cap_alone(writer_seam):
    runners.run_relatedness(None)
    assert writer_seam["usd_cap"] is None


# ── the route the task posts ─────────────────────────────────────────────────

def test_the_route_queues_the_fetch(client):
    r = client.post("/run/module_relatedness", headers=CLI)
    assert r.status_code == 202 and r.get_json()["ok"] is True
    assert len(_queued("module_relatedness")) == 1


def test_the_cap_the_task_sends_reaches_the_queued_job(client):
    r = client.post("/run/module_relatedness", headers=CLI, data={"usd_cap": "10"})
    assert r.status_code == 202
    assert jobs._JOBS[r.get_json()["job_id"]]["params"] == {"usd_cap": 10.0}


def test_the_task_without_a_cap_queues_none_at_all(client):
    r = client.post("/run/module_relatedness", headers=CLI)
    assert jobs._JOBS[r.get_json()["job_id"]]["params"] == {}


def test_a_second_start_is_refused_with_the_running_job_s_id(client):
    first = client.post("/run/module_relatedness", headers=CLI).get_json()["job_id"]
    again = client.post("/run/module_relatedness", headers=CLI)
    assert again.status_code == 409 and again.get_json()["job_id"] == first
    assert len(_queued("module_relatedness")) == 1, "a multi-minute pass must not queue twice"


@pytest.mark.parametrize("bad", ["ten", "-1"])
def test_a_cap_that_is_not_a_positive_number_is_refused_before_the_queue(client, bad):
    r = client.post("/run/module_relatedness", headers=CLI, data={"usd_cap": bad})
    assert r.status_code == 400 and _queued("module_relatedness") == []


def test_only_the_scheduled_caller_may_start_it(client):
    """Decision D1/D2 stays: the board has no Fetch for this pass, because its writer may be the paid one."""
    assert client.post("/run/module_relatedness", headers={"X-RC-Panel": "dashboard"}).status_code == 403
    assert jobs.list_jobs() == []
