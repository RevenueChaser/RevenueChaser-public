"""#105 period matching: an annual fact whose ``fp`` carries a quarter instead of ``FY``.

``fp`` in companyfacts is the fiscal period of the *filing*, not of the fact. The annual pass reads
``fp: "FY"`` facts, and nine filers of the 2026-10-23 gap measurement tag ``us-gaap:Revenues`` for their
newest year on a 10-K that stamps a quarter there, so the year was never read.

The rule under test: such a fact may only **add** a year that no tag reports under ``fp: "FY"`` -- it never
replaces a year, never changes a value the current pick holds -- and only from an annual report form, so a
10-Q's cumulative figure can never enter an annual series.

Synthetic companfacts only, no network.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

from RevenueChaser.core.providers import sec_edgar as se

REV = "Revenues"
RFC = "RevenueFromContractWithCustomerExcludingAssessedTax"


def _flow(end: str, val: float, *, fp: str = "FY", form: str = "10-K", days: int = 364,
          filed: str | None = None) -> dict:
    start = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    return {"start": start, "end": end, "val": val, "form": form, "fp": fp,
            "filed": filed or f"{int(end[:4]) + 1}-03-01"}


def _facts(series: dict[str, list[dict]]) -> dict:
    return {"entityName": "Synthetic Co",
            "facts": {"us-gaap": {c: {"units": {"USD": facts}} for c, facts in series.items()}}}


def _revenue(facts: dict) -> dict[str, float]:
    return {r["fiscal_year"]: r["revenue"] for r in se.extract_annual(facts) if r.get("revenue") is not None}


def test_a_10k_annual_fact_stamped_with_a_quarter_is_read():
    """The nine filers' shape: every annual Revenues fact carries ``fp: "Q4"`` on its 10-K."""
    facts = _facts({REV: [_flow("2023-12-31", 1_000.0, fp="Q4"), _flow("2024-12-31", 1_100.0, fp="Q4")]})
    assert _revenue(facts) == {"2023": 1_000.0, "2024": 1_100.0}


def test_it_only_fills_a_year_no_fy_fact_reports():
    """2024 is tagged both ways; the ``fp: "FY"`` value wins and the quarter-stamped one adds 2023 only."""
    facts = _facts({REV: [_flow("2023-12-31", 1_000.0, fp="Q4"),
                          _flow("2024-12-31", 9_999.0, fp="Q4"),
                          _flow("2024-12-31", 1_100.0)]})
    assert _revenue(facts) == {"2023": 1_000.0, "2024": 1_100.0}


def test_it_never_takes_a_year_from_another_tag():
    """A year the merge already filled from a second tag is not replaced either (#246, #435)."""
    rev = [_flow("2024-12-31", 1_100.0)]
    rfc = [_flow("2023-12-31", 1_000.0)]
    before = _revenue(_facts({REV: list(rev), RFC: list(rfc)}))
    quarter_stamped = [_flow("2023-12-31", 9_999.0, fp="Q2"), _flow("2024-12-31", 9_999.0, fp="Q2")]
    after = _revenue(_facts({REV: quarter_stamped + rev, RFC: list(rfc)}))
    assert after == before == {"2023": 1_000.0, "2024": 1_100.0}


def test_a_quarterly_form_is_never_read_as_an_annual_fact():
    """A 12-month figure a 10-Q repeats is not an annual statement: the year stays blank."""
    facts = _facts({REV: [_flow("2024-12-31", 1_100.0, fp="Q1", form="10-Q")]})
    assert _revenue(facts) == {}


def test_a_short_period_is_still_not_an_annual_fact():
    """The duration filter holds for the new pass too: a quarter on a 10-K is not a year."""
    facts = _facts({REV: [_flow("2024-12-31", 300.0, fp="Q4", days=89)]})
    assert _revenue(facts) == {}


def test_the_newest_filing_of_the_year_wins_among_quarter_stamped_facts():
    facts = _facts({REV: [_flow("2024-12-31", 1_000.0, fp="Q4", filed="2025-03-01"),
                          _flow("2024-12-31", 1_150.0, fp="Q4", filed="2025-08-01")]})
    assert _revenue(facts) == {"2024": 1_150.0}


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_fact_order_does_not_change_the_records(seed):
    """Metamorphic: the same facts shuffled give the same records."""
    items = [_flow("2022-12-31", 900.0, fp="Q4"), _flow("2023-12-31", 1_000.0), _flow("2024-12-31", 1_100.0, fp="Q3")]
    first = _revenue(_facts({REV: list(items)}))
    random.Random(seed).shuffle(items)
    assert _revenue(_facts({REV: items})) == first == {"2022": 900.0, "2023": 1_000.0, "2024": 1_100.0}


def test_the_filer_is_typed_from_the_form_when_fp_carries_a_quarter():
    """#878: such a filer was typed ``None``; the form it filed on is the same evidence."""
    assert se._is_us_filer(_facts({REV: [_flow("2024-12-31", 1_100.0, fp="Q4")]})) is True
    assert se._is_us_filer(_facts({REV: [_flow("2024-12-31", 1_100.0, fp="Q4", form="20-F")]})) is False
    assert se._is_us_filer(_facts({REV: [_flow("2024-12-31", 1_100.0, fp="Q1", form="10-Q")]})) is None


def test_a_record_of_a_quarter_stamped_year_carries_its_provenance():
    rec, = se.extract_annual(_facts({REV: [_flow("2024-12-31", 1_100.0, fp="Q4", filed="2025-03-01")]}))
    assert rec["revenue"] == 1_100.0
    assert rec["period_ends"]["revenue"] == "2024-12-31"
