"""v2 step 6 (#1264): the door's health probes and their 2 s budget.

The budget is the point of these tests. A probe that hangs must be reported as a timeout while the others still
answer, because the failure the run plan's "2 s probes" guard against is a dependency that is reachable but wedged
— and a health route that hangs with it tells a monitor nothing.
"""
from __future__ import annotations

import time

from RevenueChaser.v2.door import boards, config, health


def test_a_wedged_probe_is_a_timeout_and_the_others_still_answer():
    def wedged():
        time.sleep(30)
        return True, "never"

    started = time.monotonic()
    result = health.run({"artifacts": lambda: (True, "fine"), "wedged": wedged}, budget_s=0.2)
    took = time.monotonic() - started
    assert took < 5, f"the route waited {took:.1f}s on a wedged probe"
    by_name = {c["check"]: c for c in result["checks"]}
    assert by_name["wedged"]["ok"] is False
    assert "0.2s" in by_name["wedged"]["detail"]
    assert by_name["artifacts"]["ok"] is True


def test_a_probe_that_raises_is_red_with_its_message_and_never_a_traceback():
    def angry():
        raise ConnectionError("redis://user:secret@host refused")

    result = health.run({"artifacts": lambda: (True, "fine"), "redis": angry})
    detail = {c["check"]: c for c in result["checks"]}["redis"]["detail"]
    assert detail.startswith("ConnectionError: ")
    assert "Traceback" not in detail


def test_only_a_required_probe_turns_the_status_degraded():
    assert health.REQUIRED == ("artifacts",)
    ok = health.run({"artifacts": lambda: (True, "fine"), "redis": lambda: (False, "down")})
    assert ok["status"] == "ok" and ok["failed"] == []
    bad = health.run({"artifacts": lambda: (False, "gone"), "redis": lambda: (True, "PING")})
    assert bad["status"] == "degraded" and bad["failed"] == ["artifacts"]


def test_an_unconfigured_dependency_is_not_a_fault(monkeypatch):
    """No ``RC_REDIS_URL`` is a complete read side, not a red probe: the door reads files."""
    monkeypatch.delenv("RC_REDIS_URL", raising=False)
    ok, detail = health.probe_redis()
    assert ok is None
    assert "not set" in detail
    assert health.run({"artifacts": lambda: (True, "fine"), "redis": health.probe_redis})["status"] == "ok"


def test_the_artifacts_probe_counts_the_envelopes_it_can_see(monkeypatch, tmp_path):
    monkeypatch.setattr(boards, "artifacts_dir", lambda: tmp_path)
    ok, detail = health.probe_artifacts()
    assert ok is True
    assert detail.startswith(f"0/{len(boards.board_keys())} envelopes")


def test_a_missing_artifacts_root_is_red(monkeypatch, tmp_path):
    monkeypatch.setattr(boards, "artifacts_dir", lambda: tmp_path / "gone")
    ok, detail = health.probe_artifacts()
    assert ok is False
    assert "not a directory" in detail


def test_the_budget_the_run_plan_asked_for_is_the_default():
    assert config.PROBE_BUDGET_S == 2.0
    assert health.run({"artifacts": lambda: (True, "fine")})["budget_s"] == 2.0
