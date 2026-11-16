"""core.baselines — the derived ``forecast_baselines`` writer (#25 HR-1). Offline; the store is a temp DuckDB.

The fixture: the universe froze on Tuesday 2026-09-01 (``D``). Every member's 30-day window is the sessions from
2026-09-02 to Thursday 2026-10-01, its 90-day window the sessions to Monday 2026-11-30. The bars start on 2026-07-01,
because the trailing volatility needs the 21 sessions ending at ``D``.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta, timezone

import pytest

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.core import baselines, calendar as cal, ledger, outcomes, prices, rawstore
from RevenueChaser.core.tests.d01_seed import drop_d01, write_d01

D = date(2026, 9, 1)                      # the freeze date (a Tuesday)
END30 = date(2026, 10, 1)                 # the last session on or before D + 30 days
LAST_BAR = date(2026, 10, 9)
VOL_START = date(2026, 7, 1)              # enough sessions before D for the 21-bar vol window
NOW = datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc)     # 19:00 New York: 2026-10-09 is complete
LATER = datetime(2027, 1, 15, 23, 0, tzinfo=timezone.utc)   # past window_end(D, 90) = 2026-11-30


def _sessions(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if cal.is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def _bar(ticker, d, o, h, low, c):
    return {"ticker": ticker, "session_date": d, "open": o, "high": h, "low": low, "close": c,
            "adj_close": None, "volume": 1000.0, "split_ratio": None, "adj_source": None, "source": "yfinance",
            "fetched_at": 0.0, "run_id": "seed", "run_at": 0.0}


def _series(ticker="AAA", *, mfe=0.10, mae=-0.05, amp=0.0, last=LAST_BAR):
    """Bars from 2026-07-01 to ``last``. Up to ``D`` the close is 100 (or ``100*(1+amp)`` on odd sessions, which
    gives a volatility that rises with ``amp``); every session after ``D`` opens at 100 with a high of
    ``100*(1+mfe)`` and a low of ``100*(1+mae)``, so the outcome is exactly ``mfe`` / ``mae`` from a reference of
    100. Nothing jumps by the split threshold."""
    rows = []
    for i, d in enumerate(_sessions(VOL_START, last)):
        if d <= D:
            c = 100.0 * (1 + (amp if i % 2 else 0.0))
            rows.append(_bar(ticker, d, c, c, c, c))
        else:
            rows.append(_bar(ticker, d, 100.0, 100.0 * (1 + mfe), 100.0 * (1 + mae), 100.0))
    return rows


class Clock:
    """A monotone change-capture clock, so a test says which day's membership the snapshot read sees."""

    def __init__(self, start: float):
        self.t = float(start)

    def tick(self) -> float:
        self.t += 1.0
        return self.t


@pytest.fixture
def clock(monkeypatch):
    """The universe is written an hour before ``D`` ended: ``universe_at(D)`` finds it."""
    c = Clock(baselines.day_end(D) - 3600)
    return c


def _seed(rows, *, tickers=None):
    """The bars, and the universe of those names (or ``tickers``) as ``D``'s membership."""
    write_d01(list(rows))
    names = tickers if tickers is not None else sorted({r["ticker"] for r in rows})
    universe_store.put([{"ticker": t, "name": t, "market_cap": 1e9} for t in names])


def _dividend(ticker, day, value):
    return {"ticker": ticker, "ex_date": day, "action": "dividend", "value": value, "session_date": day,
            "source": "yfinance", "fetched_at": 0.0, "run_id": "seed", "run_at": 0.0}


def _vols(names, basis):
    """The trailing vol of each name on ``D``, read on ``basis`` through the window ``baselines`` reads."""
    frame = prices.daily_bars_bases(names, start=D - timedelta(days=baselines.VOL_LOOKBACK_DAYS),
                                    end=cal.latest_complete_session(NOW))[basis]
    by = baselines._by_ticker(frame)
    return [baselines.realised_vol([b["close"] for b in by.get(t, []) if b["session_date"] <= D]) for t in names]


def _freeze(subjects, *, source="swing", day=D):
    ledger.write_picks(source, source, [{"subject": s, "rank": i + 1} for i, s in enumerate(subjects)],
                       model_version="v1+abcd", forecast_date=day, run_id="freeze1")


