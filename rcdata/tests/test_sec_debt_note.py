"""The question ``debt.note`` (#737): which note blocks are read, the message, the parse, the scope and the inputs.

No model is called: the parse is fed replies, and the scope and inputs read monkeypatched rows.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from revenuechaser.rcdata import read, sec_debt_note as note
from revenuechaser.rcdata.build.sec_reads import company_profile, debt_note, questions

END = date(2025, 12, 31)


def block(name="DebtDisclosureTextBlock", text="Term loan 500", *, form="10-K", end=END, top=True, seq=1,
          cik="1"):
    return {"cik": cik, "accession": "0001-25-1", "document": "a10k.htm", "form": form, "filing_date": date(2026, 2, 1),
            "local_name": name, "top_level": top, "seq": seq, "period_end": end, "text": text,
            "rules_version": "notes-1"}


def reply(**over) -> str:
    body = {"status": "stated", "balance_date": "2025-12-31", "currency": "USD", "scale": 1_000_000,
            "total_debt": 5442, "long_term": 5000, "current": 442, "finance_leases": None, "basis": "carrying",
            "quote": "Total debt 5,442"}
    return json.dumps({**body, **over})


# ── the parse ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_stated_usd_total_is_scaled_and_finance_leases_are_left_out():
    got = note.parse(reply(finance_leases=42))
    assert got["total_debt"] == 5442 and got["scale"] == 1_000_000
    assert got["total_usd"] == pytest.approx((5442 - 42) * 1e6)


def test_a_fenced_reply_is_read():
    assert note.parse("```json\n" + reply() + "\n```")["total_usd"] == pytest.approx(5442e6)


def test_no_borrowings_is_an_answer_but_never_a_zero():
    got = note.parse(json.dumps({"status": "none_stated"}))
    assert got == {"status": "none_stated", "total_usd": None}
    assert note.parse(json.dumps({"status": "not_in_text"}))["total_usd"] is None


def test_another_currency_is_stored_but_gives_no_usd_total():
    got = note.parse(reply(currency="eur"))
    assert got["currency"] == "EUR" and got["total_debt"] == 5442 and got["total_usd"] is None


@pytest.mark.parametrize("bad", [
    "not json", json.dumps([1]), json.dumps({"status": "maybe"}),
    reply(scale=7), reply(scale=True), reply(balance_date="31/12/2025"), reply(balance_date="2025-02-30"),
    reply(currency="dollars"), reply(total_debt=0), reply(total_debt=-5), reply(total_debt="5442"),
    reply(long_term=4000, current=442), reply(finance_leases=9000),
])
def test_an_unusable_reply_is_none(bad):
    assert note.parse(bad) is None


def test_parts_that_add_up_within_one_percent_are_kept():
    assert note.parse(reply(long_term=5000, current=400)) is not None


def test_a_total_that_is_only_leases_gives_no_usd_total():
    assert note.parse(reply(finance_leases=5442))["total_usd"] is None


# ── the blocks and the message ─────────────────────────────────────────────────────────────────────────────────

def test_an_allowed_disclosure_is_read_and_a_debt_security_is_not():
    rows = [block("AvailableForSaleSecuritiesDebtSecuritiesTextBlock", seq=1), block(seq=3),
            block("ScheduleOfDebtTableTextBlock", seq=4)]
    assert [r["local_name"] for r in note.choose(rows)] == ["DebtDisclosureTextBlock"]


def test_a_table_is_read_only_when_no_disclosure_is_there():
    assert [r["local_name"] for r in note.choose([block("ScheduleOfDebtTableTextBlock")])] == \
        ["ScheduleOfDebtTableTextBlock"]


def test_an_ifrs_borrowings_note_is_read():
    assert note.choose([block("DisclosureOfBorrowingsExplanatory", form="20-F")])


def test_a_40f_a_nested_block_and_a_denied_name_are_never_read():
    assert note.choose([block(form="40-F")]) == []
    assert note.choose([block(top=False)]) == []
    assert note.choose([block("DebtDisclosureTextBlockMaturities")]) == []


def test_a_company_is_skipped_without_one_balance_date_with_two_registrants_or_a_long_note():
    assert note.why_skipped([]) == "no debt note"
    assert note.why_skipped([block(), block("LongTermDebtTextBlock", end=date(2024, 12, 31))]) == \
        "no single balance date"
    assert note.why_skipped([block(end=None)]) == "no single balance date"
    assert note.why_skipped([block(text="A"), block(text="B")]) == "two registrants"
    assert note.why_skipped([block(text="x" * note.MAX_CHARS)]) == "note too long"
    assert note.why_skipped([block(), block()]) is None          # the same text twice is one block


def test_the_message_names_the_balance_date_and_holds_each_block_once():
    msg = note.build_user("ACME", "10-K", [block(), block(), block("LongTermDebtTextBlock", "Notes 300", seq=2)])
    assert msg.startswith("Company: ACME\nForm: 10-K\nBalance sheet date: 2025-12-31\n")
    assert msg.count("Term loan 500") == 1 and "=== LongTermDebtTextBlock ===\nNotes 300" in msg


# ── the question ───────────────────────────────────────────────────────────────────────────────────────────────

def test_debt_note_is_written_by_the_tools_switch_evren_by_default_with_no_cap():
    """avo, 19 Nov 2026: "Fundamentals icinde evren deepseek olmali". The writer follows the tool's one switch, like
    ``company.profile``, so EVREN by default and uncapped (it has no quota); the DeepSeek cap is kept for a process
    that names DeepSeek. The registration and the run order are checked in a fresh interpreter
    (the byte-for-byte comparison with the Relatedness board's own request, gone with that writer in #1520):
    this process's registry is emptied by fixtures."""
    q = debt_note.DEBT_NOTE
    assert (q.provider, q.max_calls, q.prompt_version) == ("evren", None, note.PROMPT_VERSION)
    assert q.provider == questions.PROVIDER == "evren" and q.writer_model == "evren-deepseek-v4.1-flash"
    assert debt_note.MAX_CALLS == 200           # the cap a DeepSeek run still gets
    assert "pro" not in q.writer_model.lower()
    assert note.PROMPT_VERSION in q.system


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr(debt_note, "_ready", lambda: None)
    monkeypatch.setattr(company_profile, "companies", lambda: {
        "1": {"name": "Acme", "sector": "Industrials"}, "2": {"name": "Paid Up", "sector": "Industrials"},
        "3": {"name": "A Bank", "sector": "Financial Services"}, "4": {"name": "No Note", "sector": "Technology"},
        "5": {"name": "Debt Free", "sector": "Technology"}, "6": {"name": "Long Line", "sector": "Technology"},
        "7": {"name": "Small Interest", "sector": "Technology"}})

    def statements(ciks, years, quarters):
        assert (years, quarters) == (1, 0)
        rows = [{"cik": c, "period_type": "annual", "fiscal_year": 2025, "field": "revenue", "value": 1.0}
                for c in ciks]
        rows.append({"cik": "2", "period_type": "annual", "fiscal_year": 2025, "field": "total_debt", "value": 9.0})
        rows.append({"cik": "1", "period_type": "annual", "fiscal_year": 2024, "field": "total_debt", "value": 9.0})
        # Decision 1 (16 Nov 2026): a current line only, or interest above 100,000; a long-term line waits for #830.
        rows += [{"cik": c, "period_type": "annual", "fiscal_year": 2025, "field": f, "value": v} for c, f, v in (
            ("1", "lt_debt_current", 5.0), ("4", "interest_expense", 250_000.0), ("6", "lt_debt", 7.0),
            ("6", "interest_expense", 250_000.0), ("7", "interest_expense", 100_000.0),
            ("3", "lt_debt_current", 5.0))]
        return [r for r in rows if r["cik"] in ciks]

    def notes(ciks=(), local_name=None, kind=None, text=True):
        rows = [block(cik="1", seq=2), block("AvailableForSaleSecuritiesDebtSecuritiesTextBlock", cik="1", seq=1),
                block("SegmentReportingDisclosureTextBlock", cik="4")]
        rows = [r for r in rows if r["cik"] in set(ciks) and (local_name is None or r["local_name"] == local_name)]
        return rows if text else [{k: v for k, v in r.items() if k != "text"} for r in rows]

    monkeypatch.setattr(read, "statements_many", statements)
    monkeypatch.setattr(read, "form_notes", notes)


def test_the_scope_is_decision_1_outside_the_two_sectors(world):
    """avo, 16 Nov 2026 decision 1, kept 24 Nov 2026 (card D2 "A"): no total, and a current line only or interest
    above 100,000. 2 has a total, 3 is a bank, 5 tags nothing and pays nothing (its missing note is the right
    answer), 6 has a long-term line (#830), 7's interest is at the floor; 1's total is an older year's."""
    assert debt_note.scope() == ["1", "4"]


def test_a_short_term_or_fallback_current_line_alone_is_in_scope():
    """Grok r2/r3: CUE tags only ``other_loans_payable_current`` and a filer may tag only ``short_term_bank_loans``;
    neither gives a total, so both are decision 1's "current line only"."""
    for f in ("other_loans_payable_current", "short_term_bank_loans", "short_term_borrowings"):
        assert debt_note._in_scope({"revenue": 1.0, f: 3.0})
    assert not debt_note._in_scope({"revenue": 1.0})
    assert not debt_note._in_scope({"senior_notes_noncurrent": 3.0, "debt_current": 1.0})


def test_an_input_is_the_chosen_note_with_its_filing_and_a_company_without_one_has_none(world):
    got = debt_note.inputs(["1", "4"])
    assert list(got) == ["1"]
    inp = got["1"]
    assert inp.messages == (inp.text,) and "Company: Acme" in inp.text and "Term loan 500" in inp.text
    assert "AvailableForSale" not in inp.text
    assert (inp.accession, inp.form, inp.report_date) == ("0001-25-1", "10-K", END)
    assert inp.kind == "note:DebtDisclosureTextBlock@2025-12-31"
    assert debt_note.DEBT_NOTE.messages(inp) == [inp.text]


def test_prompt_2_says_where_the_scale_is_and_that_every_borrowing_is_summed():
    """avo, 24 Nov 2026 23:49 (card D5 "A"): version 1 read IPGP's "$21,723" in thousands as dollars and CAL's
    revolver as the whole debt (review plan step 4). Version 2 names both rules, so its answers are a new version."""
    assert note.PROMPT_VERSION == "debt.note-2"
    assert "heading or caption" in note.SYSTEM and "EVERY borrowing" in note.SYSTEM
