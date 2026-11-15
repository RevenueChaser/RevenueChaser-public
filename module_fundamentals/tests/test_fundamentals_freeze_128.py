"""Fundamentals board -> forecast ledger (#128). Offline; the store is a temp DuckDB."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core import calendar as cal
from RevenueChaser.core import ledger, rawstore
from RevenueChaser.core.tests.d01_seed import seed_d01
from RevenueChaser.module_fundamentals import config, freeze

D = date(2026, 10, 2)
POST_CLOSE = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)      # 17:00 ET
INTRADAY = datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc)        # 12:00 ET


def _cand(ticker, ro40, multiplier=2, **kw):
    c = {"ticker": ticker, "price": 42.0, "market_cap": 5.0e9, "sector": "Health Care",
         "passed_count": multiplier, "bucket": kw.pop("bucket", "quality"), "ro40": ro40}
    c.update(kw)
    return c


def _payload(candidates, **kw):
    p = {"no_data": False, "data_quality": {"spy_stale": False},
         "candidates": candidates}
    p.update(kw)
    return p


def _close_plus(minutes):
    return cal.session_close(D).timestamp() + minutes * 60




def _stored():
    return rawstore.query("SELECT * FROM forecast_ledger WHERE source = 'fundamentals' ORDER BY rank", db="forecast")




def test_picks_map_the_shown_candidates_column_by_column():
    rows = freeze.picks([_cand("AAA", 61.5, 3, bucket="rule_of_40+quality+momentum"),
                         _cand("BBB", None, 1, bucket="quality")])
    assert rows[0] == {"subject": "AAA", "rank": 1, "score": 61.5, "bucket": "rule_of_40+quality+momentum",
                       "market_cap": 5.0e9, "sector": "Health Care", "shown_price": 42.0, "stop": None,
                       "target": None}
    assert rows[1]["rank"] == 2 and rows[1]["score"] is None and rows[1]["bucket"] == "quality"


def test_rank_is_the_one_based_position_in_candidates():
    assert [r["rank"] for r in freeze.picks([_cand("A", 3), _cand("B", 2)])] == [1, 2]


# Spelled out on purpose: the thresholds the board scores with today. Editing one in config.py fails
# this test until ``SELECTION_VERSION`` is bumped and this block is updated with it.
GOLDEN_CONFIG = {
    "MIN_PRICE": 5.0, "MIN_DOLLAR_VOLUME": 250000, "RO40_MIN": 40.0, "GROWTH_MIN": 0.2, "ROIC_MIN": 0.15,
    "ROIC_IC_MIN_SHARE": 0.05, "GM_MIN": 0.3,
    "ND_EBITDA_MAX": 3.0, "DIST_52W_MAX": 0.25, "RS_6M_MIN": 0.0, "ABOVE_200D": True,
    "DISTORTED_GROWTH": 2.0, "DISTORTED_REV_MIN": 10000000, "TAX_RATE": 0.21,
    "EXCLUDED_SECTORS": ["Financial Services", "Real Estate"], "RO40_BARRIER": 150.0,
}
GOLDEN_VERSION = "9"
GOLDEN_MODEL_VERSION = "9+f60b68e4"


def test_the_effective_config_is_the_golden_config():
    assert freeze.effective_config() == GOLDEN_CONFIG


def test_the_model_version_is_the_golden_version():
    assert config.SELECTION_VERSION == GOLDEN_VERSION
    assert freeze.model_version() == GOLDEN_MODEL_VERSION
