def _rows(day=D, basis=None):
    sql = "SELECT * FROM forecast_baselines WHERE forecast_date = ?"
    params = [day]
    if basis is not None:
        sql += " AND basis = ?"
        params.append(basis)
    return rawstore.query(sql + " ORDER BY horizon_days, basis", params, db="forecast")


def _row(basis="universe", h=30, day=D):
    got = [r for r in _rows(day, basis) if r["horizon_days"] == h]
    assert len(got) == 1, f"{basis}/{h}: {got}"
    return got[0]


# ── the table ────────────────────────────────────────────────────────────────

def test_manifest_entry_is_a_derived_upsert_keyed_by_date_horizon_and_basis():
    spec = rawstore.MANIFEST["forecast_baselines"]
    assert spec["key"] == ["forecast_date", "horizon_days", "basis"]
    assert spec["write"] == "upsert" and spec["history_mode"] == "latest_cache"
    assert rawstore._db_of("forecast_baselines") == "forecast" and not spec.get("history")
    cols = {c.split()[0] for c in spec["columns"] if not c.startswith("PRIMARY KEY")}
    assert {"n", "ge20", "ge10", "ge5", "mfe_mean", "mae_mean", "vol_lo", "vol_hi", "status",
            "computed_at", "model_version", "run_id"} <= cols


# ── red-first rules: the two baselines ───────────────────────────────────────





def _change(ticker, change, day, kind="stock"):
    return {"ticker": ticker, "kind": kind, "change": change, "reason": "test", "as_of": day, "run_id": "b"}


def test_the_dated_universe_is_each_names_stays_in_the_list(rawstore_tmp_db):
    """``my_universe_changes`` read as spans: a name that left and came back has two, and a ``kinds`` filter keeps
    the ETFs out."""
    universe_store.changes([
        _change("AAA", "entered", date(2026, 11, 5)), _change("BBB", "entered", date(2026, 11, 5)),
        _change("SPY", "entered", date(2026, 11, 5), kind="etf"),
        _change("BBB", "left", date(2026, 11, 9)), _change("BBB", "entered", date(2026, 11, 12))])
    from RevenueChaser.rcdata import read
    got = [(s["ticker"], s["entered_on"], s["left_on"]) for s in read.my_universe_spans(("stock",))]
    assert got == [("AAA", date(2026, 11, 5), None), ("BBB", date(2026, 11, 5), date(2026, 11, 9)),
                   ("BBB", date(2026, 11, 12), None)]
    assert [s["ticker"] for s in read.my_universe_spans()] == ["AAA", "BBB", "BBB", "SPY"]


def test_universe_at_is_the_membership_at_the_end_of_the_day():
    spans = [{"ticker": "AAA", "entered_on": date(2026, 11, 5), "left_on": None},
             {"ticker": "BBB", "entered_on": date(2026, 11, 5), "left_on": date(2026, 11, 9)}]
    assert baselines.universe_at(date(2026, 11, 4), spans) == []                # before the first build
    assert baselines.universe_at(date(2026, 11, 8), spans) == ["AAA", "BBB"]
    assert baselines.universe_at(date(2026, 11, 9), spans) == ["AAA"]           # left that day: out at its end


def test_a_name_that_has_left_since_still_counts_on_the_day_it_was_in(rawstore_tmp_db):
    """No survivorship: the baseline of ``D`` is ``D``'s list. BBB left after ``D`` and counts; CCC entered after
    ``D`` and does not; the fund is no stock and does not; DDD was in on ``D`` but the store holds no bar for it, so
    it is a member (``members``) outside ``n``."""
    write_d01(_series("AAA") + _series("BBB", mfe=0.30) + _series("CCC") + _series("SPY"))
    first = D - timedelta(days=30)
    universe_store.changes([_change("AAA", "entered", first), _change("BBB", "entered", first),
                            _change("DDD", "entered", first), _change("SPY", "entered", first, kind="etf"),
                            _change("BBB", "left", D + timedelta(days=5)),
                            _change("CCC", "entered", D + timedelta(days=1))])
    _freeze(["AAA"])
    out = baselines.run(now=NOW, run_id="r1")
    assert (out["no_snapshot"], out["members"]) == (0, 3)
    row = _row("universe", 30)
    assert row["n"] == 2 and row["ge20"] == 1 and row["ge10"] == 2


