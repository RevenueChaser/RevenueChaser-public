"""#763: the scorer that judges the section cutters against the hand-checked truth file.

Offline by construction: the documents are synthetic, written under a temporary raw root, and the cutters are
either fakes (for the scoring arithmetic) or our own two rules (for the one end-to-end run). No edgartools, no
network, no model.
"""
from __future__ import annotations

import gzip
import hashlib
import json

import pytest

from RevenueChaser.rcdata import sec_sections
from RevenueChaser.rcdata.build.sec_forms import score

FILLER = "We make widgets for customers in many markets and sell them through several channels. "


def _html(body_items: str) -> str:
    toc = "<p>Table of Contents</p><p>Item 1. Business</p><p>Item 1A. Risk Factors</p><p>Item 2. Properties</p>"
    return f"<html><body>{toc}<p>PART I</p>{body_items}</body></html>"


def _filing():
    business = "".join(f"<p>{FILLER * 4}</p>" for _ in range(30))
    risks = "".join(f"<p>Risks are many. {FILLER}</p>" for _ in range(20))
    return _html(f"<p>Item 1. Business</p>{business}<p>Item 1A. Risk Factors</p>{risks}"
                 "<p>Item 2. Properties</p><p>We own a building.</p>")


def _truth_case(text: str, accession: str = "0000000001-26-000001", form: str = "10-K") -> dict:
    start = text.rfind("\n", 0, text.rfind("Item 1. Business")) + 1
    end = text.rfind("\n", 0, text.rfind("Item 1A. Risk Factors")) + 1
    return {"id": "fake-10-k", "cik": "0000000001", "accession": accession, "form": form, "document": "fake.htm",
            "doc_sha256": hashlib.sha256(text.encode()).hexdigest(), "section": "item_1", "expect": "section",
            "start": start, "end": end, "chars": end - start}


def _store(root, case, html, exhibit=None):
    folder = root / "raw" / "sec" / "filings" / "documents" / case["cik"]
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{case['accession']}.{exhibit}.gz" if exhibit else f"{case['accession']}.html.gz"
    with gzip.open(folder / name, "wt", encoding="utf-8") as fh:
        fh.write(html)


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setattr(score.base, "raw_root", lambda: tmp_path / "raw")
    return tmp_path


def test_the_truth_file_is_well_formed():
    """The held-out file is data a person edits by hand; a slip in it must fail here, not mislead a score."""
    truth = score.load_truth()
    ids = [c["id"] for c in truth["cases"]]
    assert len(ids) == len(set(ids)) == 20
    for c in truth["cases"]:
        assert c["section"] in score.SECTIONS and c["expect"] in ("section", "crossref")
        if c["expect"] == "section":
            assert c["end"] - c["start"] == c["chars"] > 0, c["id"]
            assert len(c["head"]) == len(c["tail"]) == 60, c["id"]
    agree = [a["accession"] for a in truth["agreement_ids"]]
    assert len(agree) == len(set(agree)) and not set(agree) & {c["accession"] for c in truth["cases"]}


def test_a_cut_that_matches_the_truth_scores_found_and_exact(raw):
    text = sec_sections.strip_html(_filing())
    case = _truth_case(text)
    exact = text[case["start"]:case["end"]].strip()
    row = score.score_case(case, text, exact, slack=200)
    assert row["outcome"] == "found" and row["exact"]
    assert abs(row["start_err"]) <= 2 and abs(row["end_err"]) <= 2 and 0.99 < row["ratio"] <= 1.0


