"""The yfinance fake, observed end to end.

The fake counts calls in ``_CALLS``, but that list lives inside the dashboard
**subprocess** — the test process can never read it. S2 closes that hole with a
call log file (``$RC_E2E_YF_LOG``), so "this Fetch touched Yahoo" and "this
store-only view did not" become assertable from the outside.

This file also pins the ``fast_info`` contract the fake must honour for Phase B:
``.shares`` / ``.last_price`` come from the fixture, and ``.market_cap`` raises,
because real yfinance silently falls back to ``Ticker.info`` (a network call) for
it.
"""
from __future__ import annotations

from RevenueChaser.rcdata.tests import universe_store
import pytest

from .harness import yfinance_fake


class TestFastInfoContract:
    """What Phase B reads, and the one attribute it must never read."""

    def test_shares_and_last_price_come_from_the_fixture(self):
        fi = yfinance_fake.FakeTicker("MU").fast_info
        assert fi.shares == pytest.approx(1.12e9)
        assert fi.last_price == pytest.approx(110.0)

    def test_market_cap_raises_instead_of_falling_back_to_info(self):
        with pytest.raises(AssertionError):
            _ = yfinance_fake.FakeTicker("MU").fast_info.market_cap

    def test_a_ticker_without_fast_info_yields_no_numbers(self):
        fi = yfinance_fake.FakeTicker("NOCAP").fast_info
        assert fi.shares is None
        assert fi.last_price is None


