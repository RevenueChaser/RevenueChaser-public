"""Plan 2026-11-16 decision B (avo, 17 Nov 2026): an ADR's market cap is the issuer's and ignores the depositary
ratio (BP: $718B, P/E 13,050), so its P/E and P/B are unknown ("–") until the WRDS ADR ratio arrives, and the row
says it is an ADR so the card can mark it."""
from __future__ import annotations

import pytest

from RevenueChaser.core import universe
from RevenueChaser.module_fundamentals import pipeline
from RevenueChaser.module_fundamentals.report import render_fundamental_dashboard
from RevenueChaser.module_fundamentals.tests.test_fundamentals_w3_386 import _annual_pair, _patch_row


def _row(monkeypatch, security_type):
    annual = _annual_pair()
    annual[-1]["total_equity"] = 50.0
    _patch_row(monkeypatch, annual)
    return pipeline._compute_row({"ticker": "T", "market_cap": 1000.0, "security_type": security_type}, None,
                                 spine={}, drops=[])


def test_an_adr_has_no_pe_or_pb_and_says_it_is_an_adr(monkeypatch):
    row = _row(monkeypatch, "adr")
    assert row["adr"] is True
    assert row["metrics"]["pe"] is None and row["metrics"]["pb"] is None


def test_a_common_stock_keeps_its_pb(monkeypatch):
    row = _row(monkeypatch, "common")
    assert row["adr"] is False
    assert row["metrics"]["pb"] == pytest.approx(1000.0 / 50.0)


def test_the_universe_rows_carry_the_security_type(monkeypatch):
    monkeypatch.setattr(universe, "_spine_universe", lambda: [{"ticker": "BP", "security_type": "adr"}])
    assert universe.load_cached_universe()[0]["security_type"] == "adr"


def test_the_card_marks_an_adr():
    html = render_fundamental_dashboard(pipeline.build_payload([], run_stats={}))
    assert "adr-warn" in html and "P/E – P/B –" not in html         # avo F1: P/E and P/B left the card
