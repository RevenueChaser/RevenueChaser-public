"""Daily price bars (#156): the nightly writer, the fill, the read path and helpers.

Every test is offline: a fake UW client and a fake ``yf.download`` stand in at the seams,
and the clock is passed explicitly. See spec156.md §9-§10.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.core import calendar, job_lock, prices, rawstore
from RevenueChaser.core.providers.result import ProviderResult
from RevenueChaser.core.tests.d01_seed import write_d01

UTC = timezone.utc
NOW = datetime(2026, 10, 8, 20, 35, tzinfo=UTC)      # 16:35 EDT, after the 16:30 complete edge
LATEST = date(2026, 10, 8)

_YF_FIELDS = ["Open", "High", "Low", "Close", "Adj Close", "Volume",
              "Dividends", "Stock Splits", "Capital Gains"]


# ── fakes ────────────────────────────────────────────────────────────────────

class FakeUW:
    def __init__(self, bars=None, fail=(), verify_ok=True):
        self._bars = dict(bars or {})
        self._fail = set(fail)
        self._calls = 0
        self._failed = 0
        self.breaker_open = False
        self.auth_error = None
        self.verify_ok = verify_ok
        self.requests: list[tuple[str, int]] = []
        self.on_call = None

    def ohlc_daily_result(self, ticker, days=500):
        self._calls += 1
        self.requests.append((ticker, days))
        if callable(self.on_call):
            self.on_call(self, ticker)
        if ticker in self._fail:
            self._failed += 1
            return ProviderResult("failed", [], {"status": 500}, f"/stock/{ticker}/ohlc/1d")
        return ProviderResult("ok", [dict(r) for r in self._bars.get(ticker, [])])

    def health(self):
        return {"calls": self._calls, "failed": self._failed, "breaker_open": self.breaker_open,
                "auth_error": self.auth_error, "failures": [], "skipped_calls": 0}

    def verify(self):
        return (self.verify_ok, None if self.verify_ok else "missing key")


def yf_row(close, adj=None, volume=1000.0, o=None, h=None, low=None,
           div=None, split=None, gain=None):
    return {"Open": close if o is None else o, "High": close if h is None else h,
            "Low": close if low is None else low, "Close": close,
            "Adj Close": close if adj is None else adj, "Volume": volume,
            "Dividends": div, "Stock Splits": split, "Capital Gains": gain}


def make_frame(rows_by_ticker):
    dates = sorted({d for by in rows_by_ticker.values() for d in by})
    cols = {}
    for t, by in rows_by_ticker.items():
        for f in _YF_FIELDS:
            cols[(t, f)] = [by.get(d, {}).get(f) for d in dates]
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    return pd.DataFrame(cols, index=index)


class FakeDownload:
    def __init__(self, rows_by_ticker=None):
        self.rows = dict(rows_by_ticker or {})
        self.calls: list[tuple] = []
        self.raise_all = False

    def __call__(self, tickers, **kw):
        self.calls.append((list(tickers), dict(kw)))
        if self.raise_all:
            raise RuntimeError("download failed")
        subset = {t: self.rows[t] for t in tickers if t in self.rows}
        if not subset:
            return pd.DataFrame()
        return make_frame(subset)


# ── store helpers ────────────────────────────────────────────────────────────

def bar_row(ticker, d, close=1.0, source="yfinance", volume=1000.0, adj_close=None,
            adj_source=None, fetched_at=0.0, run_id="seed", run_at=0.0, ohlc=None):
    dd = d if isinstance(d, date) else date.fromisoformat(d)
    o, h, low = ohlc if ohlc else (close, close, close)
    return {"ticker": ticker, "session_date": dd, "open": o, "high": h, "low": low,
            "close": close, "adj_close": adj_close, "volume": volume, "split_ratio": None,
            "adj_source": adj_source, "source": source, "fetched_at": fetched_at,
            "run_id": run_id, "run_at": run_at}










def session_back(latest: date, n: int) -> date:
    d = latest
    count = 0
    while count < n:
        d -= timedelta(days=1)
        if calendar.is_trading_day(d):
            count += 1
    return d


# ── T1-T12, T17-T20: the nightly writer ──────────────────────────────────────



































# ── T13-T14: the read formulas ───────────────────────────────────────────────

def _t13_bars():
    ev = datetime(2026, 3, 2, 21, 35, tzinfo=UTC).timestamp()
    def b(d, c, v):
        return {"ticker": "T", "session_date": date.fromisoformat(d), "open": c, "high": c,
                "low": c, "close": c, "adj_close": None, "volume": v, "split_ratio": None,
                "adj_source": None, "source": "uw", "fetched_at": ev, "run_id": "r", "run_at": ev}
    return [b("2026-03-02", 100.0, 1000.0), b("2026-03-03", 102.0, 1000.0),
            b("2026-03-04", 51.0, 2000.0), b("2026-03-05", 50.5, 2000.0)]


def _t13_actions(**kw):
    ev = datetime(2026, 3, 4, 21, 35, tzinfo=UTC).timestamp()
    return [
        {"ticker": "T", "ex_date": date(2026, 3, 4), "action": "split", "value": 2.0,
         "session_date": date(2026, 3, 4), "source": "yfinance", "fetched_at": ev,
         "run_id": "r", "run_at": ev},
        {"ticker": "T", "ex_date": date(2026, 3, 5), "action": "dividend", "value": 0.5,
         "session_date": date(2026, 3, 5), "source": "yfinance",
         "fetched_at": datetime(2026, 3, 5, 21, 35, tzinfo=UTC).timestamp(),
         "run_id": "r", "run_at": ev},
    ]


def test_t13_read_formulas_nominal_and_adjusted():
    bars, actions = _t13_bars(), _t13_actions()
    nominal = prices.apply_events(bars, actions, "nominal")
    assert [round(r["close"], 10) for r in nominal] == [50.0, 51.0, 51.0, 50.5]
    assert [round(r["volume"], 10) for r in nominal] == [2000.0, 2000.0, 2000.0, 2000.0]
    adj = prices.apply_events(bars, actions, "adjusted")
    assert [round(r["close"], 10) for r in adj] == [
        49.5098039216, 50.5, 50.5, 50.5]


def test_t14_split_and_amount_gating():
    ev = datetime(2026, 3, 4, 21, 35, tzinfo=UTC).timestamp()
    def b(d, c):
        return {"ticker": "T", "session_date": date.fromisoformat(d), "open": c, "high": c,
                "low": c, "close": c, "adj_close": None, "volume": 1000.0, "split_ratio": None,
                "adj_source": None, "source": "uw", "fetched_at": ev, "run_id": "r", "run_at": ev}
    bars = [b("2026-02-26", 48.0), b("2026-02-27", 49.0), b("2026-03-04", 51.0)]
    actions = [
        {"ticker": "T", "ex_date": date(2026, 3, 4), "action": "split", "value": 2.0,
         "session_date": date(2026, 3, 4), "source": "yfinance", "fetched_at": ev,
         "run_id": "r", "run_at": ev},
        {"ticker": "T", "ex_date": date(2026, 2, 27), "action": "dividend", "value": 1.0,
         "session_date": date(2026, 2, 27), "source": "yfinance",
         "fetched_at": datetime(2026, 2, 27, 21, 35, tzinfo=UTC).timestamp(),
         "run_id": "r", "run_at": ev}]

    nominal = {r["session_date"]: r["close"] for r in prices.apply_events(bars, actions, "nominal")}
    assert round(nominal[date(2026, 2, 27)], 10) == 49.0      # fetched after the split open
    adj = {r["session_date"]: r["close"] for r in prices.apply_events(bars, actions, "adjusted")}
    assert round(adj[date(2026, 2, 26)], 10) == 47.5        # 48 × (1 − 0.5/48), gated
    assert round(adj[date(2026, 2, 26)], 6) != 47.0         # not 1 − 1/48


def test_t13_daily_bars_filters_after_factors(rawstore_tmp_db):
    ev = datetime(2026, 3, 2, 21, 35, tzinfo=UTC).timestamp()
    write_d01([
        {"ticker": "T", "session_date": date(2026, 3, 4), "open": 51.0, "high": 51.0,
         "low": 51.0, "close": 51.0, "adj_close": None, "volume": 2000.0, "split_ratio": None,
         "adj_source": None, "source": "uw", "fetched_at": ev, "run_id": "r", "run_at": ev}], [
        {"ticker": "T", "ex_date": date(2026, 3, 4), "action": "split", "value": 2.0,
         "session_date": date(2026, 3, 4), "source": "yfinance", "fetched_at": ev,
         "run_id": "r", "run_at": ev}])
    df = prices.daily_bars(["T"], basis="nominal", start=date(2026, 3, 4), end=date(2026, 3, 4))
    assert list(df["close"]) == [51.0]
    with pytest.raises(ValueError):
        prices.daily_bars(["T"], basis="bogus")


# ── T15-T16: the fill ────────────────────────────────────────────────────────





# ── T21-T24: diagnostics, outage, lock, calendar ─────────────────────────────









# ── scope helper ─────────────────────────────────────────────────────────────



# ── review follow-ups (coordinator review of the DeepSeek build) ─────────────

def test_an_amount_ex_on_or_after_the_split_is_never_divided_by_it():
    """§9.4: ``a' = a ÷ Π r`` only over splits with ``ex_div < e`` (and ``fetched_at_div < T(e)``)."""
    early = datetime(2026, 3, 3, 21, 35, tzinfo=UTC).timestamp()     # before the split's ex-date open
    def b(d, c):
        return {"ticker": "T", "session_date": date.fromisoformat(d), "open": c, "high": c,
                "low": c, "close": c, "adj_close": None, "volume": 1000.0, "split_ratio": None,
                "adj_source": None, "source": "uw", "fetched_at": early, "run_id": "r", "run_at": early}
    bars = [b("2026-03-05", 50.0), b("2026-03-06", 50.0)]
    actions = [
        {"ticker": "T", "ex_date": date(2026, 3, 4), "action": "split", "value": 2.0,
         "session_date": date(2026, 3, 4), "source": "yfinance", "fetched_at": early,
         "run_id": "r", "run_at": early},
        {"ticker": "T", "ex_date": date(2026, 3, 6), "action": "dividend", "value": 0.5,
         "session_date": date(2026, 3, 6), "source": "yfinance", "fetched_at": early,
         "run_id": "r", "run_at": early}]
    adj = {r["session_date"]: r["close"] for r in prices.apply_events(bars, actions, "adjusted")}
    assert round(adj[date(2026, 3, 5)], 10) == 49.5          # 50 × (1 − 0.5/50), not 1 − 0.25/50






