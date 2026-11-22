"""Financials reads the tax provision, pre-tax income and interest expense from the layer (#645 G1, avo 10 Nov 2026).

Those three lines were Yahoo's alone, so every run on the SEC's statements took a flat 21% tax rate and showed no
interest cover, and the Source line said both were "not in the facts". The builder serves all three concepts
(``IncomeTaxExpenseBenefit``, the pre-tax ladder, the interest ladder; ``rcdata/build/fundamentals/facts``), so the
effective tax rate and the interest cover are the filer's own figures and the Source line names only ITS gaps.
"""
from __future__ import annotations

import revenuechaser.module_financials.run as fm
from revenuechaser.module_financials.engines._inputs import PE_ONLY_SECTOR, effective_tax_rate


def _year(year: str, **over) -> dict:
    """One layer annual record, in ``core/fundamentals_layer._annual_records``' shape (the layer's field names)."""
    rec = {"fiscal_year": year, "revenue": 1_000.0, "ebit": 200.0, "depreciation": 20.0, "capex": 30.0,
           "income_tax_expense": 50.0, "pretax_income": 200.0, "interest_expense": 15.0,
           "period_ends": {"revenue": f"{year}-12-31"}}
    rec.update(over)
    return rec


# ── the record ────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_layers_income_tax_expense_is_read_as_the_engines_tax_provision():
    row = fm._financials_record(_year("2025"))
    assert row["tax_provision"] == 50.0                     # the engines' name, the layer's ``income_tax_expense``
    assert row["pretax_income"] == 200.0 and row["interest_expense"] == 15.0
    assert "income_tax_expense" not in row                  # the layer's own name never reaches an engine
    # A filer that tags none of them still gets an empty record, so the engines' labelled defaults show (review S1).
    bare = fm._financials_record({"fiscal_year": "2025", "revenue": 1_000.0,
                                  "period_ends": {"revenue": "2025-12-31"}})
    for field in ("tax_provision", "pretax_income", "interest_expense"):
        assert field not in bare


def test_the_tax_rate_is_now_the_filers_own_and_not_the_flat_default():
    years = [fm._financials_record(_year(y)) for y in ("2023", "2024", "2025")]
    rate, source = effective_tax_rate({}, years[-1], "Information Technology", years)
    assert rate == 50.0 / 200.0 and source.startswith("statements")   # 25%, the filer's, not the 21% default
    from revenuechaser.module_financials.config import DEFAULT_TAX_RATE
    assert rate != DEFAULT_TAX_RATE


# ── what the Source line still calls a default ────────────────────────────────────────────────────────────────

def test_a_filer_with_both_lines_has_no_tax_or_interest_gap():
    years = [fm._financials_record(_year(y)) for y in ("2024", "2025")]
    assert fm._tax_and_interest_gaps(years) == []


def test_a_filer_without_them_still_names_both():
    bare = [fm._financials_record({"fiscal_year": "2025", "revenue": 1_000.0,
                                   "period_ends": {"revenue": "2025-12-31"}})]
    assert fm._tax_and_interest_gaps(bare) == ["tax rate", "interest expense"]


def test_an_unbelievable_ratio_is_a_tax_gap_but_a_tagged_interest_line_is_not():
    # A tax benefit (a negative provision) is outside the believable band, so the DCF still takes its default.
    years = [fm._financials_record(_year("2025", income_tax_expense=-30.0))]
    assert fm._tax_and_interest_gaps(years) == ["tax rate"]


def test_a_bank_reads_neither_so_it_has_no_gap():
    bare = [fm._financials_record({"fiscal_year": "2025", "revenue": 1_000.0,
                                   "period_ends": {"revenue": "2025-12-31"}})]
    assert fm._tax_and_interest_gaps(bare, bank=True) == []
    assert PE_ONLY_SECTOR                                   # the sector the caller passes ``bank=True`` for


def test_the_three_fields_are_part_of_the_sec_field_list():
    assert {"tax_provision", "pretax_income", "interest_expense"} <= set(fm._SEC_FIELDS)
    assert not hasattr(fm, "NOT_IN_FACTS")                  # no constant gap list any more
