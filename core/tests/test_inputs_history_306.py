"""Watchlist and board settings keep every change (#306, D36, rule A; history redesign C).

The store records each write to ``board_settings`` in ``board_settings_changes`` (schema 11), and the watchlist toggle
(the stock watch list in ops.sqlite since PR 4) writes ``watchlist_stock_changes``. These tests pin what a user action
leaves there: a toggle writes its own ticker only, in one transaction, and a Reset appends its 'absent' rows in one
change. Temp stores only.
"""
from __future__ import annotations

import threading

import pytest

from RevenueChaser.core import board_settings as bs
from RevenueChaser.core import rawstore
from RevenueChaser.module_comovement import config
from RevenueChaser.rcdata import read as wl_read

B = "module_comovement"


# ── watchlist: one ticker, one transaction ───────────────────────────────────────────────────────────────────────
# Since PR 4 the toggle is the stock watch list's, in ops.sqlite, and its history is ``watchlist_stock_changes``
# (one add / remove row per flip, ordered by ``id``); the guarantees these tests pin are the same.
def _stock_history(ticker: str | None = None) -> list[tuple]:
    from RevenueChaser.module_watchlists import store
    return [(r["symbol"], r["action"]) for r in reversed(store.changes("jobs.stock", limit=10_000))
            if ticker is None or r["symbol"] == ticker]


def _stock_history_equals_list() -> bool:
    """Replaying the history (add / remove per ticker) gives the list as it stands."""
    from RevenueChaser.rcdata import ops
    state: dict[str, bool] = {}
    for t, action in _stock_history():
        state[t] = action == "add"
    return {t for t, on in state.items() if on} == set([r["ticker"] for r in wl_read.watchlists()["stock"]])


def test_toggle_adds_then_removes_and_says_which():
    assert rawstore.toggle_watchlist("AAA") is True
    assert rawstore.load_watchlist() == {"AAA"}
    assert rawstore.toggle_watchlist("AAA") is False
    assert rawstore.load_watchlist() == set()


def test_toggle_off_then_on_in_one_session_keeps_both_rows():
    for _ in range(3):
        rawstore.toggle_watchlist("AAA", by="leaps")
    assert _stock_history("AAA") == [("AAA", "add"), ("AAA", "remove"), ("AAA", "add")]


def test_toggle_leaves_the_other_tickers_alone():
    rawstore.save_watchlist({"BBB", "CCC"})
    before = _stock_history()
    rawstore.toggle_watchlist("AAA")
    rawstore.toggle_watchlist("BBB")
    assert rawstore.load_watchlist() == {"AAA", "CCC"}
    assert _stock_history()[len(before):] == [("AAA", "add"), ("BBB", "remove")]


def test_toggle_never_rewrites_the_whole_list(monkeypatch):
    from RevenueChaser.rcdata import ops

    def boom(*a, **k):
        raise AssertionError("a toggle rewrote the whole watchlist")
    monkeypatch.setattr(ops, "watch_replace", boom)
    monkeypatch.setattr(rawstore, "replace_all", boom)
    rawstore.toggle_watchlist("AAA")
    rawstore.toggle_watchlist("AAA")


def test_concurrent_toggles_of_different_tickers_all_land():
    tickers = [f"T{i}" for i in range(8)]
    errors: list[Exception] = []
    gate = threading.Barrier(len(tickers))

    def flip(t):
        try:
            gate.wait(10)
            rawstore.toggle_watchlist(t)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=flip, args=(t,)) for t in tickers]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not errors, errors[:2]
    assert rawstore.load_watchlist() == set(tickers)
    assert {t for t, _ in _stock_history()} == set(tickers) and _stock_history_equals_list()


# ── board settings: Reset appends 'absent', the board reads its defaults ─────────────────────────────────────────


# ── review round (B1, B2, S1) ────────────────────────────────────────────────────────────────────────────────────
def _race(fn, args):
    gate = threading.Barrier(len(args))
    results, errors = [], []

    def run(a):
        try:
            gate.wait(10)
            results.append(fn(*a))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(a,)) for a in args]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return results, errors


@pytest.mark.parametrize("n", [2, 7, 8])
def test_same_ticker_concurrent_toggles(n):
    """Each click flips the state the previous one left: a read outside the transaction would flip one state twice."""
    results, errors = _race(rawstore.toggle_watchlist, [("AAA",)] * n)
    assert not errors, errors[:2]
    assert sorted(results) == sorted([True] * ((n + 1) // 2) + [False] * (n // 2)), results
    assert rawstore.load_watchlist() == ({"AAA"} if n % 2 else set())
    assert [a for _, a in _stock_history("AAA")] == ["add", "remove"] * (n // 2) + (["add"] if n % 2 else [])
    assert _stock_history_equals_list()


