"""#166 item 3 — the paid providers' money: the record, and the day cap that refuses a call past it.

``core/llm_spend.py`` holds both halves and they are one module because the gate reads exactly what the record
writes. These tests pin:

* a paid answer lands on ``provider_spend_daily`` with its calls, its tokens and its cost;
* a model with no price is still recorded, with its tokens and a zero cost, because a row can be re-costed and
  no row cannot;
* the cap is the **box's** for the New York day, over every job and every run -- which the Relatedness board's
  per-run ceiling cannot see;
* ``RC_LLM_USD_DAY_CAP``: a number, ``0`` (refuse everything), ``off`` (no cap), and a value that cannot be read;
* **fail closed**: a ledger that cannot be read refuses the paid call, because a cap that cannot be checked is
  not a cap and every job's default writer costs nothing;
* ``RC_LLM_SPEND=0`` stops the record **and** the gate (one switch, both halves).
"""
from __future__ import annotations

import pytest

from revenuechaser.core import calendar as rc_calendar
from revenuechaser.core import llm_prices, llm_spend
from revenuechaser.rcdata import ops

PAID = "deepseek-v4-flash"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """The record on, no cap set (so the default holds), and no per-token price."""
    monkeypatch.delenv(llm_spend.ENV, raising=False)
    monkeypatch.delenv(llm_spend.CAP_ENV, raising=False)
    monkeypatch.delenv(llm_prices.PRICES_ENV, raising=False)


def _rows() -> list[dict]:
    today = rc_calendar.today_ny().isoformat()
    return ops.spend_by_day(today, today)


def _spend(usd: float, *, provider: str = "deepseek", model: str = PAID) -> None:
    """Put ``usd`` on today's ledger directly, as earlier runs of the day would have left it."""
    ops.count_spend(provider, model, calls=1, usd_micros=round(usd * llm_prices.MICROS))


# ── the record ────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_paid_answer_is_recorded_with_its_calls_tokens_and_cost():
    llm_spend.record("deepseek", PAID, calls=1, tokens_in=1200, tokens_out=300)
    rows = _rows()
    assert len(rows) == 1
    row = rows[0]
    assert (row["provider"], row["model"]) == ("deepseek", PAID)
    assert (row["calls"], row["tokens_in"], row["tokens_out"]) == (1, 1200, 300)
    assert row["usd_micros"] == llm_prices.micros(PAID, calls=1, tokens_in=1200, tokens_out=300)
    assert llm_spend.spent_today_usd() == pytest.approx(row["usd_micros"] / llm_prices.MICROS)


def test_two_answers_of_the_same_model_add_up_in_one_row():
    llm_spend.record("deepseek", PAID, calls=1, tokens_in=10, tokens_out=5)
    llm_spend.record("deepseek", PAID, calls=1, tokens_in=20, tokens_out=5)
    rows = _rows()
    assert len(rows) == 1 and rows[0]["calls"] == 2
    assert (rows[0]["tokens_in"], rows[0]["tokens_out"]) == (30, 10)


def test_each_model_keeps_its_own_row_because_the_model_is_what_prices_a_call():
    llm_spend.record("deepseek", PAID, calls=1)
    llm_spend.record("deepseek", "another-paid-model", calls=1)
    assert sorted(r["model"] for r in _rows()) == ["another-paid-model", PAID]


def test_a_model_with_no_price_is_recorded_with_its_tokens_and_no_cost():
    """The call happened: a row with the tokens can be re-costed once a price is known, no row cannot."""
    llm_spend.record("deepseek", "another-paid-model", calls=1, tokens_in=40, tokens_out=20)
    row = next(r for r in _rows() if r["model"] == "another-paid-model")
    assert (row["tokens_in"], row["tokens_out"], row["usd_micros"]) == (40, 20, 0)


def test_the_record_is_a_sum_of_exact_numbers(monkeypatch):
    """Money is micro-USD integers on purpose: a hundred answers do not drift."""
    monkeypatch.setenv(llm_prices.PRICES_ENV, '{"deepseek-v4-flash": [0.3, 0.3]}')
    for _ in range(100):
        llm_spend.record("deepseek", PAID, calls=1, tokens_in=1, tokens_out=0)   # 0.3 micro-USD, rounded to 0
    assert _rows()[0]["usd_micros"] == 0, "a figure below a micro-USD rounds, it does not accumulate error"
    for _ in range(100):
        llm_spend.record("deepseek", PAID, calls=1, tokens_in=10, tokens_out=0)  # 3 micro-USD each
    assert _rows()[0]["usd_micros"] == 300


def test_nothing_is_recorded_when_the_switch_is_off(monkeypatch):
    monkeypatch.setenv(llm_spend.ENV, "0")
    llm_spend.record("deepseek", PAID, calls=1, tokens_in=10, tokens_out=10)
    assert _rows() == [] and llm_spend.on() is False


