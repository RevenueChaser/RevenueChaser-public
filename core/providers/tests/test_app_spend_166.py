"""#166 item 1 and 2 — a board Fetch's provider calls land on the day's ledger, and EDGAR counts at all.

The dashboard spends the same quota the builder does, and until this nothing on the app side wrote a number:
``provider_health`` is this run's banner and goes with the render, ``result_runs`` went with #860, and EDGAR had
no counter of any kind. These tests pin the three halves of the fix:

* ``providers/spend.py`` buffers and writes ``ops.provider_calls_daily`` under the builder's own provider names,
  keeps counts pending when the store refuses the write, and stops dead on ``RC_APP_SPEND=0``.
* ``UWClient`` counts its own requests -- one a sent request, retries included -- **unless** a caller installed
  the observers (the builder), whose book it then is.
* ``sec_edgar`` counts its requests and answers a ``health()`` like every other provider.
* ``yfinance`` counts one Yahoo read, the unit ``rcdata/build/sources/yahoo.py`` counts in.
"""
from __future__ import annotations

import httpx
import pytest

from RevenueChaser.core.providers import sec_edgar, spend
from RevenueChaser.core.providers import unusual_whales as uwmod
from RevenueChaser.core.providers import yfinance as yfmod
from RevenueChaser.core.providers.unusual_whales import UWClient
from RevenueChaser.core import calendar as rc_calendar
from RevenueChaser.rcdata import ops


@pytest.fixture(autouse=True)
def _clean_spend(monkeypatch):
    """Every test starts with an empty buffer, the ledger on, and the clock under its own control."""
    monkeypatch.delenv(spend.ENV, raising=False)
    monkeypatch.setattr(spend, "_pending", {})
    monkeypatch.setattr(spend, "_since", {})
    # #1267: the ledger these counts are made against, and what an earlier file's move dropped.
    monkeypatch.setattr(spend, "_ledger", None, raising=False)
    monkeypatch.setattr(spend, "_dropped", {}, raising=False)
    now = [0.0]
    monkeypatch.setattr(spend, "_clock", lambda: now[0])
    yield now


def _row(provider: str) -> dict:
    """``provider``'s row for today on the ledger, zeros when it has none."""
    today = rc_calendar.today_ny().isoformat()
    day = ops.calls_by_day(today, today)
    return next((r for r in day if r["provider"] == provider), {"calls": 0, "failures": 0, "http_429": 0})


class _Resp:
    def __init__(self, status: int, payload=None, text: str = "", headers=None, content: bytes = b"{}"):
        self.status_code, self._payload, self.text = status, payload if payload is not None else {"data": []}, text
        self.headers, self.content = headers or {}, content

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=self)


# ── The ledger itself ─────────────────────────────────────────────────────────────────────────────────────────

def test_counts_are_buffered_until_the_flush_point():
    """A write every call would be thousands of writes a Fetch: they gather, and one write holds them all."""
    for _ in range(spend.FLUSH_EVERY - 1):
        spend.count("uw", calls=1)
    assert spend.pending() == {"uw": [spend.FLUSH_EVERY - 1, 0, 0]}
    assert _row("uw")["calls"] == 0, "nothing is written before the flush point"
    spend.count("uw", calls=1)
    assert spend.pending() == {}
    assert _row("uw")["calls"] == spend.FLUSH_EVERY


def test_a_quiet_provider_is_written_on_time_not_on_volume(_clean_spend):
    """A Fetch that sends three requests and stops must not leave them unwritten until the next Fetch."""
    spend.count("sec", calls=3, failures=1, http_429=1)
    assert _row("sec")["calls"] == 0
    _clean_spend[0] += spend.FLUSH_AFTER_S
    spend.count("sec", calls=1)
    row = _row("sec")
    assert (row["calls"], row["failures"], row["http_429"]) == (4, 1, 1)


def test_the_env_switch_stops_every_write(monkeypatch):
    monkeypatch.setenv(spend.ENV, "0")
    spend.count("uw", calls=spend.FLUSH_EVERY * 2)
    spend.flush()
    assert spend.pending() == {}
    assert _row("uw")["calls"] == 0


def test_a_refused_write_keeps_the_counts_pending():
    """A locked store may not cost the day its count: the next flush writes what the failed one held.

    Its own ``MonkeyPatch`` context, not the fixture's: ``undo()`` on the shared one would also undo the clock
    and the empty buffer this test is counting into.
    """
    def _boom(*a, **k):
        raise RuntimeError("database is locked")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ops, "count_calls", _boom)
        spend.count("sec", calls=4, failures=1)
        spend.flush()
        assert spend.pending() == {"sec": [4, 1, 0]}
    spend.flush()
    assert spend.pending() == {}
    assert _row("sec")["calls"] == 4


