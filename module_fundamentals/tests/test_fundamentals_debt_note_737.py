"""#737: the Fundamentals board reads the SEC service's ``debt.note`` answer when the facts give no total debt.

avo, 16 Nov 2026 (decisions 4-7): a note figure decides the gate and is labelled; filed > note > inferred; "no
borrowings stated" never becomes 0; finance leases are left out; a non-USD note is not used. The guards are
``module_fundamentals.debt.note_debt``: the note's balance date is the year's balance sheet date, and the total is
not below a debt line the filer tagged nor above its total assets.
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import fundamentals_layer as layer
from RevenueChaser.module_fundamentals import config, debt, pipeline
from RevenueChaser.module_fundamentals.screeners import NOTE_DEBT_NOTE, evaluate_quality
from RevenueChaser.module_fundamentals.tests.test_fundamentals_debt_free_737 import _fy, _ttm_pair
from RevenueChaser.rcdata import read, sec_debt_note

FLOWS = {"revenue": 1000.0, "gross_profit": 750.0, "ebit": 200.0, "depreciation": 50.0}
# A borrower whose facts sum no total: a current line only (40) and interest above the floor.
YEAR = {"cash": 600.0, "total_equity": 900.0, "total_assets": 5000.0, "lt_debt_current": 40.0,
        "interest_expense": 300_000.0}


def note(**over) -> dict:
    return {"status": "stated", "balance_date": "2025-12-31", "currency": "USD", "total_usd": 800.0, **over}


def year(**over) -> list[dict]:
    return [_fy(2025, FLOWS, {**YEAR, **over})]


def test_a_note_total_fills_the_years_debt_with_basis_note():
    q = pipeline._quality_metrics(year(), debt_note=note())
    assert q["debt_basis"] == debt.NOTE and q["quality_basis"] == "FY"
    assert q["net_debt_ebitda"] == pytest.approx((800.0 - 600.0) / 250.0)
    assert q["roic"] == pytest.approx(200.0 * (1 - config.TAX_RATE) / (800.0 + 900.0 - 600.0))


def test_without_a_note_the_same_borrower_stays_unknown():
    q = pipeline._quality_metrics(year())
    assert q["debt_basis"] is None and q["net_debt_ebitda"] is None


def test_a_filed_total_wins_over_the_note():
    q = pipeline._quality_metrics(year(total_debt=100.0), debt_note=note())
    assert q["debt_basis"] == debt.FILED and q["net_cash"] is True


def test_the_note_wins_over_the_inference():
    """A filer that tags nothing and pays no interest would be read as 0; its note says otherwise."""
    rec = [_fy(2025, FLOWS, {"cash": 600.0, "total_equity": 900.0, "total_assets": 5000.0})]
    assert pipeline._quality_metrics(rec)["debt_basis"] == debt.INFERRED_NONE
    assert pipeline._quality_metrics(rec, debt_note=note())["debt_basis"] == debt.NOTE


@pytest.mark.parametrize("bad", [
    note(total_usd=None),                       # none_stated, or a non-USD note: never 0
    note(total_usd=0.0),
    note(balance_date="2024-12-31"),            # another year's column
    note(balance_date="not a day"),
    note(total_usd=30.0),                       # below the current line the filer tagged
    note(total_usd=6000.0),                     # above total assets
])
def test_a_note_that_fails_a_guard_is_not_used(bad):
    assert debt.note_debt(year()[0], bad) is None
    assert pipeline._quality_metrics(year(), debt_note=bad)["debt_basis"] is None


def test_a_52_53_week_year_end_a_few_days_off_still_matches():
    assert debt.note_debt(year()[0], note(balance_date="2025-12-27")) == 800.0


def test_the_trailing_year_falls_back_to_the_year_the_note_belongs_to():
    annual, quarterly = _ttm_pair(year_over={"lt_debt_current": 40.0, "total_assets": 5000.0})
    q = pipeline._quality_metrics(annual, quarterly, debt_note=note())
    assert q["quality_basis"] == "FY" and q["debt_basis"] == debt.NOTE


def test_the_leverage_rule_says_the_debt_came_from_the_note():
    q = pipeline._quality_metrics(year(), debt_note=note())
    gate = evaluate_quality({"net_debt_ebitda": q["net_debt_ebitda"], "net_cash": q["net_cash"], "roic": q["roic"],
                             "debt_basis": q["debt_basis"]})
    labels = {r["id"]: r["label"] for r in gate["rules"]}
    assert NOTE_DEBT_NOTE in labels["net_debt_ebitda"]


def test_the_layer_hands_the_board_only_ok_answers_of_the_current_prompt(monkeypatch):
    rows = [{"cik": "1", "status": "ok", "prompt_version": sec_debt_note.PROMPT_VERSION, "accession": "a1",
             "answer": {"total_usd": 5.0}},
            {"cik": "2", "status": "partial", "prompt_version": sec_debt_note.PROMPT_VERSION, "answer": {}},
            {"cik": "3", "status": "ok", "prompt_version": "debt.note-0", "answer": {"total_usd": 1.0}}]
    monkeypatch.setattr(read, "sec_reads", lambda ciks, question: rows if question == "debt.note" else [])
    assert layer._debt_notes({"1", "2", "3"}) == {"1": {"total_usd": 5.0, "accession": "a1"}}
