"""#116 step C: the gates drop, under a cap, and every drop is a funnel step.

``price_hygiene.decide`` is the one place that turns a scan's flags into drops: more than ``DROP_MAX_SHARE`` of the
scanned names flagged is a data failure, not a universe of broken series, so nothing drops and the board says so.
The funnel side: one ``drop`` step per fired reason (``by_design=False``), after the liquidity prefilter's steps and
before the scoring drops, plus the ``note`` step when the cap trips. No store, no network.
"""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from RevenueChaser.core import funnel, price_hygiene as ph
from RevenueChaser.core import screen_common as sc

from RevenueChaser.core.tests.test_screen_common_147 import Board, board  # noqa: F401 - #147's fake board
                                                                         # and its fixture


# ── decide: the cap ───────────────────────────────────────────────────────────

def test_decide_drops_each_flagged_name_under_its_own_reason():
    d = ph.decide({"AAA": "locked", "CCC": "bad_wick", "BBB": "locked"}, scanned=100)
    assert d.capped is False
    assert d.dropped == {"locked": ["AAA", "BBB"], "bad_wick": ["CCC"]}, "sorted, so a run is reproducible"
    assert d.share == pytest.approx(0.03)


def test_decide_drops_nothing_when_more_than_the_cap_is_flagged():
    """``DROP_MAX_SHARE`` follows ``screen_common.STALE_DROP_MAX_SHARE``: a wrong threshold must not be able to
    empty a board overnight, so above the cap every flagged name is kept and counted in a note."""
    flagged = {f"T{i}": "locked" for i in range(6)}
    d = ph.decide(flagged, scanned=100)
    assert d.capped is True and d.dropped == {} and d.flagged == flagged
    assert d.share == pytest.approx(0.06) and d.share > ph.DROP_MAX_SHARE


def test_the_cap_is_exclusive_so_exactly_the_share_still_drops():
    at = ph.decide({f"T{i}": "locked" for i in range(5)}, scanned=100)
    assert at.capped is False and len(at.dropped["locked"]) == 5


def test_nothing_flagged_and_nothing_scanned_drop_nothing():
    assert ph.decide({}, scanned=100) == ph.Decision({}, {}, 100, False)
    assert ph.decide({}, scanned=0).dropped == {}
    assert ph.decide({"AAA": "locked"}, scanned=0).capped is True, "no scanned count: the share cannot be tested"


# ── the funnel steps ──────────────────────────────────────────────────────────

CFG = SimpleNamespace(MIN_PRICE=5.0, MIN_DOLLAR_VOLUME=250_000.0)


def _steps(**kw):
    args = dict(universe=100, excluded_types=0, prefiltered=sc.Prefiltered([], {}), dropped={}, scored=0,
                passed=0, shown=0, cfg=CFG)
    args.update(kw)
    steps = sc.funnel_steps(**args)
    assert funnel.validate(steps) == []
    return steps


def test_every_hygiene_reason_can_be_its_own_drop_step_and_is_not_by_design():
    dropped = {k: [f"{k.upper()[:3]}{i}" for i in range(2)] for k in ph.REASONS}
    steps = {s["key"]: s for s in _steps(dropped=dropped, scored=90)}
    for key in ph.REASONS:
        assert steps[key]["kind"] == "drop" and steps[key]["count"] == 2, key
        assert steps[key]["by_design"] is False, f"{key}: a broken series is a data gap, never a board rule"
        assert ph.LABELS[key] in steps[key]["label"], key


def test_a_hygiene_step_sits_after_the_prefilter_steps_and_before_the_scoring_drops():
    pf = sc.Prefiltered([], {"low_price": ["LOW"]}, cfg=CFG)
    keys = [s["key"] for s in _steps(prefiltered=pf, dropped={"locked": ["LCK"], "no_edgar_annual": ["NOE"]},
                                     scored=97)]
    assert keys.index("low_price") < keys.index("locked") < keys.index("no_edgar_annual")


def test_the_prefilter_steps_read_as_a_liquidity_prefilter_with_their_keys_unchanged():
    """#116 D: the three reasons are a liquidity prefilter and the board text says so. The keys are stored in
    payloads, so only the printed label changes."""
    pf = sc.Prefiltered([], {k: [k.upper()] for k in sc.PREFILTER_REASONS}, cfg=CFG)
    steps = {s["key"]: s for s in _steps(prefiltered=pf, scored=97)}
    assert set(steps) >= set(sc.PREFILTER_REASONS), "the keys stay"
    for key in sc.PREFILTER_REASONS:
        assert steps[key]["label"].startswith("Liquidity prefilter:"), key
    assert "$5.00" in steps["low_price"]["label"] and "$250,000" in steps["low_dollar_volume"]["label"]


def test_the_capped_cap_is_a_note_step_naming_the_share_and_the_kept_names():
    hygiene = ph.decide({f"T{i}": "locked" for i in range(6)}, scanned=100)
    note = {s["key"]: s for s in _steps(scored=100, hygiene=hygiene)}["price_hygiene_capped"]
    assert note["kind"] == "note" and note["count"] == 6 and note["tickers"] == sorted(hygiene.flagged)
    assert "6.0%" in note["label"] and "5%" in note["label"]


def test_no_note_step_while_the_gates_drop():
    hygiene = ph.decide({"AAA": "locked"}, scanned=100)
    keys = [s["key"] for s in _steps(dropped=hygiene.dropped, scored=99, hygiene=hygiene)]
    assert "price_hygiene_capped" not in keys and "locked" in keys