# ── Unusual Whales ────────────────────────────────────────────────────────────────────────────────────────────

def _scripted(monkeypatch, *outcomes, key: str = "k") -> UWClient:
    c = UWClient(key=key, sleep=lambda _s: None)
    seq = list(outcomes)

    def _get(url, params=None):
        out = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(out, BaseException):
            raise out
        return out

    monkeypatch.setattr(c._client, "get", _get)
    monkeypatch.setattr(uwmod, "_random", lambda: 1.0)
    return c


def test_uw_counts_every_request_a_retry_ladder_sends(monkeypatch):
    """Three requests, one logical call: the provider counted three, so the ledger must say three (#519 f3)."""
    c = _scripted(monkeypatch, _Resp(500), _Resp(500), _Resp(500))
    assert c.get_result("/x").status == "failed"
    spend.flush()
    row = _row("uw")
    assert (row["calls"], row["failures"]) == (uwmod.MAX_ATTEMPTS, 1), "one final failure, not one per attempt"


def test_uw_counts_a_429_answer_and_then_the_success(monkeypatch):
    c = _scripted(monkeypatch, _Resp(429), _Resp(200, {"data": [1]}))
    assert c.get_result("/x").status == "ok"
    spend.flush()
    row = _row("uw")
    assert (row["calls"], row["failures"], row["http_429"]) == (2, 0, 1)


def test_uw_counts_a_final_4xx_of_its_own_making(monkeypatch):
    """An unknown ticker never reaches ``health()``, so nothing else would ever count it."""
    c = _scripted(monkeypatch, _Resp(404, text="no such ticker"))
    assert c.get_result("/x").status == "failed"
    spend.flush()
    row = _row("uw")
    assert (row["calls"], row["failures"]) == (1, 1)


def test_uw_counts_nothing_when_a_caller_owns_the_counting(monkeypatch):
    """The builder installs the observers and writes the ledger itself: counting here would double its day."""
    c = _scripted(monkeypatch, _Resp(429), _Resp(500), _Resp(500))
    seen: list[str] = []
    c.on_request = seen.append
    c.on_response = lambda ep, r: seen.append(f"{ep}:{r.status_code}")
    assert c.get_result("/x").status == "failed"
    spend.flush()
    assert len(seen) == 2 * uwmod.MAX_ATTEMPTS
    assert _row("uw")["calls"] == 0


def test_uw_counts_nothing_for_a_call_the_breaker_refused(monkeypatch):
    """The breaker sends no request, so there is no spend -- and no failure either."""
    c = _scripted(monkeypatch, _Resp(200, {"data": []}))
    c._breaker_open = True
    assert c.get_result("/x").status == "failed"
    spend.flush()
    row = _row("uw")
    assert (row["calls"], row["failures"]) == (0, 0)


# ── SEC EDGAR ─────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _edgar_ready(monkeypatch):
    sec_edgar.reset_breaker()
    sec_edgar.reset_health()
    monkeypatch.setattr(sec_edgar, "_throttle", lambda: None)
    # The retry backoff, not ``time.sleep`` itself: patching the module's clock would patch it for the process.
    monkeypatch.setattr(sec_edgar, "_retry_delay", lambda resp, attempt: 0.0)


def _edgar_client(*outcomes):
    seq = list(outcomes)

    class _Client:
        def get(self, url):
            out = seq.pop(0) if len(seq) > 1 else seq[0]
            if isinstance(out, BaseException):
                raise out
            return out

    return _Client()


def test_edgar_answers_a_health_like_every_other_provider():
    """Item 2: EDGAR was the one provider with no ``health()`` at all, so a Fetch of it recorded nothing."""
    assert sec_edgar.health() == {"provider": "sec", "calls": 0, "failed": 0, "auth_error": None,
                                  "failures": [], "breaker_open": False, "skipped_calls": 0}


def test_edgar_counts_one_request_and_one_call_on_an_answer():
    assert sec_edgar.get_json("https://data.sec.gov/x", _edgar_client(_Resp(200, content=b'{"a": 1}'))) == {"a": 1}
    spend.flush()
    row = _row("sec")
    assert (row["calls"], row["failures"]) == (1, 0)
    assert (sec_edgar.health()["calls"], sec_edgar.health()["failed"]) == (1, 0)


