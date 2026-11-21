"""#1214: the earnings press release as a stored document and a ``release`` section.

What is asked here is the three steps the rule needs before it can read a word: which filing the release belongs
to, which file in it is the release, and that the cut and the board reader hand back the previous quarter's text
and never the one being scored.

The rule's own scoring (``rule8_sentiment``) is not asked here: it has its own tests, and this change does not
touch it.
"""
from __future__ import annotations

from datetime import date

import pytest

from RevenueChaser.core.providers import sec_edgar
from RevenueChaser.module_earnings_radar import store_reads
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.fundamentals import filings
from RevenueChaser.rcdata.build.sec_forms import forms

from . import fund_fixture as fx


# ── which file in the filing is the release ─────────────────────────────────────────────────────────────────────

def test_the_exhibit_is_found_by_its_type_through_edgars_escaped_tags():
    """EDGAR serves the header file with its SGML tags HTML-escaped. Measured on the 22 filings of #1214: a raw
    regex over those tags matched 0 of 22, ``html.unescape`` matched 21."""
    assert filings.release_exhibit(fx.index_headers()) == fx.RELEASE_EXHIBIT


def test_a_release_whose_name_says_nothing_is_still_found():
    """The fixture's exhibit is named ``msft-q1-results.htm``: matching ``ex99`` in the file name found only 14 of
    those same 22 filings, so a name filter would lose this one."""
    assert "ex99" not in fx.RELEASE_EXHIBIT
    assert filings.release_exhibit(fx.index_headers("whatever-we-call-it.htm")) == "whatever-we-call-it.htm"


def test_an_exhibit_of_another_type_is_not_the_release():
    assert filings.release_exhibit(fx.index_headers(kind="EX-10.1")) is None


def test_a_release_filed_as_a_pdf_is_a_miss_and_not_a_stored_binary():
    assert filings.release_exhibit(fx.index_headers("q1-results.pdf")) is None


def test_no_header_file_text_is_no_exhibit():
    assert filings.release_exhibit("") is None


# ── which filing the release belongs to ─────────────────────────────────────────────────────────────────────────

def _row(accession: str, form: str, filed: str, items: str) -> dict:
    return {"accession": accession, "form": form, "filing_date": filed, "items": items,
            "primary_document": "x.htm"}


def test_the_newest_8k_carrying_item_2_02_is_the_release_filing():
    rows = [_row("a", "8-K", "2025-07-29", "2.02,9.01"), _row("b", "8-K", "2025-10-29", "2.02,9.01"),
            _row("c", "8-K", "2025-11-03", "5.02")]
    assert filings.pick_release(rows)["accession"] == "b"


def test_an_8k_with_no_item_2_02_is_not_a_release():
    assert filings.pick_release([_row("a", "8-K", "2025-10-29", "7.01,9.01")]) is None


def test_an_item_number_that_only_contains_2_02_is_not_item_2_02():
    assert filings.pick_release([_row("a", "8-K", "2025-10-29", "12.02")]) is None


def test_an_amendment_never_counts():
    assert filings.pick_release([_row("a", "8-K/A", "2025-10-29", "2.02")]) is None


# ── the cut ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_release_is_one_uncut_section_of_its_own():
    rows = forms.sections_of(fx.press_release(), "8-K", release=True)
    assert [r[0] for r in rows] == [forms.RELEASE]
    section, text, quality, method, start, end = rows[0]
    assert "Revenue grew 18%" in text
    assert (method, start, end) == (forms.UNCUT, None, None)
    assert quality in ("ok", "short")          # the filer's own length, never ours


def test_a_release_is_not_cut_as_an_annual_reports_sections():
    """``whole`` and ``business`` are an annual report's rows; an 8-K has neither, and reading one as if it did
    would put a press release into the corpus Value Chain and Relatedness read."""
    assert forms.BUSINESS not in {r[0] for r in forms.sections_of(fx.press_release(), "8-K", release=True)}
    assert forms.WHOLE not in {r[0] for r in forms.sections_of(fx.press_release(), "8-K", release=True)}


# ── the fetch, end to end over the build ────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sec(monkeypatch, http_mock):
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec_edgar, "SEC_DATA_BASE", "https://data.sec.test")
    fx.spine()
    return http_mock