def test_a_freeze_date_without_a_universe_snapshot_writes_zero_members(rawstore_tmp_db, clock):
    """Before the store recorded membership there is no snapshot: the rows say n = 0 rather than quietly using
    today's list, and the run counts the date as one without a snapshot."""
    write_d01(_series("AAA"))
    clock.t = baselines.day_end(D) + 86400                       # membership is first recorded after D
    universe_store.put([{"ticker": "AAA"}])
    _freeze(["AAA"])
    out = baselines.run(now=NOW, run_id="r1")
    assert out["no_snapshot"] == 1
    assert _rows() and {r["n"] for r in _rows()} == {0}










# ── red-first rules: what is not measured ────────────────────────────────────







# ── the nightly ──────────────────────────────────────────────────────────────

def test_a_rerun_upserts_the_same_rows_and_adds_none(rawstore_tmp_db, clock):
    _seed(_series("AAA") + _series("BBB", amp=0.01))
    _freeze(["AAA"])
    first = baselines.run(now=NOW, run_id="r1")
    before = _rows()
    second = baselines.run(now=NOW, run_id="r2", full=True)
    after = _rows()
    assert len(before) == len(after) == first["rows"] == second["rows"]
    assert {r["run_id"] for r in after} == {"r2"}
    assert [{k: v for k, v in r.items() if k != "run_id"} for r in after] == \
           [{k: v for k, v in r.items() if k != "run_id"} for r in before]


def test_the_nightly_skips_a_date_whose_windows_have_ended(rawstore_tmp_db, clock):
    """Both windows have ended *and* the store holds a bar past their ends: the rows are final from then on."""
    _seed(_series("AAA", last=date(2026, 12, 1)))
    _freeze(["AAA"])
    baselines.run(now=NOW, run_id="r1")
    assert _row(h=90)["status"] == baselines.OPEN
    closing = baselines.run(now=LATER, run_id="r2")              # the run that closes both windows
    assert closing["dates"] == 1
    assert {_row(h=h)["status"] for h in baselines.HORIZONS} == {baselines.CLOSED}
    assert baselines.run(now=LATER, run_id="r3")["dates"] == 0    # final: skipped
    # The 30-day rows were already closed by r1, so r2 left them alone and rewrote the 90-day ones.
    assert {r["run_id"] for r in _rows() if r["horizon_days"] == 30} == {"r1"}
    assert {r["run_id"] for r in _rows() if r["horizon_days"] == 90} == {"r2"}
    full = baselines.run(now=LATER, run_id="r4", full=True)
    assert full["dates"] == 1 and {r["run_id"] for r in _rows()} == {"r4"}


def test_a_row_stays_open_until_the_store_holds_a_bar_on_or_after_its_window_end(rawstore_tmp_db, clock):
    """Daily Bars failed for the night END30 passed: the calendar says the 30-day window has ended, but the store's
    newest bar is still 2026-09-25. A row closed there would be frozen on a short window — ``_open_rows`` never
    recomputes a closed row — so it stays open until a bar on or after the end is stored."""
    _seed(_series("AAA", last=date(2026, 9, 25)))
    _freeze(["AAA"])
    first = baselines.run(now=NOW, run_id="r1")                  # 2026-10-09: past END30 on the clock alone
    assert first["status"] == {baselines.OPEN: 22}
    assert {_row(h=h)["status"] for h in baselines.HORIZONS} == {baselines.OPEN}
    baselines.run(now=NOW, run_id="r2")                          # still no bar at the window end: still open
    assert {_row(h=h)["status"] for h in baselines.HORIZONS} == {baselines.OPEN}
    _seed(_series("AAA", last=END30))                            # the backfill reaches the window's last session
    baselines.run(now=NOW, run_id="r3")
    assert _row(h=30)["status"] == baselines.CLOSED
    assert _row(h=90)["status"] == baselines.OPEN                # END90 has no bar yet


