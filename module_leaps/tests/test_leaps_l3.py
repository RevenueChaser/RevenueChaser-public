"""L3 (#377): the LEAPS label is classified from ``leaps_footprint_history``, not the cache list.

Red-first for the four L3 behaviours (O8, O9, O10, Q5):

1. the quarter baseline is the last recorded session at or before quarter end (O8);
2. growth is matched-expiry far-call OI growth over the expiries present in both snapshots, far being decided at
   the BASELINE date, so an expiry crossing the 270-day line or a new listing is not growth (O9);
3. an all-bid flow (ask share below ``ASK_SHARE_MIN``) is not "Accumulating" (O10);
4. the board says the signal is exploratory (Q5).

``leaps_cache.latest`` stays (Earnings reads it); its ``history[]`` list is frozen: carried unchanged, never
appended, never deleted (D1).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core import ledger, rawstore
from RevenueChaser.core.providers.result import ProviderResult
from RevenueChaser.module_leaps import engine
from RevenueChaser.module_leaps.scan import scan_leaps, scan_leaps_cached

TODAY = date(2026, 10, 5)                       # a Monday session
FAR = "2027-12-17"                              # > 270 days after TODAY
# The nine keys Earnings reads off ``leaps_cache.latest`` (pipeline._score, C26).
EARNINGS_KEYS = ("label", "as_of", "score", "far_call_oi", "far_put_oi", "far_call_share",
                 "far_oi_growth_1d_pct", "far_oi_growth_q_pct", "iv_rank")


# ── the seed helper: a real recorded session, as a Fetch writes one ───────────────────────────────────────────────

def run_at_of(day: date) -> float:
    """18:00 ET on ``day`` — a complete New York session (rule B)."""
    return datetime(day.year, day.month, day.day, 22, 0, tzinfo=timezone.utc).timestamp()


def _per(value, ticker):
    return value.get(ticker) if isinstance(value, dict) else value




class _UW:
    """A UW double: far-dated OI per ticker; every read answers ``ok``."""
    auth_error = None

    def __init__(self, oi: dict):
        self.oi = oi
        self.calls = self.failed = 0

    def health(self):
        return {"calls": self.calls, "failed": self.failed, "auth_error": None, "failures": [],
                "breaker_open": False, "skipped_calls": 0}

    def option_trades(self, **kw):
        return []

    def screener_batch(self, tickers):
        return {t: {"full_name": f"{t} Inc"} for t in tickers}

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


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text, self.headers = status, payload or {"data": []}, "", {}

    def json(self):
        return self._payload


def _uw_404(ticker, call=1000):
    """The real client, offline: ``ticker``'s oi-per-expiry answers 404, every other read answers."""
    from RevenueChaser.core.providers.unusual_whales import UWClient
    c = UWClient(key="k", sleep=lambda s: None)

    def _get(url, params=None):
        if f"/stock/{ticker}/oi-per-expiry" in url:
            return _Resp(404, {"message": "not found"})
        if "/oi-per-expiry" in url:
            return _Resp(200, {"data": [{"expiry": FAR, "call_oi": call, "put_oi": 100}]})
        return _Resp(200)

    c._client.get = _get  # type: ignore[method-assign]
    return c


@pytest.fixture
def store(rawstore_tmp_db):
    ledger.take_notes()
    return rawstore_tmp_db


def _oi(call, put=50, expiry=FAR):
    return [{"expiry": expiry, "call_oi": call, "put_oi": put}]


# ── 1. an expiry crossing the far line is not growth ──────────────────────────────────────────────────────────────

def test_an_expiry_crossing_the_far_line_is_not_growth():
    # 2027-03-27 is exactly 270 days after the 2026-06-30 baseline and 269 days before the 2027-03-28 snapshot.
    base_oi = _oi(500, expiry="2027-03-27")
    cur_oi = _oi(500, expiry="2027-03-27")
    assert engine.matched_far_growth(cur_oi, base_oi, "2026-06-30") == 0.0
    snap = {"far_call_oi": 500, "far_put_oi": 50, "far_call_share": 0.9091, "near_term_event": False}
    base = {"as_of": "2026-06-30", "oi_per_expiry": base_oi, "far_call_oi": 500}
    assert engine.classify(snap, base, None, cur_oi=cur_oi)["label"] == "Quiet"


def test_an_expiry_just_inside_the_far_line_is_left_out():
    # 2027-03-26 is 269 days from the baseline: near-dated there, so its OI doubling is not far growth.
    base_oi = [{"expiry": "2027-03-27", "call_oi": 500, "put_oi": 50},
               {"expiry": "2027-03-26", "call_oi": 100, "put_oi": 10}]
    cur_oi = [{"expiry": "2027-03-27", "call_oi": 500, "put_oi": 50},
              {"expiry": "2027-03-26", "call_oi": 200, "put_oi": 10}]
    assert engine.matched_far_growth(cur_oi, base_oi, "2026-06-30") == 0.0


# ── 2. matched expiries ──────────────────────────────────────────────────────────────────────────────────────────

def test_a_new_listing_is_not_growth():
    base_oi = _oi(1000, expiry="2027-06-18")
    cur_oi = _oi(1000, expiry="2027-06-18") + _oi(900, expiry="2028-01-21")   # a new far expiry appears
    assert engine.matched_far_growth(cur_oi, base_oi, "2026-06-30") == 0.0
    snap = {"far_call_oi": 1900, "far_put_oi": 100, "far_call_share": 0.95, "near_term_event": False}
    base = {"as_of": "2026-06-30", "oi_per_expiry": base_oi, "far_call_oi": 1000}
    assert engine.classify(snap, base, None, cur_oi=cur_oi)["label"] == "Quiet"


