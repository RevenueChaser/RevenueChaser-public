"""#385 M-FIN-2: the Financials board says what it assumed (FIN-2/DF41, FIN-9 B, FIN-10, #255 wording).

Text only: no number moves. No network.
"""
from __future__ import annotations

import copy

from revenuechaser.module_financials.engines.credit_capacity_engine import run_credit_capacity
from revenuechaser.module_financials.engines.dcf_engine import run_dcf
from revenuechaser.module_financials.engines.three_statement_engine import run_three_statement
from revenuechaser.module_financials.reporting.html_builder import build_report_html

DNA_WARNING = "D&A: assumed 0 (not reported)"


def _without_dna(financials):
    f = copy.deepcopy(financials)
    f["annual"][-1]["depreciation"] = None
    return f


def _html(financials, modules, warnings=()):
    return build_report_html({"ticker": "TEST", "financials": financials, "modules": modules,
                              "warnings": list(warnings)})


# ── FIN-2 / DF41: missing D&A is assumed 0, and the board says so ─────────────
def test_dcf_warns_when_dna_is_missing(financials):
    res = run_dcf(_without_dna(financials))
    assert DNA_WARNING in res["warnings"]
    assert res["base_year"]["dep_pct_rev"] == 0.0          # the number is unchanged: only the label is new


def test_dcf_has_no_dna_warning_when_dna_is_reported(financials):
    assert DNA_WARNING not in run_dcf(financials)["warnings"]


def test_dcf_reported_zero_dna_is_not_an_assumption(financials):
    f = copy.deepcopy(financials)
    f["annual"][-1]["depreciation"] = 0.0
    assert DNA_WARNING not in run_dcf(f)["warnings"]


def test_three_statement_warns_when_dna_is_missing(financials):
    assert DNA_WARNING in run_three_statement(_without_dna(financials))["warnings"]


def test_three_statement_has_no_dna_warning_when_dna_is_reported(financials):
    assert DNA_WARNING not in run_three_statement(financials)["warnings"]


def test_three_statement_user_dna_rate_is_not_an_assumed_zero(financials):
    res = run_three_statement(_without_dna(financials), {"depreciation_pct_rev": 0.04})
    assert DNA_WARNING not in res["warnings"]


# ── FIN-9 option B / FIN-3: the tax rate row says when it is the default ─────
def _without_statement_tax(financials):
    """The statements carry no tax basis: no stored rate, no provision / pretax pair."""
    f = copy.deepcopy(financials)
    for rec in f["annual"]:
        for key in ("tax_rate", "pretax_income", "tax_provision"):
            rec.pop(key, None)
    return f


def test_dcf_tax_rate_is_marked_default(financials):
    res = run_dcf(_without_statement_tax(financials))
    assert res["assumptions"]["tax_rate_source"] == "default"
    assert res["assumptions"]["tax_rate"] == 0.21


def test_dcf_tax_rate_from_an_assumption_is_not_default(financials):
    res = run_dcf(financials, {"tax_rate": 0.25})
    assert res["assumptions"]["tax_rate_source"] == "assumption"


def test_three_statement_tax_rate_source(financials):
    assert run_three_statement(_without_statement_tax(financials))["assumptions"]["tax_rate_source"] == "default"
    assert run_three_statement(financials, {"tax_rate": 0.3})["assumptions"]["tax_rate_source"] == "assumption"


def test_report_shows_default_tax_rate_row(financials):
    f = _without_statement_tax(financials)
    html = _html(f, {"dcf": run_dcf(f), "three_statement": run_three_statement(f)})
    # The DCF WACC panel and the 3-statement panel. No sector band carries a rate, so the row says so rather
    # than implying a sector-specific one (review S-2, _inputs.default_tax_rate).
    assert html.count("default 21.0% (no sector rate)") == 2


def test_report_shows_a_measured_tax_rate_without_default(financials):
    """The common case since FIN-3: the rate came from the statements, so the row carries no "default" word.

    The fixture's three years report 40/190, 45/215 and 50/240, so both panels read their median and say how
    many years it rests on (#89; it was the latest year's 20.8% alone).
    """
    html = _html(financials, {"dcf": run_dcf(financials), "three_statement": run_three_statement(financials)})
    # The tax rows only: since review S2 the rate rows (risk-free, premium, cost of debt) say "default" here.
    assert "default 21.0%" not in html and "(no sector rate)" not in html
    # The DCF WACC panel and the 3-statement panel, each naming the years behind the rate.
    assert html.count("20.9% (median of 3 years)") == 2
    assert "20.8%" not in html


def test_report_shows_an_assumed_tax_rate_without_default(financials):
    a = {"tax_rate": 0.25}
    html = _html(financials, {"dcf": run_dcf(financials, a), "three_statement": run_three_statement(financials, a)})
    assert "default 21.0%" not in html and "25.0%" in html


# ── FIN-10: the top bar reads "Last sync … EOD" ─────────────────────────────
def test_top_bar_reads_last_sync_eod(financials):
    financials["_fetched_at_iso"] = "2026-09-02T08:00:00+00:00"
    html = _html(financials, {})
    # 08:00 UTC is 04:00 in New York, before the open: the data is Tuesday's close (Financials review S4).
    assert "Last sync: Tuesday, September 01, 2026 EOD" in html
    assert "Data as of" not in html


def test_top_bar_without_a_stamp_says_n_a_without_eod(financials):
    financials.pop("_fetched_at_iso", None)
    html = _html(financials, {})
    assert "Last sync: N/A<" in html and "N/A EOD" not in html


# ── #255: the approved credit wording ───────────────────────────────────────
def test_credit_n_m_uses_the_approved_wording(financials):
    f = copy.deepcopy(financials)
    f["annual"][-1]["ebitda"] = -50.0
    html = _html(f, {"credit": run_credit_capacity(f)})
    assert html.count("n/m (negative EBITDA)") == 3
    assert "n/m (EBITDA" not in html