def test_a_ledger_that_cannot_be_written_does_not_lose_the_answer(monkeypatch):
    """A record may never be the reason a paid answer is thrown away."""
    def boom(*a, **k):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(ops, "count_spend", boom)
    llm_spend.record("deepseek", PAID, calls=1)                  # no exception


def test_tokens_of_reads_an_openai_shaped_usage_and_nothing_else():
    assert llm_spend.tokens_of({"prompt_tokens": 7, "completion_tokens": 3}) == (7, 3)
    assert llm_spend.tokens_of({"prompt_tokens": None}) == (0, 0)
    assert llm_spend.tokens_of({"prompt_tokens": "x"}) == (0, 0)
    assert llm_spend.tokens_of({"prompt_tokens": -5, "completion_tokens": 2}) == (0, 2)
    assert llm_spend.tokens_of(None) == (0, 0)
    assert llm_spend.tokens_of("usage") == (0, 0)


# ── the cap ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_default_cap_is_the_run_ceiling_avo_already_set():
    """25 USD a day, the ceiling of ``RC_RELATEDNESS_USD_CAP``: a full profile round is ~14 USD (#712), so it
    fits in a day and a second round waits for the next."""
    assert llm_spend.day_cap_usd() == llm_spend.DEFAULT_DAY_CAP_USD == 25.0


def test_nothing_is_refused_below_the_cap():
    _spend(llm_spend.DEFAULT_DAY_CAP_USD - 1)
    assert llm_spend.refusal(PAID) is None and llm_spend.at_cap() is False


def test_the_call_is_refused_once_the_day_is_spent(monkeypatch):
    monkeypatch.setenv(llm_spend.CAP_ENV, "1.00")
    _spend(0.99)
    assert llm_spend.refusal(PAID) is None
    _spend(0.01)
    why = llm_spend.refusal(PAID)
    assert why and "day cap is spent" in why and "1.00 USD" in why
    assert "measured cost a call" in why, "the refusal says what kind of number it refused on"
    assert llm_spend.at_cap() is True


def test_the_cap_is_the_boxs_money_over_every_job_and_every_run(monkeypatch):
    """Six runs of their own ceiling are six times the money: the per-run cap cannot see that, this does."""
    monkeypatch.setenv(llm_spend.CAP_ENV, "10")
    _spend(6.0, model=PAID)
    _spend(4.0, model="another-paid-model")                     # another job, another model, same money
    assert llm_spend.spent_today_usd() == pytest.approx(10.0)
    assert llm_spend.at_cap() is True


def test_spend_can_still_be_read_for_one_provider_alone():
    _spend(2.0, provider="deepseek")
    _spend(3.0, provider="someone-else")
    assert llm_spend.spent_today_usd("deepseek") == pytest.approx(2.0)
    assert llm_spend.spent_today_usd() == pytest.approx(5.0)


def test_a_cap_of_zero_refuses_every_paid_call(monkeypatch):
    monkeypatch.setenv(llm_spend.CAP_ENV, "0")
    why = llm_spend.refusal(PAID)
    assert why and "0 USD" in why
    assert llm_spend.day_cap_usd() == 0.0


@pytest.mark.parametrize("raw", ["off", "OFF", "none", "no", "-1"])
def test_the_cap_can_be_removed(monkeypatch, raw):
    monkeypatch.setenv(llm_spend.CAP_ENV, raw)
    _spend(10_000.0)
    assert llm_spend.day_cap_usd() is None and llm_spend.refusal(PAID) is None


def test_a_cap_that_cannot_be_read_falls_back_to_the_default_and_not_to_no_cap(monkeypatch):
    monkeypatch.setenv(llm_spend.CAP_ENV, "lots")
    assert llm_spend.day_cap_usd() == llm_spend.DEFAULT_DAY_CAP_USD
    _spend(llm_spend.DEFAULT_DAY_CAP_USD)
    assert llm_spend.at_cap() is True


def test_a_ledger_that_cannot_be_read_refuses_the_paid_call(monkeypatch):
    """Fail closed: a cap that cannot be checked is not a cap, and the free writer is every job's default."""
    def boom(*a, **k):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(ops, "spend_micros_today", boom)
    assert llm_spend.spent_today_micros() is None
    why = llm_spend.refusal(PAID)
    assert why and "could not be read" in why


def test_the_switch_turns_the_gate_off_with_the_record(monkeypatch):
    """A gate reading a counter nobody writes is worse than no gate: one switch, both halves."""
    monkeypatch.setenv(llm_spend.CAP_ENV, "1")
    _spend(5.0)
    assert llm_spend.at_cap() is True
    monkeypatch.setenv(llm_spend.ENV, "0")
    assert llm_spend.refusal(PAID) is None