# ── run_screen end to end ─────────────────────────────────────────────────────

def _bars(closes, start="2024-01-02"):
    closes = [float(c) for c in closes]
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Open": closes, "High": [c * 1.01 for c in closes], "Low": [c * 0.99 for c in closes],
                         "Close": closes, "Volume": [1e6] * len(closes)}, index=idx)


def _clean(n=80):
    return _bars([100 + (i % 3) for i in range(n)])


def _locked():
    return _bars([100 + (i % 3) for i in range(70)] + [50] * 5)


def _preloaded(monkeypatch, frames: dict[str, pd.DataFrame]):
    monkeypatch.setattr(sc, "stale_names", lambda names, ref: set())
    monkeypatch.setattr(sc, "load_bars_many", lambda tickers, now=None: {t: (frames[t], frames[t]) for t in tickers})


def test_a_flagged_name_is_dropped_from_the_board_and_named_in_the_funnel(board, monkeypatch):
    """#147's fake board scans 5 names, so one locked series is 20 % of the scan: over the cap. Nothing drops,
    the name stays on the board and the funnel carries the note that says why."""
    _preloaded(monkeypatch, {t: (_locked() if t == "B" else _clean()) for t in "ABCDE"})
    payload = board.run()
    assert payload["results"] == list("ABCDE"), "20 % flagged is over the cap: nothing drops"
    assert board.stats["price_flags"] == {"locked": ["B"]} and board.stats["price_flags_capped"] is True
    note = {s["key"]: s for s in payload["funnel_steps"]}["price_hygiene_capped"]
    assert note["kind"] == "note" and note["tickers"] == ["B"]
    assert funnel.validate(payload["funnel_steps"]) == []


def test_under_the_cap_the_flagged_name_leaves_the_board_and_is_never_persisted(monkeypatch):
    names = [f"T{i:02d}" for i in range(40)]
    b = Board(monkeypatch, rows=[{"ticker": t, "quote": {}} for t in names])
    _preloaded(monkeypatch, {t: (_locked() if t == "T07" else _clean()) for t in names})
    payload = b.run()
    assert "T07" not in payload["results"] and len(payload["results"]) == 39
    assert b.stats["price_flags"] == {"locked": ["T07"]} and b.stats["price_dropped"] == {"locked": ["T07"]}
    assert b.stats["price_flags_capped"] is False
    assert "T07" not in [r["ticker"] for r in b.persisted[0]], "a dropped name is not frozen by this Fetch"
    step = {s["key"]: s for s in payload["funnel_steps"]}["locked"]
    assert step["count"] == 1 and step["tickers"] == ["T07"] and step["by_design"] is False
    assert funnel.validate(payload["funnel_steps"]) == []
    assert {s["key"] for s in payload["funnel_steps"]} >= {"locked", "candidates"}


def test_a_name_that_could_not_be_scored_is_not_dropped_twice(monkeypatch):
    """A flagged name the scorer already dropped keeps its own reason: the hygiene drop only takes scored rows, so
    the funnel never counts one name twice."""
    names = [f"T{i:02d}" for i in range(40)]
    b = Board(monkeypatch, rows=[{"ticker": t, "quote": {}} for t in names])
    b.behaviour["T07"] = None
    b.reasons["T07"] = "no_edgar_annual"
    _preloaded(monkeypatch, {t: (_locked() if t == "T07" else _clean()) for t in names})
    payload = b.run()
    assert b.stats["price_dropped"] == {} and b.stats["price_flags"] == {"locked": ["T07"]}
    steps = {s["key"]: s for s in payload["funnel_steps"]}
    assert steps["no_edgar_annual"]["tickers"] == ["T07"] and "locked" not in steps
    assert funnel.validate(payload["funnel_steps"]) == []


def test_the_gates_add_no_store_read_and_no_provider_call(monkeypatch):
    """The gates are pure: the scan hands them the bars it already loaded. So a run with a gate firing makes
    exactly the store reads a run with nothing flagged makes — the two runs are counted and compared, because the
    scan reads the store for SPY's reference session and the payload's data date whatever the gates do. A provider
    call would raise ``NetworkAccessAttempted`` (the root conftest) in either run.
    """
    names = [f"T{i:02d}" for i in range(40)]
    frames = {t: (_locked() if t == "T07" else _clean()) for t in names}

    def run(gates_on: bool):
        reads: list[int] = []
        with monkeypatch.context() as m:
            b = Board(m, rows=[{"ticker": t, "quote": {}} for t in names])
            m.setattr(sc, "stale_names", lambda tickers, ref: set())
            m.setattr(sc, "load_bars_many",
                      lambda tickers, now=None: {t: (frames[t], frames[t]) for t in tickers})
            m.setattr(sc.ledger, "d01_last_bars", lambda n: reads.append(1) or {})
            if not gates_on:
                m.setattr(sc.price_hygiene, "evaluate", lambda *a, **k: None)
            payload = b.run()
        return len(reads), b.stats, payload

    gated, stats, payload = run(True)
    plain, plain_stats, plain_payload = run(False)
    assert stats["price_dropped"] == {"locked": ["T07"]} and "T07" not in payload["results"]
    assert plain_stats["price_dropped"] == {} and "T07" in plain_payload["results"]
    assert gated == plain, "the gates read nothing of their own"
