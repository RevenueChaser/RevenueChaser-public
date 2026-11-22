"""Earnings Radar board -> forecast ledger (#580). Offline; the store is a temp DuckDB.

The board's own two rules, next to the shared ones of #128: only a report still to come is frozen, and one name
without a complete daily bar does not refuse the day (SPY's own bar still anchors it).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from revenuechaser.core import calendar as cal
from revenuechaser.core import ledger, rawstore
from revenuechaser.module_earnings_radar import composite, freeze
from revenuechaser.module_earnings_radar.models import TradeCard

D = date(2026, 10, 2)                                               # a Friday
POST_CLOSE = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)      # 17:00 ET
INTRADAY = datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc)        # 12:00 ET
AHEAD = date(2026, 10, 7)                                           # a report still to come


def _card(ticker, *, confidence=70.0, pre=5.0, action="OPTIONS_BULL", conviction="HIGH",
          earnings_date=AHEAD, market_cap=8.0e8, price=12.5, sector="Information Technology") -> TradeCard:
    return TradeCard(ticker=ticker, confidence_score=confidence, pre_score=pre, final_action=action,
                     conviction=conviction, earnings_date=earnings_date, market_cap_value=market_cap,
                     shown_price=price, sector=sector)


def _spy_bar(minutes=45):
    """SPY's D01 bar for D, written ``minutes`` after the close: the freeze's anchor."""
    from revenuechaser.core.tests.d01_seed import seed_d01
    from revenuechaser.rcdata.tests import prices_store
    at = (cal.session_close(D) + timedelta(minutes=minutes)).timestamp()
    seed_d01("SPY", [D], at)
    prices_store.set_built_at(at)


def _no_bars():
    from revenuechaser.core.tests.d01_seed import drop_d01
    drop_d01()


def _stored():
    return rawstore.query("SELECT * FROM forecast_ledger WHERE source = 'earnings_radar' ORDER BY rank",
                          db="forecast")


@pytest.fixture
def store(rawstore_tmp_db):
    ledger.take_notes()
    _spy_bar()
    return rawstore_tmp_db


# ── the mapping ──────────────────────────────────────────────────────────────

def test_picks_map_the_shown_cards_column_by_column():
    rows = freeze.picks([_card("AAA"), _card("BBB", confidence=40.0, pre=0.0, action="WATCH",
                                             conviction="LOW", market_cap=None, price=None, sector="")], D)
    assert rows[0] == {"subject": "AAA", "rank": 1, "score": 75.0, "bucket": "OPTIONS_BULL|HIGH",
                       "market_cap": 8.0e8, "sector": "Information Technology", "shown_price": 12.5,
                       "stop": None, "target": None}
    assert rows[1] == {"subject": "BBB", "rank": 2, "score": 40.0, "bucket": "WATCH|LOW",
                       "market_cap": None, "sector": None, "shown_price": None, "stop": None, "target": None}


def test_rank_is_the_one_based_position_in_the_board_order():
    cards = [_card("A"), _card("B"), _card("C")]
    assert [r["rank"] for r in freeze.picks(cards, D)] == [1, 2, 3]


def test_the_score_is_confidence_plus_the_preselect_score():
    assert freeze.board_score(_card("A", confidence=61.4, pre=2.1)) == 63.5


@pytest.mark.parametrize("day", [D, D - timedelta(days=1), None, "", "not-a-date"])
def test_a_card_whose_report_is_not_ahead_of_the_session_is_left_out(day):
    """A report the market has already heard is not a forecast, and neither is a card with no readable date."""
    assert freeze.picks([_card("OLD", earnings_date=day)], D) == []


def test_a_left_out_card_leaves_no_hole_in_the_ranks():
    cards = [_card("AHEAD1"), _card("PAST", earnings_date=D), _card("AHEAD2")]
    rows = freeze.picks(cards, D)
    assert [(r["subject"], r["rank"]) for r in rows] == [("AHEAD1", 1), ("AHEAD2", 2)]


def test_a_card_reporting_the_next_session_is_still_ahead():
    assert [r["subject"] for r in freeze.picks([_card("TMRW", earnings_date=D + timedelta(days=1))], D)] == ["TMRW"]


# ── model version ────────────────────────────────────────────────────────────

# Spelled out on purpose: this is the config the board scores with today. Editing any of it in ``core/config.py`` or
# in ``composite.py`` fails this test until ``SELECTION_VERSION`` is bumped and this block is updated with it.
GOLDEN_CONFIG = {
    "RULE_WEIGHTS": {"rule1_drivers": 0.0, "rule2_guidance": 0.20, "rule3_financial": 0.20,
                     "rule5_positioning": 0.0, "rule7_accounting": 0.15, "rule8_sentiment": 0.10},
    "DIRECTION_RANGE": [-100, 100],
    "VOLATILITY_EDGE_RANGE": [0, 100],
    "GATES": {"MIN_OPTION_VOLUME": 500, "MIN_TOTAL_OI": 200, "MIN_DOLLAR_OPTION_VOLUME": 50_000,
              "MIN_EXPECTED_MOVE_PCT": 1.5, "MAX_EXPECTED_MOVE_PCT": 25.0, "WATCHLIST_BYPASS": True,
              "MAX_DEEP_CHECKS_PER_DAY": 500, "FLOW_SWEEP_BLOCK_MIN": 25_000, "INST_FLOW_MIN_NET": 25_000},
    "CUTS": {"BIAS_LEAN": 12, "CONVICTION_HIGH": [25, 65, 3], "CONVICTION_MEDIUM": [12, 45, 2],
             "WATCH_DIRECTION": 12, "WATCH_CONFIDENCE": 50, "OPTIONS_DIRECTION": 25, "OPTIONS_VOL_EDGE": 50,
             "SHARES_DIRECTION": 18},
}
GOLDEN_VERSION = "1"                    # 1: the first frozen Earnings Radar board (#580)
GOLDEN_MODEL_VERSION = "1+3bf74da7"


def test_the_effective_config_is_the_golden_config():
    assert freeze.effective_config() == GOLDEN_CONFIG


def test_the_model_version_is_the_golden_version():
    assert composite.SELECTION_VERSION == GOLDEN_VERSION
    assert freeze.model_version() == GOLDEN_MODEL_VERSION


def test_the_named_cuts_are_the_ones_the_three_classifiers_use():
    """The cuts left the function bodies for the hash; a rename that drops one from ``SCORING_CUTS`` is caught here."""
    assert composite.classify_bias(composite.BIAS_LEAN) == "BULLISH_LEAN"
    assert composite.classify_bias(composite.BIAS_LEAN - 1) == "NEUTRAL"
    assert composite.classify_bias(-composite.BIAS_LEAN) == "BEARISH_LEAN"
    assert composite.select_action(composite.WATCH_DIRECTION - 1, 100, False, 100) == "WATCH"
    assert composite.select_action(30, 0, False, composite.WATCH_CONFIDENCE - 1) == "WATCH_LOW_COVERAGE"
    assert composite.select_action(composite.OPTIONS_DIRECTION, composite.OPTIONS_VOL_EDGE, False, 80) \
        == "OPTIONS_BULL"
    assert composite.select_action(-composite.SHARES_DIRECTION, 0, False, 80) == "SHARES_BEAR"
    assert set(composite.SCORING_CUTS) == {
        "BIAS_LEAN", "CONVICTION_HIGH", "CONVICTION_MEDIUM", "WATCH_DIRECTION", "WATCH_CONFIDENCE",
        "OPTIONS_DIRECTION", "OPTIONS_VOL_EDGE", "SHARES_DIRECTION"}


# ── the whole freeze ─────────────────────────────────────────────────────────

def test_a_post_close_fetch_freezes_every_card_still_to_report(store):
    out = freeze.freeze_cards([_card("AAA"), _card("BBB", confidence=60.0), _card("CCC", confidence=50.0)],
                              run_id="job1", now=POST_CLOSE)
    assert (out.frozen, out.source, out.label) == (3, "earnings_radar", "Earnings Radar")
    rows = _stored()
    assert [(r["subject"], r["rank"], r["bucket"], r["forecast_date"], r["target_date"]) for r in rows] == [
        ("AAA", 1, "OPTIONS_BULL|HIGH", D, D), ("BBB", 2, "OPTIONS_BULL|HIGH", D, D),
        ("CCC", 3, "OPTIONS_BULL|HIGH", D, D)]
    assert {r["run_id"] for r in rows} == {"job1"}
    assert {r["model_version"] for r in rows} == {freeze.model_version()}
    assert ledger.take_notes() == ["Froze 3 Earnings Radar rows for 2026-10-02."]


def test_a_second_fetch_the_same_day_with_another_set_changes_nothing(store):
    freeze.freeze_cards([_card("AAA")], run_id="one", now=POST_CLOSE)
    before = _stored()
    out = freeze.freeze_cards([_card("BBB"), _card("CCC")], run_id="two", now=POST_CLOSE)
    assert out.frozen == 0 and _stored() == before


def test_an_intraday_run_freezes_nothing(store):
    assert freeze.freeze_cards([_card("AAA")], run_id="x", now=INTRADAY).frozen == 0
    assert rawstore.count("forecast_ledger") == 0


def test_a_fetch_of_past_days_freezes_nothing(store):
    """Every card reports on or before D: a backfill run, not a forecast."""
    out = freeze.freeze_cards([_card("AAA", earnings_date=D), _card("BBB", earnings_date=D - timedelta(days=3))],
                              run_id="x", now=POST_CLOSE)
    assert out.frozen == 0 and rawstore.count("forecast_ledger") == 0
    assert "no usable picks" in ledger.take_notes()[0]


def test_no_cards_freezes_nothing(store):
    out = freeze.freeze_cards([], run_id="x", now=POST_CLOSE)
    assert out.frozen == 0 and "no candidates" in ledger.take_notes()[0]


def test_a_session_without_a_spy_d01_bar_freezes_nothing(store):
    _no_bars()
    out = freeze.freeze_cards([_card("AAA")], run_id="x", now=POST_CLOSE)
    assert out.frozen == 0 and rawstore.count("forecast_ledger") == 0
    (note,) = ledger.take_notes()
    assert "SPY has no complete" in note and "2026-10-02" in note


def test_a_spy_bar_written_before_the_close_plus_margin_freezes_nothing(store):
    _spy_bar(minutes=29)
    assert freeze.freeze_cards([_card("AAA")], run_id="x", now=POST_CLOSE).frozen == 0
    _spy_bar(minutes=30)
    assert freeze.freeze_cards([_card("AAA")], run_id="x", now=POST_CLOSE).frozen == 1


def test_a_card_without_its_own_daily_bar_does_not_refuse_the_board(store):
    """Unlike Swing and Fundamentals: an Earnings Radar card is scored from the chain, the flow and the estimates,
    so one name with no bar must not cost the whole day."""
    out = freeze.freeze_cards([_card("NOBARS"), _card("AAA")], run_id="x", now=POST_CLOSE)
    assert out.frozen == 2
    assert [r["subject"] for r in _stored()] == ["NOBARS", "AAA"]


def test_one_ticker_shown_twice_is_frozen_once(store):
    out = freeze.freeze_cards([_card("AAA"), _card("AAA", confidence=10.0)], run_id="x", now=POST_CLOSE)
    assert out.frozen == 1 and out.dropped == 1
    assert [r["subject"] for r in _stored()] == ["AAA"]
