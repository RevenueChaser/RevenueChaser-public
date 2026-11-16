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


def test_a_handful_of_right_labels_is_not_a_pass():
    rep = prec.precision(_labels(3, 0))
    assert rep["precision"] == 1.0 and rep["passes"] is False


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


def test_the_committed_fixture_is_empty():
    """Plan v31 step 1(g): the 80 labels judged the keyword scan #748 deleted; the census fills the file again."""
    assert prec.load_labels() == []
    assert prec.gate(served=[])["status"] == "not measured"


def test_load_labels_missing_is_empty():
    from pathlib import Path
    assert prec.load_labels(Path("definitely_missing.json")) == []