def test_a_short_cut_is_found_but_not_exact_and_says_by_how_much(raw):
    text = sec_sections.strip_html(_filing())
    case = _truth_case(text)
    half = text[case["start"]:case["start"] + case["chars"] // 2]
    row = score.score_case(case, text, half, slack=200)
    assert row["outcome"] == "found" and not row["exact"]
    assert row["end_err"] < -1000 and 0.45 < row["ratio"] < 0.55


def test_a_cut_of_another_section_is_wrong_and_no_cut_is_missed(raw):
    text = sec_sections.strip_html(_filing())
    case = _truth_case(text)
    risks = text[case["end"]:text.rfind("Item 2. Properties")]
    assert score.score_case(case, text, risks, slack=200)["outcome"] == "wrong"
    assert score.score_case(case, text, None, slack=200)["outcome"] == "missed"


def test_a_cut_whose_spacing_differs_is_still_located(raw):
    """edgartools' text is its own, not ``strip_html``'s, so whitespace must not decide whether it is found."""
    text = sec_sections.strip_html(_filing())
    case = _truth_case(text)
    respaced = "  ".join(text[case["start"]:case["end"]].split())
    row = score.score_case(case, text, respaced, slack=200)
    assert row["outcome"] == "found" and row["exact"]


def test_a_crossref_document_scores_right_on_no_cut_and_false_on_any_slice(raw):
    case = {"id": "x", "expect": "crossref", "section": "item_4"}
    assert score.score_case(case, "anything", None, slack=200)["outcome"] == "right"
    assert score.score_case(case, "anything", "a slice", slack=200)["outcome"] == "false"


def test_a_run_reads_stored_documents_scores_every_cutter_and_reports_what_it_could_not_read(raw):
    html = _filing()
    text = sec_sections.strip_html(html)
    case = _truth_case(text)
    _store(raw, case, html)
    gone = dict(case, id="gone", accession="0000000001-26-000002")
    drifted = dict(case, id="drifted", accession="0000000001-26-000003")
    _store(raw, drifted, html + "<p>appended later</p>")
    truth = {"cases": [case, gone, drifted], "agreement_ids": [], "end_slack": 200}
    cutters = {"ours-2": score.CUTTERS["ours-2"], "nothing": lambda c, t: None}
    rows, skipped = score.score(truth, cutters)
    assert skipped == {"gone": "not in the corpus", "drifted": "text differs from the hand-checked one"}
    got = {r["cutter"]: r for r in rows}
    assert got["ours-2"]["outcome"] == "found" and got["nothing"]["outcome"] == "missed"
    table = score.table(rows)
    assert "ours-2" in table and "found 1" in table and "missed 1" in table


def test_the_edgartools_answer_is_read_from_the_cache_and_never_cut(raw, monkeypatch):
    """The scorer never starts the worker: it reads what the cutter already stored, and says n/a otherwise."""
    answers = raw / "answers"
    answers.mkdir()
    monkeypatch.setattr(score.cutter, "answer_path", lambda acc: answers / f"{acc}.jsonl.gz")
    with gzip.open(answers / "a1.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"item": "1A", "text": "risks"}) + "\n")
        fh.write(json.dumps({"item": "Item 1", "text": "the business"}) + "\n")
    edgar = score.CUTTERS["edgartools"]
    assert edgar({"accession": "a1", "section": "item_1"}, "") == "the business"
    assert edgar({"accession": "a2", "section": "item_1"}, "") is score.NOT_CUT
    assert edgar({"accession": "a1", "section": "aif_business"}, "") is score.NOT_CUT


def test_agreement_counts_two_cutters_that_cut_the_same_range_as_agreeing(raw):
    html = _filing()
    text = sec_sections.strip_html(html)
    case = _truth_case(text)
    _store(raw, case, html)
    whole = text[case["start"]:case["end"]]
    truth = {"cases": [], "agreement_ids": [{"cik": case["cik"], "accession": case["accession"], "form": "10-K"}],
             "end_slack": 200}
    same = {"a": lambda c, t: whole, "b": lambda c, t: whole, "c": lambda c, t: whole[:100]}
    pairs, disagree, skipped = score.agreement(truth, same)
    assert pairs[("a", "b")] == (1, 1) and pairs[("a", "c")] == (0, 1)
    assert disagree == {case["accession"]: ["a/c", "b/c"]} and skipped == {}