# ── code review B1/B2 and test gaps G1-G4 (arch_reviews/2026-10-09_156_slice_a_code_review.md) ──

_REF = {"SPY": {"2026-03-02": yf_row(600.0), "2026-03-03": yf_row(601.0)},
        "^GSPC": {"1990-01-02": yf_row(350.0), "2026-03-03": yf_row(5000.0)}}






def test_g1_an_amount_fetched_after_the_split_is_not_divided():
    after = datetime(2026, 3, 5, 21, 35, tzinfo=UTC).timestamp()
    bar = {"ticker": "T", "session_date": date(2026, 2, 26), "open": 48.0, "high": 48.0, "low": 48.0,
           "close": 48.0, "adj_close": None, "volume": 1.0, "split_ratio": None, "adj_source": None,
           "source": "yfinance", "fetched_at": after, "run_id": "r", "run_at": after}
    actions = [
        {"ticker": "T", "ex_date": date(2026, 3, 4), "action": "split", "value": 2.0, "fetched_at": after},
        {"ticker": "T", "ex_date": date(2026, 2, 27), "action": "dividend", "value": 1.0, "fetched_at": after}]
    adj = prices.apply_events([bar], actions, "adjusted")
    assert round(adj[0]["close"], 10) == 47.0             # 48 × (1 − 1/48): the amount is already post-split


