"""Spine health on ``GET /metrics`` (avo, 23 Nov 2026): the three numbers home-server's Grafana alerts read.

(a) the spine/security check's ``coverage`` (Tier A with a CUSIP) against its coverage target, (b) the Tier A rows
of security type ``unknown`` in the live spine against #1334's acceptance (under 30), (c) the open spine/security
build issues, already ``rc_dataset_open_issues``, against a rise within a day. The limits are ``rc_threshold`` values,
so no rule retypes them.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import duckdb
import pytest

from revenuechaser.core import config
from revenuechaser.module_settings import control, metrics, newdata
from revenuechaser.rcdata import ops, serving

NOW = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
SPINE = {"spine/security": SimpleNamespace(kind="spine", providers=("sec",), attended=False)}


@pytest.fixture(autouse=True)
def _market(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MARKET_DIR", tmp_path / "market")
    monkeypatch.setattr(config, "MARKET_RAW_DIR", tmp_path / "market_raw")
    monkeypatch.setattr(ops, "read_log", ops.ReadLog(process="test"))
    (tmp_path / "market").mkdir()


def _families(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith("# TYPE "):
            out.setdefault(line.split()[2], [])
        elif line and not line.startswith("#"):
            out.setdefault(re.split(r"[{ ]", line, maxsplit=1)[0], []).append(line)
    return out


def _collect(**kw):
    kw.setdefault("datasets", SPINE)
    kw.setdefault("timer", {"state": "on"})
    kw.setdefault("ibkr", lambda: {"state": "up"})
    kw.setdefault("lanes", lambda: {})
    kw.setdefault("news", lambda: {})
    return metrics.collect(NOW, **kw)


def _spine(rows: list[tuple[str, str, str | None]]) -> None:
    """A spine file moved over the live name, as the builder's swap does (``os.replace``: a new inode)."""
    new = serving.live_path("spine").with_suffix(".new.duckdb")
    con = duckdb.connect(str(new))
    con.execute("CREATE TABLE security (ticker TEXT, tier TEXT, security_type TEXT)")
    con.executemany("INSERT INTO security VALUES (?, ?, ?)", rows)
    con.close()
    os.replace(new, serving.live_path("spine"))


def test_a_dataset_reports_the_coverage_of_its_newest_build():
    """(a): the share the newest check that built reported; a later skipped run carries none and does not blank it."""
    ops.record_check("spine/security", "changed", checked_on="2026-11-22", coverage=0.9712)
    ops.record_check("spine/security", "skipped", checked_on="2026-11-23")
    fam = _families(metrics.render(_collect()))
    assert fam["rc_dataset_coverage"] == ['rc_dataset_coverage{dataset="spine/security",kind="spine"} 0.9712']


def test_a_dataset_without_a_coverage_has_no_coverage_line():
    ops.record_check("spine/security", "changed", checked_on="2026-11-22")
    assert _families(metrics.render(_collect()))["rc_dataset_coverage"] == []


def test_the_tier_a_rows_of_unknown_type_are_counted_in_the_live_spine():
    """(b): only Tier A, only ``unknown``; a Tier B note and a Tier A common stock do not count."""
    _spine([("BIPH", "A", "unknown"), ("SAX", "A", "unknown"), ("AAPL", "A", "common"), ("GECCG", "B", "unknown"),
            ("XYZ", "A", None)])
    fam = _families(metrics.render(_collect()))
    assert fam["rc_spine_tier_a_unknown_type"] == ["rc_spine_tier_a_unknown_type 2"]


def test_the_spine_is_opened_once_per_build_not_once_per_scrape(monkeypatch):
    """Prometheus scrapes every 60 s; the count changes only when a new spine build is swapped in."""
    _spine([("BIPH", "A", "unknown")])
    opened = []
    real = serving.read_live
    monkeypatch.setattr(serving, "read_live", lambda kind, work: opened.append(kind) or real(kind, work))
    for _ in range(3):
        fam = _families(metrics.render(_collect()))
    assert fam["rc_spine_tier_a_unknown_type"] == ["rc_spine_tier_a_unknown_type 1"]
    assert opened == ["spine"], "the second and third scrape reuse the reading of the same file"
    _spine([("BIPH", "A", "unknown"), ("SAX", "A", "unknown")])
    fam = _families(metrics.render(_collect()))
    assert fam["rc_spine_tier_a_unknown_type"] == ["rc_spine_tier_a_unknown_type 2"]
    assert opened == ["spine", "spine"]


def test_no_spine_yet_leaves_the_count_out_and_is_no_error():
    before = metrics._errors.get("spine", 0)
    fam = _families(metrics.render(_collect()))
    assert fam["rc_spine_tier_a_unknown_type"] == []
    assert metrics._errors["spine"] == before


def test_a_spine_that_cannot_be_read_is_counted_and_takes_only_its_own_line():
    def boom():
        raise RuntimeError("spine.duckdb cannot be read")

    before = metrics._errors.get("spine", 0)
    ops.record_check("spine/security", "changed", checked_on="2026-11-22", coverage=0.99)
    fam = _families(metrics.render(_collect(spine=boom)))
    assert fam["rc_spine_tier_a_unknown_type"] == []
    assert metrics._errors["spine"] == before + 1
    assert fam["rc_dataset_coverage"] == ['rc_dataset_coverage{dataset="spine/security",kind="spine"} 0.99']


def test_the_three_spine_limits_are_thresholds():
    """The rules in home-server's rc.yaml read these; the coverage limit is the screen's own target."""
    fam = _families(metrics.render(_collect()))
    assert newdata.COVERAGE_TARGET.get("spine/security") == 0.98
    assert 'rc_threshold{name="spine_coverage_min"} 0.98' in fam["rc_threshold"]
    assert control.SPINE_UNKNOWN_ALERT == 30
    assert 'rc_threshold{name="spine_tier_a_unknown_max"} 30' in fam["rc_threshold"]
    assert control.SPINE_ISSUES_RISE_ALERT == 0.2
    assert 'rc_threshold{name="spine_issues_rise_share"} 0.2' in fam["rc_threshold"]
