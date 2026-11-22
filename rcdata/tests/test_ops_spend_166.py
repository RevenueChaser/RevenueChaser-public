"""#166 item 3 — ``provider_spend_daily``, the paid providers' money, on whichever backend is configured.

The money counter is separate from ``provider_calls_daily`` because its unit is money and its key carries the
model, which is what prices a call. These tests hold it to that: one row per provider, model and New York day,
adding up, in the ledger's exact integer unit (micro-USD), and the metered counter untouched beside it.

``rcdata/tests/test_ops_redis.py`` holds the two backends to the same answers; this file is the behaviour.
"""
from __future__ import annotations

from revenuechaser.core import calendar as rc_calendar
from revenuechaser.rcdata import ops


def _today() -> str:
    return rc_calendar.today_ny().isoformat()


def test_a_row_is_kept_per_provider_model_and_day():
    ops.count_spend("deepseek", "deepseek-v4-flash", calls=1, tokens_in=900, tokens_out=100, usd_micros=1800)
    ops.count_spend("deepseek", "another-model", calls=3, usd_micros=10)
    rows = ops.spend_by_day(_today(), _today())
    assert [(r["provider"], r["model"], r["calls"], r["usd_micros"]) for r in rows] == [
        ("deepseek", "another-model", 3, 10), ("deepseek", "deepseek-v4-flash", 1, 1800)]
    assert rows[1]["tokens_in"] == 900 and rows[1]["tokens_out"] == 100


def test_the_same_key_adds_up():
    for _ in range(3):
        ops.count_spend("deepseek", "deepseek-v4-flash", calls=1, tokens_in=10, tokens_out=4, usd_micros=1800)
    row = ops.spend_by_day(_today(), _today())[0]
    assert (row["calls"], row["tokens_in"], row["tokens_out"], row["usd_micros"]) == (3, 30, 12, 5400)


def test_todays_total_is_over_every_model_and_can_be_asked_per_provider():
    """The day cap is the box's money, so the gate asks for the total (``core/llm_spend.py``)."""
    ops.count_spend("deepseek", "deepseek-v4-flash", usd_micros=1_500_000)
    ops.count_spend("deepseek", "another-model", usd_micros=500_000)
    ops.count_spend("someone-else", "their-model", usd_micros=1)
    assert ops.spend_micros_today() == 2_000_001
    assert ops.spend_micros_today("deepseek") == 2_000_000
    assert ops.spend_micros_today("nobody") == 0


def test_an_earlier_day_is_not_todays_spend():
    """The window is the New York day, as ``provider_calls_daily``'s is: yesterday's money is spent and gone."""
    ops.put_rows("provider_spend_daily", [{"provider": "deepseek", "model": "deepseek-v4-flash",
                                           "ny_day": "2026-10-25", "calls": 10, "tokens_in": 0, "tokens_out": 0,
                                           "usd_micros": 9_000_000}])
    assert ops.spend_micros_today() == 0
    assert len(ops.spend_by_day("2026-10-25", _today())) == 1


def test_an_empty_ledger_is_zero_and_not_an_error():
    assert ops.spend_micros_today() == 0 and ops.spend_by_day("2000-01-01", _today()) == []


def test_the_metered_counter_is_a_different_table():
    """``provider_calls_daily`` counts requests and knows nothing about money; neither leaks into the other."""
    ops.count_calls("uw", 5)
    ops.count_spend("deepseek", "deepseek-v4-flash", calls=1, usd_micros=1800)
    assert ops.calls_today("uw") == 5 and ops.calls_today("deepseek") == 0
    assert ops.spend_micros_today("uw") == 0 and ops.spend_micros_today() == 1800
