"""Settings inventory: counts, last dates and holes, computed store-only."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from revenuechaser.rcdata.tests import universe_store
from revenuechaser.core import rawstore
from revenuechaser.module_settings import inventory




def _rows(payload):
    return {r["key"]: r for r in payload["rows"]}




















def _d01_bars(ticker, *days):
    return [{"ticker": ticker, "session_date": date.fromisoformat(day), "close": 1.0,
             "source": "uw", "volume": 1.0} for day in days]




# Before = what the drill used to report (swing_ohlc). After = D01, the price of record.
# One name (AAPL) has D01 bars and no swing_ohlc row — the wrong-number case.
_EVIDENCE = (
    ("AAPL", ("2024-01-02", "2025-06-02", "2026-02-02"), ()),
    ("MSFT", (), ("2026-01-02", "2026-02-02")),
    ("NVDA", ("2026-01-02", "2026-01-03", "2026-01-06", "2026-02-02"), ("2026-01-02",)),
    ("MU", ("2026-02-01", "2026-02-02"), ("2026-02-01", "2026-02-02")),
    ("SPY", (), ("2024-01-02", "2024-06-03", "2025-01-02", "2026-02-02")),
)






# ── F4: a failed query is an error, a missing table is not ───────────────────








# ── every (table, column) the inventory queries exists in the MANIFEST ───────




# ── the one universe: the security-type filter reaches the Settings board (#87) ──




# ── identity health (issue #89): the Identity spine row and ``payload["identity"]`` ───────────
FIXED = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)      # tests never touch today's date
RUN1, RUN2, RUN3 = "2026-09-20T00:00:00Z", "2026-09-30T00:00:00Z", "2026-10-01T00:00:00Z"
SOURCES_OK = {"spdr": {"status": "ok", "selected": True, "rows": 480, "fetched": 0, "error": None},
              "nasdaq": {"status": "ok", "selected": True, "rows": 5000, "fetched": 0, "error": None}}
SOURCES_NO_SPDR = {"nasdaq": {"status": "ok", "selected": True, "rows": 5000, "fetched": 0, "error": None},
                   "spdr": {"status": "skipped", "selected": False, "rows": 0, "fetched": 0, "error": None}}

# (ticker, cap, security_type, sector_source). GONE is not in the universe, NOCAP has a NULL cap.
MASTER = [
    ("AAPL", 3.0e12, "common", "sp1500"), ("MSFT", 2.0e12, "common", "provider_uw"),
    ("ORCL", 1.0e12, "common", "provider_uw"), ("NVDA", 9.0e11, "common", "provider_yf"),
    ("BANKX", 5.0e9, "bank_nonsec", "sic_explicit"), ("PDI", 2.0e9, "cef", "type_rule"),
    ("FLAG", 1.0e9, "etp", "type_rule(etp: no GICS)"), ("ACQ", 4.0e8, "spac", "none"),
    ("SMALL", 1.0e8, "common", "none"), ("NOCAP", None, "common", None),
    ("MANU", 5.0e8, "common", "manual"), ("UNK", 1.0e9, None, "none"), ("GONE", "absent", "common", "provider_uw"),
]


def _run_row(run_id, started, status, sources, counts, finished=None):
    return {"run_id": run_id, "started_at": started, "finished_at": finished or started.replace("00:00:00", "00:06:00"),
            "status": status, "sources": sources, "counts": counts}




def _identity(**kw):
    return inventory.collect(now=FIXED)["identity"]
























































# ── Daily price bars row (#156) ───────────────────────────────────────────────







# ── Quotes and market cap row (#294) ──────────────────────────────────────────
def _quote(ticker, source, cap, day=date(2026, 9, 30)):
    return {"ticker": ticker, "session_date": day, "source": source, "market_cap": cap, "price": 1.0,
            "payload": {"t": ticker}, "fetched_at": 1.0, "run_id": "r", "run_at": 1.0}














@pytest.mark.parametrize("status,want,not_want", [
    (404, "No served file holds a row for", "Could not read"),
    (400, "No served file holds a row for", "Could not read"),
    (500, "Could not read the served files for", "No served file holds")])
def test_df98_lookup_message_by_status(tmp_path, rawstore_tmp_db, status, want, not_want):
    """DF98 under node: only an unknown or malformed ticker says the files hold no row; a server failure says the
    served files could not be read (#715 renamed both, the rule is unchanged)."""
    from revenuechaser.core.tests.board_js import run_board_js
    from revenuechaser.module_settings import report as sr
    html = sr.render_settings_dashboard(inventory.collect())
    tail = """
globalThis.fetch = function(){ return Promise.resolve({status: %d, ok: false, json: function(){ return Promise.resolve({}); }}); };
onDrillPick('AAPL');
setTimeout(function(){ console.log(JSON.stringify(_els['drill-body'].innerHTML)); }, 20);
""" % status
    out = run_board_js(html, tail, tmp_path)
    assert want in out and not_want not in out


# ── Vendor statements and valuation row (#297) ───────────────────────────────






# ── SPX daily levels row (D03, #293) ─────────────────────────────────────────
def _level(day, symbol="^GSPC", source="yfinance", close=6000.0):
    return {"symbol": symbol, "session_date": day, "open": close, "high": close, "low": close,
            "close": close, "volume": 1.0, "source": source, "fetched_at": 1.0, "run_id": "r",
            "run_at": 1.0}











def _sec_file_rows(run_at=1.0, n=4):
    return [{"ticker": f"T{i}", "cik": str(i), "name": f"N{i}", "exchange": "Nasdaq", "valid_from": None,
             "status": "present", "source": "sec_exchange", "fetched_at": run_at, "run_id": "seed",
             "run_at": run_at} for i in range(n)]


def _sec_receipt(markers, session, name="exchange", **data):
    markers.mkdir(parents=True, exist_ok=True)
    (markers / f"{session}_{name}").write_text(json.dumps({"session": session, **data}), encoding="utf-8")