def test_the_nightly_recomputes_only_the_horizon_still_open(rawstore_tmp_db, clock):
    """At NOW the 30-day window has ended: its eleven rows are final, and the next nightly rewrites the 90-day
    eleven alone (11 rows, not 22) — a closed row is never rewritten, and its numbers cannot change."""
    late = date(2026, 10, 20)
    _seed(_series("AAA", last=late) + _series("BBB", amp=0.01, last=late))
    _freeze(["AAA"])
    baselines.run(now=NOW, run_id="r1")                          # 30-day rows close here, 90-day rows stay open
    assert {_row(h=30)["run_id"]} == {"r1"}
    second = baselines.run(now=datetime(2026, 10, 20, 23, 0, tzinfo=timezone.utc), run_id="r2")
    assert (second["dates"], second["rows"]) == (1, 11) and second["status"] == {baselines.OPEN: 11}
    assert {r["run_id"] for r in _rows() if r["horizon_days"] == 30} == {"r1"}
    assert {r["run_id"] for r in _rows() if r["horizon_days"] == 90} == {"r2"}




def test_dry_run_computes_and_writes_nothing(rawstore_tmp_db, clock):
    _seed(_series("AAA"))
    _freeze(["AAA"])
    out = baselines.run(now=NOW, run_id="r1", write=False)
    assert out["rows"] >= 1 and out["written"] == 0 and out["dry_run"] is True
    assert rawstore.count("forecast_baselines") == 0




def test_a_ledger_with_no_pick_has_no_baseline(rawstore_tmp_db, clock):
    _seed(_series("AAA"))
    out = baselines.run(now=NOW, run_id="r1")
    assert (out["dates"], out["rows"], rawstore.count("forecast_baselines")) == (0, 0, 0)


# ── guards (green from the start; each killed by its mutation) ──────────────

def test_the_writer_never_writes_the_ledger(rawstore_tmp_db, clock, monkeypatch):
    _seed(_series("AAA"))
    _freeze(["AAA"])
    written = []
    real = rawstore.write_rows

    def spy(name, rows):
        if name == "forecast_ledger":
            raise AssertionError("forecast_baselines must never write forecast_ledger")
        written.append(name)
        return real(name, rows)

    monkeypatch.setattr(rawstore, "write_rows", spy)
    for name in ("update_columns", "replace_all", "delete", "clear", "execute"):
        monkeypatch.setattr(rawstore, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError(name)))
    monkeypatch.setattr(ledger, "write_picks", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ledger")))
    baselines.run(now=NOW, run_id="r1", full=True)
    assert set(written) == {"forecast_baselines"}




# ── the pieces the board will read ──────────────────────────────────────────

def test_realised_vol_is_the_annualised_stdev_of_the_last_20_log_returns():
    closes = [100.0] * 20 + [110.0]
    want = statistics.stdev([0.0] * 19 + [math.log(1.1)]) * math.sqrt(252)
    assert baselines.realised_vol(closes) == pytest.approx(want)
    assert baselines.realised_vol([5.0] + closes) == pytest.approx(want)      # only the last 21 closes count


@pytest.mark.parametrize("closes", [
    [],
    [100.0] * 20,                                          # 20 closes = 19 returns
    [100.0] * 20 + [0.0],                                  # a zero price has no log return
    [100.0] * 20 + [float("nan")],
])
def test_realised_vol_is_none_when_it_cannot_be_measured(closes):
    assert baselines.realised_vol(closes) is None


def test_a_decile_is_matched_by_its_own_boundaries():
    """``vol_lo`` inclusive, ``vol_hi`` exclusive, NULL at either end: a pick's vol lands in exactly one decile."""
    cuts = [1.0, 2.0, 3.0]
    assert [baselines.basis_of(v, cuts) for v in (0.5, 1.0, 2.5, 3.0, 9.0)] == \
        ["vol_decile_1", "vol_decile_2", "vol_decile_3", "vol_decile_4", "vol_decile_4"]
    assert baselines.vol_range(cuts, 1) == (None, 1.0)
    assert baselines.vol_range(cuts, 2) == (1.0, 2.0)
    assert baselines.vol_range(cuts, 4) == (3.0, None)


def test_decile_cuts_split_a_hundred_evenly_spaced_peers_into_ten_groups_of_ten():
    cuts = baselines.decile_cuts([float(i) for i in range(100)])
    assert len(cuts) == baselines.DECILES - 1
    counts = [0] * 10
    for i in range(100):
        counts[int(baselines.basis_of(float(i), cuts).rsplit("_", 1)[1]) - 1] += 1
    assert counts == [10] * 10
    assert baselines.decile_cuts([]) == []
