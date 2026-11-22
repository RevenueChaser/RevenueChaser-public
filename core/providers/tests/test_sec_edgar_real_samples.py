"""sec_edgar.extract_annual on real, trimmed SEC companyfacts (#896 step 3).

The other tests here build their facts by hand, so they test the author's idea of the format. These four files are
real filings (fixtures/sec_companyfacts/, each with its `_what` and `_how_to_recapture`): a September fiscal year
(AAPL), a June one (MSFT), a 52/53-week year ending in January (NVDA) and a bank (JPM). The expected numbers are
the ones printed in each company's 10-K, written by hand, never captured from this code. The metamorphic checks
need no expected value: the same facts in another order, or with a concept the code does not read, give the same
records.
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path

import pytest

from revenuechaser.core.providers import sec_edgar as se

_DIR = Path(__file__).parent / "fixtures" / "sec_companyfacts"
_B = 1e9

# ticker -> fiscal year end -> field -> value from the 10-K (USD).
_FROM_THE_10K = {
    "aapl": {
        "2024-09-28": {"revenue": 391.035 * _B, "net_income": 93.736 * _B, "total_assets": 364.980 * _B,
                       "capex": 9.447 * _B},
        "2023-09-30": {"revenue": 383.285 * _B, "net_income": 96.995 * _B, "total_assets": 352.583 * _B},
    },
    "msft": {
        "2024-06-30": {"revenue": 245.122 * _B, "net_income": 88.136 * _B, "total_assets": 512.163 * _B},
        "2023-06-30": {"revenue": 211.915 * _B, "net_income": 72.361 * _B},
    },
    "nvda": {
        "2025-01-26": {"revenue": 130.497 * _B, "net_income": 72.880 * _B, "total_assets": 111.601 * _B},
        "2024-01-28": {"revenue": 60.922 * _B, "net_income": 29.760 * _B},
    },
    "jpm": {
        "2024-12-31": {"revenue_net_of_interest_expense": 177.556 * _B, "net_income": 58.471 * _B,
                       "total_assets": 4002.814 * _B},
        "2023-12-31": {"net_income": 49.552 * _B},
    },
}


def _facts(name: str) -> dict:
    return json.loads((_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _year_ending(annual: list[dict], end: str) -> dict:
    hits = [r for r in annual if end in r["period_ends"].values()]
    assert len(hits) == 1, f"{len(hits)} records end on {end}: {[r['fiscal_year'] for r in annual]}"
    return hits[0]


@pytest.mark.parametrize("name", sorted(_FROM_THE_10K))
def test_the_annual_records_carry_the_numbers_the_10k_prints(name):
    annual = se.extract_annual(_facts(name))
    for end, fields in _FROM_THE_10K[name].items():
        rec = _year_ending(annual, end)
        for field, want in fields.items():
            assert rec.get(field) == pytest.approx(want), (name, end, field)
            if field not in se._OMIT_WHEN_ABSENT:  # the bank top line is kept out of period_ends on purpose
                assert rec["period_ends"].get(field) == end, (name, end, field)


@pytest.mark.parametrize("name", sorted(_FROM_THE_10K))
def test_every_sample_reads_as_a_us_filer(name):
    assert se._is_us_filer(_facts(name)) is True


@pytest.mark.parametrize("name", sorted(_FROM_THE_10K))
def test_the_order_of_the_facts_does_not_change_the_records(name):
    facts = _facts(name)
    shuffled = copy.deepcopy(facts)
    rng = random.Random(896)
    for body in shuffled["facts"]["us-gaap"].values():
        for items in body["units"].values():
            rng.shuffle(items)
    assert se.extract_annual(shuffled) == se.extract_annual(facts)


@pytest.mark.parametrize("name", sorted(_FROM_THE_10K))
def test_a_concept_the_code_does_not_read_changes_nothing(name):
    facts = _facts(name)
    noisy = copy.deepcopy(facts)
    noisy["facts"]["us-gaap"]["AdvertisingExpense"] = {"units": {"USD": [
        {"start": "2023-01-01", "end": "2023-12-31", "val": 1.0, "form": "10-K", "fp": "FY", "filed": "2024-02-01"}]}}
    assert "AdvertisingExpense" not in {c for concepts, _unit in se.CONCEPTS.values() for c in concepts}
    assert se.extract_annual(noisy) == se.extract_annual(facts)
