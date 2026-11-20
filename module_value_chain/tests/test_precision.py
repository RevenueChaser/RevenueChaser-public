"""Value Chain precision gate: the Wilson 95% lower bound at or above 0.70 (plan v31 section 6). Synthetic labels,
no network."""
from __future__ import annotations

import json

import pytest

from RevenueChaser.module_value_chain import precision as prec


def _labels(n_true, n_false):
    return ([{"src": "A", "dst_ticker": "B", "relation": "supplier", "label": True}] * n_true
            + [{"src": "A", "dst_ticker": "C", "relation": "customer", "label": False}] * n_false)


def test_the_plans_own_numbers_175_labels_need_135_right():
    """Section 6: "At 175 that is 135 right (0.77)"."""
    rep = prec.precision(_labels(135, 40))
    assert rep["passes"] is True and rep["status"] == "pass"
    assert rep["lower_bound"] == pytest.approx(0.7038, abs=1e-4)
    assert prec.precision(_labels(134, 41))["passes"] is False


def test_a_rate_of_070_on_30_labels_does_not_clear_the_bound():
    """The old rule passed 21 of 30 (0.70 point estimate); its lower bound is about 0.52."""
    rep = prec.precision(_labels(21, 9))
    assert rep["precision"] == 0.7 and rep["passes"] is False and rep["status"] == "fail"
    assert rep["lower_bound"] == pytest.approx(0.5212, abs=1e-4)
    assert prec.precision(_labels(3, 0))["status"] == "fail"       # a handful of right labels is no pass either


def test_unlabeled_ignored_and_empty_is_not_measured():
    rep = prec.precision([{"src": "A", "label": None}])
    assert rep["precision"] is None and rep["lower_bound"] is None and rep["status"] == "not measured"
    assert prec.precision([])["passes"] is False


def test_gate_flags_over_max_edges(tmp_path):
    edges = [{"src": "HOT"} for _ in range(41)] + [{"src": "OK"} for _ in range(5)]
    p = tmp_path / "labels.json"
    p.write_text(json.dumps(_labels(135, 40)), encoding="utf-8")
    rep = prec.gate(edges=edges, path=p)
    assert rep["passes"] is True
    assert rep["over_max_edges"] == {"HOT": 41}


def test_the_committed_fixture_is_the_census_that_cleared_the_gate():
    """#1159: the second census sample, drawn fresh after the wrong-edge filter of #1142 and marked under avo's
    lenient rule. It is what ``SERVE_PROFILE_EDGES`` rests on, so the numbers are asserted, not just the shape."""
    labels = prec.load_labels()
    assert len(labels) == 200
    rep = prec.precision(labels)
    assert (rep["n"], rep["tp"], rep["fp"]) == (194, 166, 28)       # 6 rows unmarkable, so not judged
    assert rep["precision"] == pytest.approx(0.8557, abs=1e-4)
    assert rep["lower_bound"] == pytest.approx(0.7993, abs=1e-4)   # above the section 6 rule of 0.70
    assert rep["passes"] is True
    # Every row carries the keys ``served_labels`` matches an edge on, and an unmarkable row says why.
    for l in labels:
        assert l["src"] and l["dst_ticker"] and l["relation"] in ("customer", "supplier")
        assert l["label"] in (True, False, None)
        assert (l["label"] is not None) or l["unmarkable"]
        assert (l["label"] is not False) or l["wrong_because"]
    # A label whose edge the extractor no longer emits says nothing about what the board shows.
    assert prec.gate(served=[])["status"] == "not measured"
    assert prec.gate(served=[])["links"] == 0


def test_load_labels_missing_is_empty():
    from pathlib import Path
    assert prec.load_labels(Path("definitely_missing.json")) == []