def test_the_backfill_stores_the_release_exhibit_of_the_8k_that_carries_item_2_02(sec):
    fx.filing_routes(sec, {"789019": fx.submissions(789019, fx.MSFT_FILINGS, "MICROSOFT CORP")},
                     {"msft-10k.htm": fx.ten_k(), "msft-def14a.htm": fx.proxy()})
    check = fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert check["result"] == "changed", check["note"]
    stored = filings.stored_release("789019", fx.EIGHT_K)
    assert stored is not None and stored.exists(), "the release exhibit is not stored"
    assert "Revenue grew 18%" in base.read_raw(stored).decode("utf-8", "replace")


def test_the_release_is_fetched_once_and_not_again_on_the_next_run(sec):
    fx.filing_routes(sec, {"789019": fx.submissions(789019, fx.MSFT_FILINGS, "MICROSOFT CORP")},
                     {"msft-10k.htm": fx.ten_k(), "msft-def14a.htm": fx.proxy()})
    fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert len(sec.calls(fx.RELEASE_EXHIBIT)) == 1, "the release exhibit was not fetched exactly once"
    fx.run(filings.NAME, mode="backfill", to="2026-10-29")
    assert len(sec.calls(fx.RELEASE_EXHIBIT)) == 1, "the stored file is not the resume marker"


# ── the board's reader ──────────────────────────────────────────────────────────────────────────────────────────

def _reader(monkeypatch, rows, companies=(("MSFT", "789019"),)):
    monkeypatch.setattr(store_reads.read, "fundamental_companies",
                        lambda tickers: [{"ticker": t, "cik": c} for t, c in companies])
    monkeypatch.setattr(store_reads.read, "form_release", lambda ciks, text=True: rows)


def _release(cik="789019", filed=date(2025, 10, 29), text="Revenue grew 18%.") -> dict:
    return {"cik": cik, "accession": fx.EIGHT_K, "document": fx.RELEASE_EXHIBIT, "filing_date": filed,
            "text": text, "chars": len(text)}


def test_the_reader_hands_back_the_release_of_the_quarter_already_reported(monkeypatch):
    _reader(monkeypatch, [_release()])
    out, note = store_reads.release_texts(["MSFT"], report_dates={"MSFT": date(2026, 1, 27)},
                                          today=date(2026, 1, 20))
    assert out["MSFT"]["text"] == "Revenue grew 18%."
    assert note["stored"] is True and note["source_as_of"] == "2025-10-29"


def test_a_release_filed_on_the_report_day_is_the_print_itself_and_is_dropped(monkeypatch):
    """The board scores before the print. On the morning of a report the newest release is that print's, and
    reading it would hand the rule the answer it exists to anticipate."""
    _reader(monkeypatch, [_release(filed=date(2026, 1, 27))])
    out, note = store_reads.release_texts(["MSFT"], report_dates={"MSFT": date(2026, 1, 27)},
                                          today=date(2026, 1, 27))
    assert out == {}
    assert note["stored"] is False and "not before the report" in note["label"]


def test_a_release_older_than_the_window_is_not_last_quarters(monkeypatch):
    _reader(monkeypatch, [_release(filed=date(2025, 1, 2))])
    out, note = store_reads.release_texts(["MSFT"], report_dates={"MSFT": date(2026, 1, 27)},
                                          today=date(2026, 1, 20))
    assert out == {}
    assert str(store_reads.RELEASE_MAX_AGE_DAYS) in note["label"]


def test_a_name_with_no_release_is_absent_rather_than_empty_text(monkeypatch):
    _reader(monkeypatch, [])
    out, note = store_reads.release_texts(["MSFT"], report_dates={"MSFT": date(2026, 1, 27)},
                                          today=date(2026, 1, 20))
    assert out == {} and note["stored"] is False


def test_a_store_error_is_not_stored_and_never_raises(monkeypatch):
    def boom(tickers):
        raise RuntimeError("serving file is gone")
    monkeypatch.setattr(store_reads.read, "fundamental_companies", boom)
    out, note = store_reads.release_texts(["MSFT"])
    assert out == {} and note["stored"] is False and "RuntimeError" in note["label"]
