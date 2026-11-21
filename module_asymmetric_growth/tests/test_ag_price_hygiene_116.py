"""#116 step B for Asymmetric Growth: the board screens through its own engine, so the gates are wired at its scan
loop — flag per batch on the bars the batch already read, drop once the whole scan is in, under the cap.

The trap this pins (issue #116, 21 Nov re-measurement): AG's batch preload held only the SPLIT basis, and
``price_hygiene.unexplained_jump`` compares the nominal move against the ADJUSTED series. Passing one frame twice
would make that gate inert, so ``_preload`` reads the returns basis too. No store, no network.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from RevenueChaser.core import funnel, price_hygiene as ph
from RevenueChaser.module_asymmetric_growth import engine


def _rows(closes, start=date(2026, 1, 5), highs=None):
    days = list(pd.bdate_range(start, periods=len(closes)).date)
    highs = highs or [c * 1.01 for c in closes]
    return [{"session_date": d, "open": c, "high": h, "low": c * 0.99, "close": c, "volume": 1e6}
            for d, c, h in zip(days, closes, highs)]


def _walk(n=70):
    return [100.0 + (i % 3) for i in range(n)]


# ── the frames the gates read ─────────────────────────────────────────────────

def test_the_bar_rows_become_the_date_indexed_frame_the_gates_read():
    frame = engine._hygiene_frame(_rows(_walk(5)))
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(frame.index, pd.DatetimeIndex) and len(frame) == 5
    assert frame.index.is_monotonic_increasing
    assert engine._hygiene_frame([]).empty and engine._hygiene_frame(None).empty


def test_a_row_with_no_close_is_left_out_as_the_other_readers_leave_it_out():
    rows = _rows(_walk(5))
    rows[2]["close"] = None
    assert len(engine._hygiene_frame(rows)) == 4


# ── the gates, on both bases ──────────────────────────────────────────────────

def test_a_batch_flags_a_locked_series_by_its_own_reason():
    preload = {"bars": {"LCK": _rows(_walk(65) + [50.0] * 5), "OK": _rows(_walk())},
               "bars_adjusted": {"LCK": _rows(_walk(65) + [50.0] * 5), "OK": _rows(_walk())}}
    assert engine._price_flags(preload) == {"LCK": "locked"}


def test_the_unexplained_jump_gate_stays_live_because_both_bases_are_read():
    """The one gate that needs two frames: a spike the adjusted series repeats and takes back is a bad print, a
    nominal-only jump the adjusted series does not repeat is an action. With one frame passed twice the second
    case would be flagged too — which is what reading only the split basis would have done."""
    spike = _walk(65) + [200.0] + _walk(4)
    action = _walk(65) + [50.5, 51.0, 50.0, 50.5, 51.0]        # the nominal level halves, the returns do not
    preload = {"bars": {"BAD": _rows(spike), "ACT": _rows(action)},
               "bars_adjusted": {"BAD": _rows(spike), "ACT": _rows(_walk(70))}}
    assert engine._price_flags(preload) == {"BAD": "unexplained_jump"}


def test_a_name_with_no_bars_has_no_flag():
    assert engine._price_flags({"bars": {}, "bars_adjusted": {}}) == {}
    assert engine._price_flags({"bars": {"X": []}, "bars_adjusted": {}}) == {}


def test_the_preload_reads_the_returns_basis_beside_the_split_basis(monkeypatch):
    seen: list[str] = []

    def fake_bars(tickers, session, basis="split"):
        seen.append(basis)
        return {}

    monkeypatch.setattr(engine, "_bars_by_ticker", fake_bars)
    monkeypatch.setattr(engine.sec_edgar, "stored_fundamentals_many", lambda t: {})
    monkeypatch.setattr(engine, "themes_for_many", lambda t: {})
    preload = engine._preload(["AAA"], no_fetch=True, session=date(2026, 11, 20))
    assert sorted(seen) == ["split", "total_return"], "one read per basis per batch, never one per name"
    assert "bars" in preload and "bars_adjusted" in preload


def test_the_two_reads_use_the_same_window_and_session(monkeypatch):
    from RevenueChaser.rcdata import read as rcread
    calls: list[tuple] = []
    monkeypatch.setattr(engine, "_price_session", lambda: date(2026, 11, 20))
    monkeypatch.setattr(rcread, "ticker_bars",
                        lambda tickers, start=None, end=None, basis="split":
                        calls.append((tuple(tickers), start, end, basis)) or pd.DataFrame())
    monkeypatch.setattr(engine.sec_edgar, "stored_fundamentals_many", lambda t: {})
    monkeypatch.setattr(engine, "themes_for_many", lambda t: {})
    engine._preload(["AAA"], no_fetch=True)
    assert len(calls) == 2 and {c[3] for c in calls} == {"split", "total_return"}
    assert {c[1] for c in calls} == {date(2026, 11, 20) - timedelta(days=engine.BARS_WINDOW_DAYS)}
    assert {c[2] for c in calls} == {date(2026, 11, 20)}


# ── the funnel ────────────────────────────────────────────────────────────────

def _drops(by_reason=None):
    d = engine._Drops()
    for reason, names in (by_reason or {}).items():
        for t in names:
            d.add(reason, t)
    return d


def test_each_hygiene_reason_is_its_own_drop_step_and_is_not_by_design():
    drops = _drops({k: [f"{k[:3].upper()}{i}" for i in range(2)] for k in ph.REASONS})
    steps = engine._funnel_steps(100, 0, drops, {}, 100 - 2 * len(ph.REASONS))
    assert funnel.validate(steps) == []
    by_key = {s["key"]: s for s in steps}
    for key in ph.REASONS:
        assert by_key[key]["count"] == 2 and by_key[key]["by_design"] is False, key
        assert ph.LABELS[key] in by_key[key]["label"], key


def test_the_tripped_cap_is_a_note_step_that_names_the_share():
    hygiene = ph.decide({f"T{i}": "locked" for i in range(6)}, scanned=100)
    steps = engine._funnel_steps(100, 0, _drops(), {}, 100, hygiene=hygiene)
    assert funnel.validate(steps) == []
    note = {s["key"]: s for s in steps}["price_hygiene_capped"]
    assert note["kind"] == "note" and note["count"] == 6 and "6.0%" in note["label"] and "5%" in note["label"]


# ── the scan, end to end ─────────────────────────────────────────────────────

@pytest.fixture
def scan(monkeypatch, rawstore_tmp_db):
    """The AG scan with the store stubbed out: every name scores a card, and the bars come from ``bars``."""
    def _run(names, bars, adjusted=None):
        from RevenueChaser.core import index_registry
        monkeypatch.setattr(engine._spine, "universe_with_stats",
                            lambda: ([{"ticker": t} for t in names], {}))
        monkeypatch.setattr(engine._spine, "excluded_tickers", lambda: set())
        monkeypatch.setattr(engine._spine, "spine_gics", lambda: {})
        monkeypatch.setattr(engine, "_price_session", lambda: date(2026, 11, 20))
        monkeypatch.setattr(engine, "_preload", lambda t, no_fetch, session=None: {
            "edgar": {}, "quarterly": {}, "themes": {},
            "bars": {k: v for k, v in bars.items() if k in t},
            "bars_adjusted": {k: v for k, v in (adjusted or bars).items() if k in t},
            "session": date(2026, 11, 20)})
        monkeypatch.setattr(engine, "enrich_and_score",
                            lambda ticker, meta, no_fetch=False, spine=None, preload=None: {
                                "ticker": ticker, "sector": "Technology", "total_points": 7, "tier": 2,
                                "themes": [], "tech_breakthrough": False, "signals": [], "flags": []})
        monkeypatch.setattr(engine.earnings_dates, "stored_next_dates", lambda: {})
        monkeypatch.setattr(engine.ownership, "sec13f_totals", lambda: {})
        monkeypatch.setattr(engine.ownership, "shares_outstanding", lambda t: {})
        monkeypatch.setattr(engine.ownership, "split_factors_13f", lambda p: {})
        monkeypatch.setattr(index_registry, "annotate_cards", lambda cards: None)
        from RevenueChaser.module_asymmetric_growth import freeze
        monkeypatch.setattr(freeze, "model_version", lambda: "test")
        return engine.run_asymmetric_growth_hunter(no_fetch=True)
    return _run


def _universe(n=40, locked=("T07",)):
    bars = {}
    for i in range(n):
        t = f"T{i:02d}"
        bars[t] = _rows(_walk(65) + ([50.0] * 5 if t in locked else _walk(5)))
    return [f"T{i:02d}" for i in range(n)], bars


def test_a_flagged_card_leaves_the_board_and_the_funnel_names_it(scan):
    names, bars = _universe()
    result = scan(names, bars)
    tickers = [c["ticker"] for c in result["cards"]]
    assert "T07" not in tickers and len(tickers) == 39
    step = {s["key"]: s for s in result["funnel_steps"]}["locked"]
    assert step["count"] == 1 and step["tickers"] == ["T07"] and step["by_design"] is False
    assert funnel.validate(result["funnel_steps"]) == []
    assert result["summary"]["scanned"] == 39, "the summary counts the cards the board shows"


def test_above_the_cap_every_flagged_card_stays_and_the_board_says_why(scan):
    names, bars = _universe(n=10, locked=("T03", "T08"))        # 2 of 10: over the 5 % cap
    result = scan(names, bars)
    assert [c["ticker"] for c in result["cards"]] == sorted(names)
    note = {s["key"]: s for s in result["funnel_steps"]}["price_hygiene_capped"]
    assert note["kind"] == "note" and note["tickers"] == ["T03", "T08"]
    assert "locked" not in {s["key"] for s in result["funnel_steps"]}
    assert funnel.validate(result["funnel_steps"]) == []


def test_a_dropped_name_never_dates_the_board(scan):
    """``data_as_of`` is the newest session among the cards the board SHOWS (#380 S4): the dropped name's own
    newer bar must not date a board it is not on."""
    names, bars = _universe()
    bars["T07"] = _rows(_walk(65) + [50.0] * 6)          # one session further than every clean name
    result = scan(names, bars)
    assert "T07" not in [c["ticker"] for c in result["cards"]]
    assert result["data_as_of"] == max(engine._bar_day(r) for r in bars["T00"]).isoformat()


def test_a_clean_scan_runs_the_gates_over_both_bases_and_adds_no_step(scan, monkeypatch):
    """Nothing is flagged, so the funnel gains no hygiene row at all — and every name still reached the gates with
    BOTH of its frames, which is what makes a clean board evidence rather than a gate that never ran."""
    names, bars = _universe(locked=())
    adjusted = {t: _rows(_walk(75)) for t in names}        # a different length, so the two frames cannot be one
    seen: list[tuple[int, int]] = []
    real = engine.price_hygiene.evaluate
    monkeypatch.setattr(engine.price_hygiene, "evaluate",
                        lambda nominal, adj=None: seen.append((len(nominal), 0 if adj is None else len(adj)))
                        or real(nominal, adj))
    result = scan(names, bars, adjusted=adjusted)
    assert len(seen) == 40 and set(seen) == {(70, 75)}, "every name is gated on the nominal AND the returns basis"
    keys = {s["key"] for s in result["funnel_steps"]}
    assert not (keys & (set(ph.REASONS) | {"price_hygiene_capped"}))
    assert len(result["cards"]) == 40 and funnel.validate(result["funnel_steps"]) == []
