"""Swing board -> forecast ledger (#128). Offline; the store is a temp DuckDB."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core import calendar as cal
from RevenueChaser.core import ledger, rawstore
from RevenueChaser.core.tests.d01_seed import seed_d01
from RevenueChaser.rcdata.tests import prices_store
from RevenueChaser.module_swing_potential import config, freeze

D = date(2026, 10, 2)
POST_CLOSE = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)      # 17:00 ET
INTRADAY = datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc)        # 12:00 ET


def _cand(ticker, quality, bucket="minervini+weinstein", **kw):
    c = {"ticker": ticker, "price": 20.0, "market_cap": 3.0e9, "sector": "Industrials",
         "bucket": bucket, "quality": quality, "stop": 18.0, "target": 24.0}
    c.update(kw)
    return c


def _payload(candidates, **kw):
    p = {"is_fixture": False, "no_data": False, "data_quality": {"spy_stale": False},
         "candidates": candidates}
    p.update(kw)
    return p


def _close_plus(minutes):
    return cal.session_close(D).timestamp() + minutes * 60




def _stored():
    return rawstore.query("SELECT * FROM forecast_ledger WHERE source = 'swing' ORDER BY rank", db="forecast")




# ── the mapping ──────────────────────────────────────────────────────────────

def test_picks_map_the_shown_candidates_column_by_column():
    rows = freeze.picks([_cand("AAA", 91.5, "minervini+weinstein"),
                         _cand("BBB", None, "qullamaggie", stop=None, target=None)])
    assert rows[0] == {"subject": "AAA", "rank": 1, "score": 91.5, "bucket": "minervini+weinstein",
                       "market_cap": 3.0e9, "sector": "Industrials", "shown_price": 20.0, "stop": 18.0,
                       "target": 24.0}
    assert rows[1]["rank"] == 2 and rows[1]["score"] is None and rows[1]["bucket"] == "qullamaggie"
    assert rows[1]["stop"] is None and rows[1]["target"] is None


def test_rank_is_the_one_based_position_in_candidates():
    assert [r["rank"] for r in freeze.picks([_cand("A", 3), _cand("B", 2), _cand("C", 1)])] == [1, 2, 3]


# ── model version ────────────────────────────────────────────────────────────

# Spelled out on purpose: this is the config the board scores with today. Editing any threshold in
# config.py fails this test until ``SELECTION_VERSION`` is bumped and this block is updated with it.
GOLDEN_CONFIG = {
    "MIN_PRICE": 5.0, "MIN_DOLLAR_VOLUME": 250000, "RS_MIN": 70, "ABOVE_52W_LOW": 1.25, "WITHIN_52W_HIGH": 0.75, "VOL_CONFIRM": 1.5,
    "VOL_WINDOW": 5, "VOL_AVG_DAYS": 20, "BREAKOUT_HIGH_PCT": 0.98, "MOVE_MIN": 0.25, "ADR_MIN": 0.03, "W_12_1": 0.5, "W_PROX": 0.25,
    "W_CONS": 0.25, "CONSISTENCY_LOOKBACK": 126, "STOP_ATR": 2.0, "TARGET_R": 2.0, "ATR_PERIOD": 14,
    "Q_WEIGHTS": {"minervini": 40, "weinstein": 30, "qullamaggie": 30},
    "Q_RULE_TOTALS": {"minervini": 8, "weinstein": 5, "qullamaggie": 6},
}
GOLDEN_VERSION = "5"                # 5: the Weinstein volume window (Swing review finding 3, PR 6)
GOLDEN_MODEL_VERSION = "5+c94564a9"


def test_the_effective_config_is_the_golden_config():
    assert freeze.effective_config() == GOLDEN_CONFIG


def test_the_model_version_is_the_golden_version():
    assert config.SELECTION_VERSION == GOLDEN_VERSION
    assert freeze.model_version() == GOLDEN_MODEL_VERSION


# ── the whole freeze ─────────────────────────────────────────────────────────





























