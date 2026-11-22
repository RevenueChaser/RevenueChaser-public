"""#166 item 3 — what a paid answer costs, and the rule that a paid model always has a figure.

``core/llm_prices.py`` is the only place that prices a call, because the day ledger and the Relatedness board's
per-run ceiling both read it (``module_relatedness.config.EST_USD_PER_CALL``) and two copies would drift.

The number it falls back to is **measured, not published**: the 10 Nov 2026 pilot wrote 400 names in 668 calls for
about 1 USD. These tests pin that provenance (the figure still prices that pilot at about a dollar), the shape of
the ``RC_LLM_PRICES`` override, what happens to a value that cannot be read, and the one rule that keeps money
visible to the cap: a paid writer with no figure would spend USD the gate could never count.
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.core import llm_prices, llm_writers

PAID = "deepseek-v4-flash"


@pytest.fixture(autouse=True)
def _no_env_prices(monkeypatch):
    monkeypatch.delenv(llm_prices.PRICES_ENV, raising=False)


# ── the figure in the code ────────────────────────────────────────────────────────────────────────────────────

def test_every_paid_model_has_a_figure():
    """A paid model with no price spends money the day cap cannot see (``core/llm_spend.py``)."""
    paid = [m for w in llm_writers.WRITERS.values() if w.paid for m in w.models]
    assert paid, "the registry has no paid writer: this rule would pass by being empty"
    for model in paid:
        assert llm_prices.micros(model, calls=1) is not None, f"{model} is paid and has no figure"


def test_the_measured_figure_still_prices_its_own_pilot_at_about_a_dollar():
    """The provenance of 0.0018: 668 calls for about 1 USD (#712, review of PR #557)."""
    usd = llm_prices.micros(PAID, calls=668) / llm_prices.MICROS
    assert 0.9 <= usd <= 1.3
    assert llm_prices.unit(PAID) == "measured cost a call"


def test_the_relatedness_run_ceiling_reads_the_same_number():
    """One source: the per-run cap and the day ledger cost a call alike."""
    from revenuechaser.module_relatedness import config
    assert config.EST_USD_PER_CALL == llm_prices.measured_usd_per_call(PAID)


def test_a_model_nobody_priced_has_no_figure_rather_than_a_zero():
    assert llm_prices.micros("made-up-model", calls=10) is None
    assert llm_prices.measured_usd_per_call("made-up-model") is None
    assert llm_prices.unit("made-up-model") == "no price"


def test_the_measured_figure_counts_calls_and_ignores_the_tokens():
    """Without a per-token price the tokens cannot be costed; they are still recorded by the ledger."""
    assert llm_prices.micros(PAID, calls=2, tokens_in=10_000, tokens_out=9_999) == \
        llm_prices.micros(PAID, calls=2)


# ── the published price, when the box is told one ─────────────────────────────────────────────────────────────

def test_a_published_per_token_price_wins_over_the_measured_one(monkeypatch):
    monkeypatch.setenv(llm_prices.PRICES_ENV, json.dumps({PAID: [0.28, 0.42]}))
    # 1,000 in at 0.28/Mtok and 500 out at 0.42/Mtok = 0.00028 + 0.00021 USD = 490 micros.
    assert llm_prices.micros(PAID, calls=1, tokens_in=1000, tokens_out=500) == 490
    assert llm_prices.unit(PAID) == "published per-token price"


def test_a_published_price_is_read_at_call_time(monkeypatch):
    """A changed variable must not need a restart (``rcdata.caps`` and the other gates read theirs the same way)."""
    assert llm_prices.per_mtok(PAID) is None
    monkeypatch.setenv(llm_prices.PRICES_ENV, json.dumps({PAID: [1.0, 2.0]}))
    assert llm_prices.per_mtok(PAID) == (1.0, 2.0)


def test_a_priced_model_with_no_reported_tokens_falls_back_to_the_call(monkeypatch):
    """A gate that reports no usage would otherwise cost 0 and hide a paid call from the cap."""
    monkeypatch.setenv(llm_prices.PRICES_ENV, json.dumps({PAID: [0.28, 0.42]}))
    assert llm_prices.micros(PAID, calls=1) == llm_prices.micros(PAID, calls=1, tokens_in=0, tokens_out=0)
    monkeypatch.delenv(llm_prices.PRICES_ENV)
    assert llm_prices.micros(PAID, calls=1) == round(0.0018 * llm_prices.MICROS)


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '{"deepseek-v4-flash": "cheap"}',
                                 '{"deepseek-v4-flash": [1.0]}', '{"deepseek-v4-flash": [-1.0, 2.0]}'])
def test_a_price_that_cannot_be_read_falls_back_to_the_measured_figure(monkeypatch, raw):
    """Money is never counted against half a price: the known-good figure holds and the log says why."""
    monkeypatch.setenv(llm_prices.PRICES_ENV, raw)
    assert llm_prices.per_mtok(PAID) is None
    assert llm_prices.micros(PAID, calls=1) == round(0.0018 * llm_prices.MICROS)


def test_a_price_for_another_model_leaves_this_one_measured(monkeypatch):
    monkeypatch.setenv(llm_prices.PRICES_ENV, json.dumps({"something-else": [1.0, 2.0]}))
    assert llm_prices.per_mtok(PAID) is None
    assert llm_prices.unit(PAID) == "measured cost a call"