def test_edgar_reads_an_absent_object_as_an_answer_not_a_failure():
    """A 404 is the SEC saying the object is not there; the caller reads it as absent, and so does the ledger."""
    with pytest.raises(httpx.HTTPStatusError):
        sec_edgar.get_bytes("https://www.sec.gov/x", _edgar_client(_Resp(404)))
    spend.flush()
    row = _row("sec")
    assert (row["calls"], row["failures"]) == (1, 0)
    assert sec_edgar.health()["failed"] == 0


def test_edgar_counts_a_retried_429_and_the_final_failure():
    with pytest.raises(httpx.HTTPStatusError):
        sec_edgar.get_bytes("https://www.sec.gov/x", _edgar_client(_Resp(429), _Resp(429), _Resp(429), _Resp(429)))
    spend.flush()
    row = _row("sec")
    assert (row["calls"], row["http_429"], row["failures"]) == (sec_edgar._MAX_RETRIES, sec_edgar._MAX_RETRIES, 1)
    assert sec_edgar.health()["failed"] == 1


def test_edgar_counts_the_403_that_breaks_the_circuit():
    with pytest.raises(httpx.HTTPStatusError):
        sec_edgar.get_bytes("https://www.sec.gov/x", _edgar_client(_Resp(403)))
    spend.flush()
    row = _row("sec")
    assert (row["calls"], row["failures"]) == (1, 1)
    assert sec_edgar.health()["failures"] == [{"endpoint": "https://www.sec.gov/x", "error": "HTTP 403"}]


def test_edgar_counts_nothing_when_the_breaker_sent_no_request():
    sec_edgar._breaker_fail(immediate=True)
    with pytest.raises(sec_edgar.SECUnavailable):
        sec_edgar.get_bytes("https://www.sec.gov/x", _edgar_client(_Resp(200)))
    spend.flush()
    assert _row("sec")["calls"] == 0


# ── yfinance ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_yahoo_counts_one_read_the_unit_the_builder_counts_in():
    yfmod.reset_health()
    assert yfmod.attempt(lambda: 7, endpoint="info")[0] == 7
    spend.flush()
    row = _row("yfinance")
    assert (row["calls"], row["failures"]) == (1, 0)


def test_a_failed_yahoo_read_is_a_failure_on_the_ledger():
    yfmod.reset_health()

    def _raise():
        raise ValueError("Yahoo said no")

    value, error = yfmod.attempt(_raise, endpoint="info", empty=None)
    assert value is None and error
    spend.flush()
    row = _row("yfinance")
    assert row["calls"] >= 1 and row["failures"] >= 1


# ── The caller's own book (#1277) ──────────────────────────────────────────────────────────────────────────────

def test_yahoo_counts_nothing_while_the_caller_owns_the_ledger():
    """The builder counts its own Yahoo reads (``ctx.count``), so counting here would double its day (#1277)."""
    yfmod.reset_health()
    with yfmod.spend_owned_by_caller():
        assert yfmod.attempt(lambda: 7, endpoint="info")[0] == 7
    spend.flush()
    assert _row("yfinance")["calls"] == 0
    assert yfmod.health()["calls"] == 1          # the banner still sees the read


def test_a_failed_read_inside_the_callers_block_is_not_on_the_ledger_either():
    yfmod.reset_health()

    def _raise():
        raise ValueError("Yahoo said no")

    with yfmod.spend_owned_by_caller():
        value, error = yfmod.attempt(_raise, endpoint="info")
    assert value is None and error
    spend.flush()
    row = _row("yfinance")
    assert (row["calls"], row["failures"]) == (0, 0)
    assert yfmod.health()["failed"] == 1


def test_the_block_ends_with_its_body_so_a_later_read_is_counted_again():
    yfmod.reset_health()
    with yfmod.spend_owned_by_caller():
        yfmod.attempt(lambda: 1, endpoint="info")
    yfmod.attempt(lambda: 2, endpoint="info")
    spend.flush()
    assert _row("yfinance")["calls"] == 1


def test_the_block_ends_on_an_exception_too():
    yfmod.reset_health()
    with pytest.raises(RuntimeError):
        with yfmod.spend_owned_by_caller():
            raise RuntimeError("the fetch gave up")
    yfmod.attempt(lambda: 1, endpoint="info")
    spend.flush()
    assert _row("yfinance")["calls"] == 1


def test_the_blocks_nest_so_an_inner_one_does_not_reopen_the_ledger():
    yfmod.reset_health()
    with yfmod.spend_owned_by_caller():
        with yfmod.spend_owned_by_caller():
            yfmod.attempt(lambda: 1, endpoint="info")
        yfmod.attempt(lambda: 2, endpoint="info")
    spend.flush()
    assert _row("yfinance")["calls"] == 0
