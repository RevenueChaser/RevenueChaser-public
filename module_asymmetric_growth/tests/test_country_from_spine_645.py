"""The non-US test reads the spine's country, not the SEC address (#645, avo 21 Nov 2026).

``security.country`` is Compustat's own country of the company where the spine links one and the SEC submissions
address only where it does not (spine 10), so the board's non-US test asks the maintained source first. The SEC
header stays the fallback: it changes only when the filer asks, and it is all a name Compustat does not link has.
"""
from __future__ import annotations

import pytest

from RevenueChaser.module_asymmetric_growth import engine

ANNUAL = [{"period_end": "2025-12-31", "revenue": 100.0, "filed": "2026-02-01"}]


def _financials(spine_country, *, is_us=True, sec_country=None):
    meta = {"is_us": is_us, "business_country": sec_country, "entity_name": "A Co"}
    preload = {"edgar": {"T": (ANNUAL, meta)}}
    return engine._cached_financials("T", no_fetch=True, preload=preload, spine_country=spine_country)


def test_the_spine_country_decides_where_it_has_one():
    assert _financials("JP")["info"]["country"] == "Foreign"
    assert _financials("US")["info"]["country"] == engine.US_COUNTRY


def test_the_spine_country_beats_the_sec_address():
    """A company Compustat places abroad whose SEC address is a US office is foreign, and the other way round."""
    assert _financials("JP", sec_country="US")["info"]["country"] == "Foreign"
    assert _financials("US", sec_country="JP")["info"]["country"] == engine.US_COUNTRY


@pytest.mark.parametrize("spine_country", [None, "", "  "])
def test_without_a_spine_country_the_sec_address_still_decides(spine_country):
    assert _financials(spine_country, sec_country="DE")["info"]["country"] == "Foreign"
    assert _financials(spine_country, sec_country="US")["info"]["country"] == engine.US_COUNTRY
    assert _financials(spine_country)["info"]["country"] == engine.US_COUNTRY   # neither places it: US-listed


def test_a_foreign_form_filer_is_foreign_whatever_the_country_says():
    """``is_us`` False is a 20-F / 40-F filer: the form, not the address, and it is not overruled."""
    assert _financials("US", is_us=False)["info"]["country"] == "Foreign"


def test_the_scan_passes_the_universe_rows_country(monkeypatch):
    """``enrich_and_score`` is where the universe row is in hand, so that is where the country comes from."""
    seen = {}

    def spy(ticker, no_fetch=False, preload=None, spine_country=None):
        seen["country"] = spine_country
        return None

    monkeypatch.setattr(engine, "_cached_financials", spy)
    engine.enrich_and_score("T", {"country": "JP", "quote": {}}, no_fetch=True, spine={})
    assert seen["country"] == "JP"
