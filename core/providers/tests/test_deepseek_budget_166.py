"""#166 — the paid client's money gate and its record, inside ``deepseek.complete``.

The order is **cache -> off-peak gate -> money gate -> HTTP**, and each step of it is here:

* a cached answer costs nothing, so the cap never stands in its way;
* a spent day raises ``BudgetSpentError`` and **sends nothing** (the point of a gate over a report);
* an answer that is served records its own calls and tokens, so the next call's gate sees it;
* ``BudgetSpentError`` is a ``DeepSeekError`` and its own class: a caller that stops on one stops on this, and a
  run can say *budget* and not *peak*, because the two boundaries free at different times.
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import calendar as rc_calendar
from RevenueChaser.core import llm_prices, llm_spend
from RevenueChaser.core.providers import deepseek as ds
from RevenueChaser.rcdata import ops


class _Resp:
    def __init__(self, payload):
        self.status_code, self._payload, self.text, self.headers = 200, payload, "", {}

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self._resp, self.calls = _Resp(payload), 0

    def post(self, *a, **k):
        self.calls += 1
        return self._resp

    def close(self):
        pass


def _answer(content="{}", usage=None):
    return _Client({"choices": [{"message": {"content": content}}], "usage": usage or {}})


@pytest.fixture(autouse=True)
def live(monkeypatch):
    """Off-peak gate off, a key present, the record on and no cap set: the money gate is what is under test."""
    monkeypatch.setenv("RC_DEEPSEEK_OFF_PEAK_ONLY", "0")
    monkeypatch.setattr(ds, "key_for", lambda slug: "k")
    monkeypatch.delenv(llm_spend.ENV, raising=False)
    monkeypatch.delenv(llm_spend.CAP_ENV, raising=False)
    monkeypatch.delenv(llm_prices.PRICES_ENV, raising=False)


def _rows() -> list[dict]:
    today = rc_calendar.today_ny().isoformat()
    return ops.spend_by_day(today, today)


def _spend(usd: float) -> None:
    ops.count_spend("deepseek", ds.MODEL, calls=1, usd_micros=round(usd * llm_prices.MICROS))


def test_a_spent_day_raises_before_the_request_is_sent(rawstore_tmp_db, monkeypatch):
    monkeypatch.setenv(llm_spend.CAP_ENV, "1")
    _spend(1.0)
    client = _answer()
    with pytest.raises(ds.BudgetSpentError) as caught:
        ds.complete("sys", "user", client=client, use_cache=False)
    assert client.calls == 0, "a gate that sends the request first is a report, not a gate"
    assert "day cap is spent" in caught.value.reason


def test_the_budget_error_is_a_deepseek_error_and_its_own_class():
    """Callers that already stop on a DeepSeekError stop on this; a run still reports ``budget``, not ``peak``."""
    assert issubclass(ds.BudgetSpentError, ds.DeepSeekError)
    assert not issubclass(ds.BudgetSpentError, ds.PeakHoursError)
    assert not issubclass(ds.BudgetSpentError, (ds.DeepSeekAuthError, ds.DeepSeekTransientError))


def test_an_answer_under_the_cap_is_served_and_recorded(rawstore_tmp_db):
    client = _answer("{}", {"prompt_tokens": 900, "completion_tokens": 100})
    assert ds.complete("sys", "user", client=client, use_cache=False) == "{}"
    assert client.calls == 1
    row = next(r for r in _rows() if r["model"] == ds.MODEL)
    assert (row["calls"], row["tokens_in"], row["tokens_out"]) == (1, 900, 100)
    assert row["usd_micros"] == llm_prices.micros(ds.MODEL, calls=1, tokens_in=900, tokens_out=100)


def test_the_record_of_one_call_is_what_the_next_calls_gate_reads(rawstore_tmp_db, monkeypatch):
    """The whole point of a straight-through write: the cap holds inside a run, not only between runs."""
    monkeypatch.setenv(llm_spend.CAP_ENV, f"{0.0018 * 1.5:.4f}")       # room for one measured call, not two
    assert ds.complete("sys", "one", client=_answer(), use_cache=False) == "{}"
    client = _answer()
    with pytest.raises(ds.BudgetSpentError):
        ds.complete("sys", "two", client=client, use_cache=False)
    assert client.calls == 0


def test_an_answer_with_no_usage_still_costs_its_call(rawstore_tmp_db):
    """A gate that reports no tokens must not make a paid call look free to the cap."""
    ds.complete("sys", "user", client=_answer(), use_cache=False)
    row = next(r for r in _rows() if r["model"] == ds.MODEL)
    assert row["usd_micros"] == llm_prices.micros(ds.MODEL, calls=1) > 0


def test_a_cached_answer_is_served_at_the_cap_and_is_not_recorded_again(rawstore_tmp_db, monkeypatch):
    """The cache comes first on purpose: a cached answer costs nothing, so the cap has nothing to refuse."""
    assert ds.complete("sys", "user", client=_answer("{\"a\": 1}")) == "{\"a\": 1}"
    before = next(r for r in _rows() if r["model"] == ds.MODEL)["calls"]
    monkeypatch.setenv(llm_spend.CAP_ENV, "0")                          # every paid call refused
    client = _answer("{\"a\": 1}")
    assert ds.complete("sys", "user", client=client) == "{\"a\": 1}"     # the cache answers
    assert client.calls == 0
    assert next(r for r in _rows() if r["model"] == ds.MODEL)["calls"] == before


def test_the_switch_leaves_the_client_as_it_was_before_the_gate(rawstore_tmp_db, monkeypatch):
    """``RC_LLM_SPEND=0`` is the rollback: no refusal and no row."""
    monkeypatch.setenv(llm_spend.ENV, "0")
    monkeypatch.setenv(llm_spend.CAP_ENV, "0")
    client = _answer()
    assert ds.complete("sys", "user", client=client, use_cache=False) == "{}"
    assert client.calls == 1 and _rows() == []


def test_a_ledger_that_cannot_be_read_stops_the_paid_call(rawstore_tmp_db, monkeypatch):
    """Fail closed, and the free writer is every job's default (``core.llm_jobs``), so the work goes on."""
    def boom(*a, **k):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(ops, "spend_micros_today", boom)
    client = _answer()
    with pytest.raises(ds.BudgetSpentError):
        ds.complete("sys", "user", client=client, use_cache=False)
    assert client.calls == 0


def test_the_peak_gate_still_comes_first(rawstore_tmp_db, monkeypatch):
    """At peak the money question is never asked: nothing is sent either way, and the message must say peak."""
    monkeypatch.setenv("RC_DEEPSEEK_OFF_PEAK_ONLY", "1")
    monkeypatch.setattr(ds.offpeak, "is_off_peak", lambda now=None: False)
    monkeypatch.setenv(llm_spend.CAP_ENV, "0")
    client = _answer()
    with pytest.raises(ds.PeakHoursError):
        ds.complete("sys", "user", client=client, use_cache=False)
    assert client.calls == 0


def test_the_free_writer_is_not_gated_and_not_recorded(rawstore_tmp_db, monkeypatch):
    """EVREN costs nothing, has its own client, and must not be stopped by the paid cap (#1183)."""
    from RevenueChaser.core.providers import evren
    monkeypatch.setenv(llm_spend.CAP_ENV, "0")
    monkeypatch.setattr(evren, "key_for", lambda slug: "k")
    client = _answer()
    assert evren.complete("sys", "user", client=client, use_cache=False) == "{}"
    assert client.calls == 1 and _rows() == []