def test_g2_daily_bars_window_uses_a_c_prev_outside_it(rawstore_tmp_db):
    ev = datetime(2026, 3, 5, 21, 35, tzinfo=UTC).timestamp()
    write_d01([bar_row("T", "2026-03-03", close=40.0, fetched_at=ev),
               bar_row("T", "2026-03-04", close=50.0, fetched_at=ev)], [
        {"ticker": "T", "ex_date": date(2026, 3, 5), "action": "dividend", "value": 1.0,
         "session_date": date(2026, 3, 5), "source": "yfinance", "fetched_at": ev, "run_id": "r",
         "run_at": ev}])
    df = prices.daily_bars(["T"], basis="adjusted", start=date(2026, 3, 3), end=date(2026, 3, 3))
    assert [round(x, 10) for x in df["close"]] == [39.2]    # C_prev is 03-04's 50, not 03-03's 40








def test_n4_a_bare_string_is_one_ticker(rawstore_tmp_db):
    write_d01([bar_row("SPY", "2026-10-07", close=600.0)])
    assert list(prices.daily_bars("SPY")["ticker"]) == ["SPY"]


# ── re-review of 5428edb: G6-G8, N1/N11, N6 (arch_reviews/2026-10-09_156_slice_a_rereview_5428edb.md) ──



ARRIVED = datetime(2026, 10, 8, 13, 45, tzinfo=UTC).timestamp()


















def test_n11b_a_zero_c_prev_skips_the_event_instead_of_crashing():
    bars = [bar_row("T", "2026-03-02", close=50.0), bar_row("T", "2026-03-03", close=0.0),
            bar_row("T", "2026-03-04", close=49.5)]
    actions = [{"ticker": "T", "ex_date": date(2026, 3, 4), "action": "dividend", "value": 0.5,
                "fetched_at": 0.0}]
    adj = prices.apply_events(bars, actions, "adjusted")
    assert adj.attrs["skipped_events"] == 1




# ── prices.duckdb (#156, avo 2026-10-09) ─────────────────────────────────────

def _in_file(db: str, sql: str) -> list[tuple]:
    with rawstore.connect(read_only=True, db=db) as conn:
        return conn.execute(sql).fetchall()




# ── Data Health (#124 S4): the typed numbers the note is derived from ────────



