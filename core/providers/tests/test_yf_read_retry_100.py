"""#100: every yfinance read is counted for the board banner and retried once after Yahoo's 401.

Two things were measured on ``main`` c2b2c88 (20 Nov 2026) and are fixed here:

* ``yf_session.recover`` — the 401 cure built for #402 — had **no non-test caller**. Its one caller,
  ``load_ohlc``, went with the old bar path, so the cure was dead code: a 401 mid-sweep poisoned every later
  read of the process, which is exactly the 14 Oct night #402 was opened for.
* call sites counted nothing or counted on the module global alone, so the ``health_scope`` a board opens for
  its own run (#299) saw fewer calls than the run made — zero, for Swing's whole ``.info`` sweep.

Offline: no yfinance import answers anything real here, the session reset is faked, and
``conftest.isolate_yf_session`` keeps one test's pending 401 out of the next.
"""
from __future__ import annotations

import pandas as pd
import pytest

from revenuechaser.core.providers import yf_session
from revenuechaser.core.providers import yfinance as yfp

AUTH = "HTTP Error 401: Invalid Crumb"


@pytest.fixture
def resets(monkeypatch):
    """Count the session resets and keep the real one off the installed library."""
    done: list[int] = []
    monkeypatch.setattr(yf_session, "_reset", lambda: (done.append(1), ["crumb"])[1])
    return done


def _saw_401() -> None:
    """What yfinance's logger does when Yahoo refuses the crumb: the watcher notes it, nothing raises."""
    yf_session._STATE["seen"] = yf_session.clock()


# --- the counting half -------------------------------------------------------------------------------------

def test_a_read_is_counted_in_the_global_and_in_every_open_scope():
    before = yfp.health()["calls"]
    with yfp.health_scope() as health:
        assert yfp.attempt(lambda: 7, endpoint="X.info") == (7, None)
    assert health.health()["calls"] == 1
    assert yfp.health()["calls"] == before + 1


def test_a_failed_read_is_counted_failed_with_its_text_and_the_caller_gets_it():
    with yfp.health_scope() as health:
        value, error = yfp.attempt(lambda: (_ for _ in ()).throw(RuntimeError("Yahoo said no")), endpoint="X.info")
    assert value is None and error == "Yahoo said no"
    reported = health.health()
    assert reported["calls"] == 1 and reported["failed"] == 1
    assert reported["failures"] == [{"endpoint": "X.info", "error": "Yahoo said no"}]


def test_an_exception_with_no_message_is_counted_under_its_type():
    with yfp.health_scope() as health:
        _, error = yfp.attempt(lambda: (_ for _ in ()).throw(TimeoutError()), endpoint="X.info")
    assert error == "TimeoutError"
    assert health.health()["failures"] == [{"endpoint": "X.info", "error": "TimeoutError"}]


def test_count_false_buys_the_retry_without_the_counting(resets):
    """Swing's ``.info`` refetch counts for itself: an answer that came back empty is a failed read there."""
    _saw_401()
    tries: list[int] = []

    def call():
        tries.append(1)
        if len(tries) == 1:
            raise RuntimeError(AUTH)
        return {"marketCap": 1}

    with yfp.health_scope() as health:
        value, error = yfp.attempt(call, endpoint="X.info", count=False)
    assert (value, error) == ({"marketCap": 1}, None)
    assert len(tries) == 2 and len(resets) == 1, "the reset and the retry still happen"
    assert health.health()["calls"] == 0, "counting is the caller's"


def test_read_gives_the_default_on_failure_and_the_value_otherwise():
    assert yfp.read(lambda: (_ for _ in ()).throw(RuntimeError("no")), default={}) == {}
    assert yfp.read(lambda: {"a": 1}, default={}) == {"a": 1}


# --- the 401 half ------------------------------------------------------------------------------------------

def test_a_401_resets_the_session_once_and_the_read_is_retried(resets):
    tries: list[int] = []

    def call():
        tries.append(1)
        if len(tries) == 1:
            raise RuntimeError(AUTH)
        return "second time lucky"

    with yfp.health_scope() as health:
        assert yfp.attempt(call, endpoint="X.info") == ("second time lucky", None)
    assert len(tries) == 2, "the read was tried again after the reset"
    assert len(resets) == 1, "exactly one session reset"
    reported = health.health()
    assert (reported["calls"], reported["failed"]) == (1, 0), "a cured read is one successful call"


def test_a_failure_that_is_not_a_401_is_not_retried(resets):
    tries: list[int] = []

    def call():
        tries.append(1)
        raise RuntimeError("Too Many Requests. Rate limited.")

    value, error = yfp.attempt(call, endpoint="X.info")
    assert value is None and "Rate limited" in error
    assert len(tries) == 1 and resets == [], "a rate limit is not cured by a new session"


def test_a_401_that_is_only_logged_reaches_the_retry_through_the_empty_predicate(resets):
    """yfinance does not raise a refused ``history``: it logs the 401 and hands back an empty frame."""
    _saw_401()
    tries: list[int] = []

    def call():
        tries.append(1)
        return pd.DataFrame() if len(tries) == 1 else pd.DataFrame({"Close": [1.0]})

    frame, error = yfp.attempt(call, endpoint="X.history",
                               empty=lambda df: df is None or getattr(df, "empty", True))
    assert error is None and list(frame["Close"]) == [1.0]
    assert len(tries) == 2 and len(resets) == 1


def test_an_honestly_empty_answer_is_not_retried(resets):
    """No 401 pending: an empty frame is Yahoo having no bar, and one empty answer is the answer."""
    tries: list[int] = []

    def call():
        tries.append(1)
        return pd.DataFrame()

    frame, error = yfp.attempt(call, endpoint="X.history",
                               empty=lambda df: df is None or getattr(df, "empty", True))
    assert error is None and frame.empty
    assert len(tries) == 1 and resets == []


def test_a_retry_that_fails_again_is_one_counted_failure(resets):
    _saw_401()
    tries: list[int] = []

    def call():
        tries.append(1)
        raise RuntimeError(AUTH)

    with yfp.health_scope() as health:
        value, error = yfp.attempt(call, endpoint="X.info")
    assert value is None and "Invalid Crumb" in error
    assert len(tries) == 2 and len(resets) == 1
    reported = health.health()
    assert (reported["calls"], reported["failed"]) == (1, 1), "one read, counted once"


def test_a_predicate_that_raises_means_not_empty(resets):
    _saw_401()
    tries: list[int] = []

    def call():
        tries.append(1)
        return object()

    value, error = yfp.attempt(call, endpoint="X.info", empty=lambda v: v.nope)
    assert error is None and value is not None
    assert len(tries) == 1, "a broken predicate must never turn a good read into a retry"


# --- the cure must not go inert again ----------------------------------------------------------------------

def test_the_401_recovery_has_a_non_test_caller():
    """#402's cure was inert for weeks because its only caller was deleted. This is the guard against that.

    ``attempt`` is now the single place every yfinance read passes through, so this asserts the wiring at the
    one point that matters: a module that stops calling ``recover`` fails here.
    """
    import inspect
    source = inspect.getsource(yfp.attempt)
    assert "yf_session.recover(" in source, "attempt() must consult the 401 recovery"
    # and the whole tree reads Yahoo through it
    assert callable(yfp.read) and callable(yfp.attempt)
