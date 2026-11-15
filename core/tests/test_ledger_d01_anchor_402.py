"""U1 (#402, K8b's SPY part): the SPY anchor of the Swing and Fundamentals freeze reads D01 first.

On 2026-10-14 RC-Daily-Bars had SPY's session bar in ``price_bars_daily``, but the freeze read SPY from the old
``swing_ohlc`` cache, whose refetch had failed, and refused both boards. Offline; the store is a temp DuckDB.
"""
from __future__ import annotations

from datetime import date

from RevenueChaser.core import calendar as cal
from RevenueChaser.core import ledger, rawstore
from RevenueChaser.core.tests.d01_seed import write_d01

D = date(2026, 10, 2)          # a Friday and a normal session


def _close_plus(minutes, day=D):
    return cal.session_close(day).timestamp() + minutes * 60




def _seed_d01(ticker, last_day, fetched_at):
    write_d01([
        {"ticker": ticker, "session_date": date.fromisoformat(d), "open": 1.0, "high": 2.0, "low": 0.5,
         "close": 1.5, "adj_close": None, "volume": 100.0, "split_ratio": None, "adj_source": None,
         "source": "uw", "fetched_at": fetched_at, "run_id": "seed", "run_at": fetched_at}
        for d in ("2026-09-30", "2026-10-01", last_day)])




def test_with_no_spy_in_the_cache_at_all_d01_still_anchors_the_board(rawstore_tmp_db):
    """Common review K8b's red test: a store with only ``price_bars_daily`` for SPY still freezes."""
    _seed_d01("SPY", "2026-10-02", _close_plus(40))
    assert ledger.spy_anchor_problem(D) is None






def test_a_d01_bar_later_than_the_session_is_not_the_session(rawstore_tmp_db):
    _seed_d01("SPY", "2026-10-05", _close_plus(40, date(2026, 10, 5)))
    assert ledger.d01_has_session(D, "SPY") is False


def test_d01_last_bars_has_the_shape_of_last_bars(rawstore_tmp_db):
    _seed_d01("SPY", "2026-10-02", _close_plus(40))
    _seed_d01("AAA", "2026-10-01", 123.0)
    got = ledger.d01_last_bars([" spy", "AAA", "MISSING", None])
    # The served file stamps every bar with its one build (#642 PR 6): the newest write, SPY's.
    assert got == {"SPY": ("2026-10-02", _close_plus(40)), "AAA": ("2026-10-01", _close_plus(40))}
    assert ledger.d01_last_bars([]) == {}


def test_no_price_file_reads_as_no_d01_bars(isolate_rawstore):
    """A store without prices.duckdb (or without the table) is the old behaviour, never an error."""
    assert ledger.d01_last_bars(["SPY"]) == {}
    assert ledger.d01_has_session(D, "SPY") is False




