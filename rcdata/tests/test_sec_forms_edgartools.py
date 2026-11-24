"""The edgartools item cutter wired into ``sec/forms`` (#754, avo 24 Nov 2026, pin 6.3.0).

The worker is faked: no runner has the edgartools venv. What is pinned is our side -- which documents are sent to
the cutter, how its answer becomes the business row, what label every row carries, and that a document edgartools
cannot cut still gets our own cut.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from revenuechaser.core.providers import sec_edgar
from revenuechaser.rcdata import sec_sections
from revenuechaser.rcdata.build.sec_forms import cut, cutter, forms

from . import fund_fixture as fx
from .test_sec_forms_serving import MSFT, _cut, _stored, q

BODY = "Our business is the cloud. " * 120          # over MIN_ITEM_CHARS, and not what our own rule cuts


def _answer(path: Path, *rows: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


# ── the label ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_row_label_names_the_pinned_edgartools_version():
    """A pin bump that forgets the label would serve a new cut under the old name, and the readers that pin the
    label would never see that anything moved."""
    assert sec_sections.FORMS_ROWS_VERSION == f"{sec_sections.OURS_2}+edgartools-{cutter.pinned_version()}"


def test_the_header_rollback_labels_the_rows_ours_2_again(monkeypatch):
    monkeypatch.setenv(cutter.MODE_ENV, "header")
    assert forms.rows_version() == sec_sections.OURS_2
    monkeypatch.setenv(cutter.MODE_ENV, "edgartools")
    assert forms.rows_version() == sec_sections.FORMS_ROWS_VERSION


def test_an_unknown_mode_fails_before_a_row_is_labelled(monkeypatch):
    monkeypatch.setenv(cutter.MODE_ENV, "edgar")
    with pytest.raises(cutter.CutterUnusable):
        forms.rows_version()


# ── the mapping ───────────────────────────────────────────────────────────────────────────────────────────────

def test_item_1_of_a_10k_and_item_4_of_a_20f_are_the_business_section(tmp_path):
    a = _answer(tmp_path / "a.jsonl.gz", {"item": "Item 1A", "text": "risk " * 900, "confidence": 0.95},
                {"item": "Item 1", "text": BODY, "confidence": 0.95},
                {"item": "Item 4", "text": "information on the company " * 100, "confidence": 0.95})
    assert cut.business(a, "10-K") == (BODY, "ok")
    assert cut.business(a, "20-F")[0].startswith("information on the company")


def test_a_combined_heading_holds_the_business_item(tmp_path):
    """"Items 1 and 2. Business and Properties" is one section with ``item='1'``-or-``'2'`` and both covered."""
    a = _answer(tmp_path / "a.jsonl.gz", {"item": "2", "covered_items": ["1", "2"], "text": BODY})
    assert cut.business(a, "10-K") == (BODY, "ok")


def test_a_doubtful_section_is_served_with_a_suspect_flag(tmp_path):
    low = _answer(tmp_path / "low.jsonl.gz", {"item": "1", "text": BODY, "confidence": 0.5})
    warned = _answer(tmp_path / "warned.jsonl.gz", {"item": "1", "text": BODY, "confidence": 0.95,
                                                    "warnings": ["pointer"]})
    assert cut.business(low, "10-K") == (BODY, f"ok;{cut.SUSPECT}")
    assert cut.business(warned, "10-K") == (BODY, f"ok;{cut.SUSPECT}")


def test_no_section_a_short_one_or_a_form_without_vocabulary_is_handed_back(tmp_path):
    a = _answer(tmp_path / "a.jsonl.gz", {"item": "1", "text": "Business. See Item 15."},
                {"item": "7", "text": BODY})
    assert cut.business(a, "10-K") is None, "a pointer under MIN_ITEM_CHARS is not served as the section"
    assert cut.business(a, "20-F") is None, "no Item 4 in it"
    assert cut.business(a, "40-F") is None and cut.business(a, "10-KT") is None


@pytest.fixture
def sec(monkeypatch, http_mock):
    """As ``test_sec_forms_serving.sec``: the SEC at a test host and the spine on disk."""
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec_edgar, "SEC_DATA_BASE", "https://data.sec.test")
    fx.spine()
    return http_mock


# ── the layer ─────────────────────────────────────────────────────────────────────────────────────────────────

class FakeCutter:
    """``cutter.Cutter`` as the layer uses it: ``cut`` answers a path or None, ``close`` ends it."""

    seen: list[tuple[str, str]] = []
    answer: dict | None = None
    root: Path = Path()

    def __init__(self, corpus_root=None):
        self.cut_now = self.cached = self.empty = 0
        self.failed: dict = {}
        self.closed = False

    def cut(self, accession, html, form):
        FakeCutter.seen.append((accession, form))
        if FakeCutter.answer is None:
            return None
        self.cut_now += 1
        return _answer(FakeCutter.root / f"{accession}.jsonl.gz", FakeCutter.answer)

    def close(self):
        self.closed = True


@pytest.fixture
def edgartools(monkeypatch, tmp_path):
    monkeypatch.setenv(cutter.MODE_ENV, "edgartools")
    FakeCutter.seen, FakeCutter.answer, FakeCutter.root = [], None, tmp_path / "answers"
    monkeypatch.setattr(forms.cutter, "Cutter", FakeCutter)
    return FakeCutter


def test_the_business_row_of_a_10k_is_edgartools_item_1(sec, edgartools):
    edgartools.answer = {"item": "Item 1", "text": BODY, "confidence": 0.95, "detection_method": "toc"}
    _stored(sec)
    check = _cut()
    assert check["result"] != "failed", check.get("note")
    text, method, quality, start = q("SELECT text, method, quality, start_char FROM filing_section "
                                     "WHERE cik = ? AND section = 'business'", MSFT)[0]
    assert (text, method, quality, start) == (BODY, forms.EDGARTOOLS, "ok", None)
    assert q("SELECT DISTINCT rules_version FROM filing_section") == [(sec_sections.FORMS_ROWS_VERSION,)]
    assert [form for _a, form in edgartools.seen] == ["10-K"], "only the annual report goes to the cutter"


def test_a_10k_edgartools_cannot_cut_keeps_our_own_cut(sec, edgartools):
    _stored(sec)
    check = _cut()
    assert check["result"] != "failed", check.get("note")
    text, method = q("SELECT text, method FROM filing_section WHERE cik = ? AND section = 'business'", MSFT)[0]
    assert method == forms.HEADER and "We develop software and cloud services." in text
    assert q("SELECT DISTINCT rules_version FROM filing_section") == [(sec_sections.FORMS_ROWS_VERSION,)]


def test_turning_the_cutter_on_cuts_every_company_again(sec, edgartools, monkeypatch):
    """Rows labelled ``ours-2`` are another version once edgartools is on, so the next run re-cuts them."""
    monkeypatch.setenv(cutter.MODE_ENV, "header")
    _stored(sec)
    _cut()
    assert q("SELECT DISTINCT rules_version FROM filing_section") == [(sec_sections.OURS_2,)]
    monkeypatch.setenv(cutter.MODE_ENV, "edgartools")
    edgartools.answer = {"item": "1", "text": BODY}
    _cut()
    assert q("SELECT DISTINCT rules_version FROM filing_section") == [(sec_sections.FORMS_ROWS_VERSION,)]
    assert q("SELECT method FROM filing_section WHERE cik = ? AND section = 'business'", MSFT) == [
        (forms.EDGARTOOLS,)]