def test_no_matched_expiry_gives_none():
    base_oi = _oi(500, expiry="2027-06-18")
    cur_oi = _oi(900, expiry="2027-12-17")          # a different expiry on each side: nothing to compare
    assert engine.matched_far_growth(cur_oi, base_oi, "2026-06-30") is None


def test_an_empty_history_gives_none_never_zero():
    assert engine.matched_far_growth(_oi(900), [], "2026-06-30") is None
    assert engine.matched_far_growth(_oi(900), _oi(0), "2026-06-30") is None      # a 0 baseline is no growth




# ── 3. the quarter baseline ──────────────────────────────────────────────────────────────────────────────────────







# ── 4. the ask-share gate ────────────────────────────────────────────────────────────────────────────────────────

def _snap(share=0.9):
    return {"far_call_oi": 1000, "far_put_oi": 50, "far_call_share": share, "near_term_event": False}


def _cand(share=0.8, ask_share=0.2):
    return {"ticker": "ABC", "final_score": 80.0, "frequency": 4, "notional": 4e5, "net_notional": 1e5,
            "concentration": 0.6, "itm_conc": 0.6, "otm_conc": 0.1, "concentration_mult": 1.2,
            "call_share": share, "ask_share": ask_share, "near_event": False}


def test_an_all_bid_flow_is_not_accumulating():
    out = engine.classify(_snap(), {"far_call_oi": 700}, None, ask_share=0.2)
    assert out["far_oi_growth_1d_pct"] > 0            # the OI did grow
    assert out["label"] == "Quiet"                    # but the prints were all bid
    assert engine.radar_snapshot(_cand(ask_share=0.2))["label"] == "Quiet"


def test_no_prints_is_not_gated():
    assert engine.classify(_snap(), {"far_call_oi": 700}, None, ask_share=None)["label"] == "Accumulating"
    assert engine.radar_snapshot(_cand(ask_share=None))["label"] == "Accumulating"


def test_high_ask_share_stays_accumulating():
    assert engine.classify(_snap(), {"far_call_oi": 700}, None, ask_share=0.8)["label"] == "Accumulating"
    assert engine.radar_snapshot(_cand(ask_share=0.8))["label"] == "Accumulating"




# ── 5. a failed read leaves the recorded baseline alone ──────────────────────────────────────────────────────────



# ── 6. an unreadable history is a warning, never a failed Fetch ──────────────────────────────────────────────────





# ── 7. the cache payload: latest kept, history frozen ────────────────────────────────────────────────────────────

def test_latest_keeps_label_and_as_of(store):
    old = [{"ticker": "AAA", "label": "Quiet", "as_of": "2026-09-30"},
           {"ticker": "AAA", "label": "Accumulating", "as_of": "2026-10-01"}]
    rawstore.save_watchlist({"AAA"})
    rawstore.write_rows("leaps_cache", [{"ticker": "AAA", "payload": {
        "latest": {"ticker": "AAA", "label": "Quiet", "as_of": "2026-10-01"}, "history": old}}])
    engine.fetch_and_classify("AAA", _UW({"AAA": (1000, 200)}), today=TODAY, inputs={})
    engine.fetch_and_classify("AAA", _UW({"AAA": (1200, 200)}), today=TODAY, inputs={})
    data = engine.load_cache("AAA")
    latest = data["latest"]
    assert latest["label"] in engine.LABELS and latest["as_of"] == TODAY.isoformat()
    for key in EARNINGS_KEYS:
        assert key in latest, f"Earnings reads {key}"
    assert "inputs" not in latest and "oi_per_expiry" not in latest
    assert data["history"] == old                     # carried unchanged: never appended, never deleted (D1)


# ── 8. Refresh: re-derive with the row's own date (D4) ───────────────────────────────────────────────────────────

def _cached_0915(expiry, label="Quiet"):
    return {"ticker": "AAA", "label": label, "score": 0, "as_of": "2026-09-15",
            "far_call_oi": 1000, "far_put_oi": 50, "far_call_share": 0.9524,
            "far_oi_growth_1d_pct": None, "far_oi_growth_q_pct": None,
            "iv_rank": 55.0, "iv_rank_slope": None, "near_term_event": False}






# ── 9. the board says the signal is exploratory (Q5) ─────────────────────────────────────────────────────────────

def test_the_board_says_exploratory(tmp_path, monkeypatch):
    import RevenueChaser.module_leaps.report as ld
    monkeypatch.setattr(ld, "OUTPUT_DIR", tmp_path)
    snap = {"ticker": "ABC", "label": "Quiet", "score": 5, "frequency": 0, "net_notional": 0.0}
    html = ld.render_leaps_dashboard([snap], []).read_text(encoding="utf-8")
    header = html[html.index('class="header"'):html.index('class="controls"')]
    assert "exploratory" in header.lower()
    help_box = html[html.index('<details class="help">'):html.index('id="tier-watchlist"')]
    assert "exploratory" in help_box.lower()
    legend = html[html.index('<div class="legend">'):html.index("<footer>")]
    assert "exploratory" in legend.lower()
    assert "ask" in legend.lower() and "bid" in legend.lower()
