"""L5 (#377): a Refresh reads its names from the recorded history, not the 13F meta.

A LEAPS Fetch resolves names through the UW screener and records them with every footprint
(``leaps_footprint_history``). A ticker the 13F meta does not carry would lose its name on Refresh; the last
recorded session snapshot (the K2 readers, ``core/history``) is the source, with the 13F meta as the fallback.
"""
from datetime import date, datetime, timezone

from RevenueChaser.core import rawstore
from RevenueChaser.core.providers.result import ProviderResult
from RevenueChaser.module_leaps import engine
from RevenueChaser.module_leaps.scan import scan_leaps, scan_leaps_cached

TODAY = date(2026, 10, 6)
COMPLETE = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc).timestamp()
FAR = "2027-12-17"


class _UW:
    """A UW double whose screener carries both the plain and the outcome-carrying read."""
    auth_error = None

    def __init__(self, oi):
        self.oi = oi
        self.calls = self.failed = 0

    def health(self):
        return {"calls": self.calls, "failed": self.failed, "auth_error": None, "failures": [],
                "breaker_open": False, "skipped_calls": 0}

    def option_trades(self, **kw):
        return []

    def screener_batch(self, tickers):
        return {t: {"full_name": f"{t} OLD"} for t in tickers}

    def screener_batch_result(self, tickers):
        return ProviderResult("ok", {t: {"full_name": f"{t} NEW"} for t in tickers})

    def oi_per_expiry(self, ticker, date=None):
        self.calls += 1
        call, put = self.oi.get(ticker, (0, 0))
        return [{"expiry": FAR, "call_oi": call, "put_oi": put}]

    def flow_per_expiry(self, ticker):
        self.calls += 1
        return []

    def iv_rank(self, ticker):
        self.calls += 1
        return [{"iv_rank_1y": "55.0"}]

    def oi_per_expiry_result(self, ticker, date=None):
        return ProviderResult("ok", self.oi_per_expiry(ticker, date))

    def flow_per_expiry_result(self, ticker):
        return ProviderResult("ok", self.flow_per_expiry(ticker))

    def iv_rank_result(self, ticker):
        return ProviderResult("ok", self.iv_rank(ticker))


def _footprint(ticker, name):
    return {"ticker": ticker, "name": name, "snapshot": {"ticker": ticker, "label": "Quiet"},
            "inputs": {}, "fetch_status": "ok"}


def _cache(ticker):
    engine.save_cache(ticker, {"ticker": ticker, "label": "Quiet", "score": 5, "as_of": "2026-10-05"})


# ── the Refresh reads history ──







# ── the Fetch resolves names through the screener result read ──

def test_the_fetch_prefers_the_screener_result_read(rawstore_tmp_db):
    rawstore.save_watchlist({"AAA"})
    footprints: list = []
    scan_leaps(_UW({"AAA": (1000, 200)}), today=TODAY, footprints=footprints)
    assert footprints[0]["name"] == "AAA NEW"


