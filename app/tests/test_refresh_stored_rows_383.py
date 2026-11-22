"""Common K4 + AG S5 (C19, #383 R1): a screener Refresh renders what the last Fetch stored and never re-scores.

- Asymmetric Growth: the cards are the ``ticker_scores`` rows (``ticker_store``), the rest (universe, summary, funnel)
  the last Fetch's history header (K2). The card the board embeds is the stored shape (``ticker_store.card_view``),
  so a Fetch and a Refresh embed the same card.
- Swing and Fundamentals: the last Fetch's board payload, recorded on its history header, or the board's saved JSON
  when that is newer (a Fetch whose history write failed). A saved board that is empty or the demo fixture never
  counts. A header from before K4 (no payload) falls back to the saved JSON; with neither, no scan is stored.
- With ``no_fetch=True`` no ``compute_row`` / scorer runs and no pool opens; one that would raise changes nothing.
- Golden: on fixtures the Refresh render equals the Fetch render. The Recorded-sessions panel is read when the page
  renders (a Fetch shows its own session from the next render), so it is left out of the comparison.
Offline, temp store.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from revenuechaser.rcdata.tests import universe_store
from revenuechaser.app import runners
from revenuechaser.core import rawstore, screen_common, ticker_store
from revenuechaser.module_fundamentals import config as fcfg
from revenuechaser.module_fundamentals import pipeline as fp
from revenuechaser.module_swing_potential import config as scfg
from revenuechaser.module_swing_potential import pipeline as sp
from revenuechaser.module_swing_potential.tests.test_ohlc import _df

_PANEL = re.compile(r'<details class="(?:rules|rc-history)" id="history-panel">.*?</details>', re.S)
ANNUAL = [{"fiscal_year": 2022 + i, "revenue": 100.0 * (i + 1), "gross_profit": 60.0 * (i + 1),
           "operating_cash_flow": 30.0 * (i + 1), "capex": 5.0, "total_debt": 10.0, "cash": 30.0,
           "total_assets": 200.0, "total_equity": 100.0, "net_income": 20.0 * (i + 1)} for i in range(3)]


@pytest.fixture
def out(isolate_board_artifacts, monkeypatch):
    """Every artifact the runners write lands in this test's folder: the root conftest already points both copies
    of each board path there (#111), so only the runners' own OUTPUT_DIR is set here."""
    monkeypatch.setattr(runners, "OUTPUT_DIR", isolate_board_artifacts)
    return isolate_board_artifacts


def _html(path) -> str:
    return _PANEL.sub("", path.read_text(encoding="utf-8"))


def _no_scoring(monkeypatch):
    """Any scorer, pool or network call on a Refresh fails the test."""
    def boom(*a, **k):
        raise AssertionError("a Refresh must not score")
    from revenuechaser.module_asymmetric_growth import engine
    for mod in (sp, fp):
        monkeypatch.setattr(mod, "_compute_row", boom)
    monkeypatch.setattr(engine, "run_asymmetric_growth_hunter", boom)
    monkeypatch.setattr(engine, "enrich_and_score", boom)
    monkeypatch.setattr(screen_common, "ThreadPoolExecutor", boom)
    monkeypatch.setattr("yfinance.Ticker", boom)
    monkeypatch.setattr("yfinance.download", boom)


# ── Asymmetric Growth (S5) ───────────────────────────────────────────────────────────────────────────────────────
def _card(ticker, points, **kw):
    card = {"ticker": ticker, "fiscal_year": 2025, "name": f"{ticker} Inc", "sector": "Technology",
            "industry": "Software", "inst_ownership_pct": 0.61, "price": 12.5, "market_cap": 8.0e8,
            "ps_ratio": 4.2, "rev_growth": 0.45, "gross_margin": 0.7, "fcf": 5_000_000, "runway_years": None,
            "rd_intensity": 0.2, "dilution_yoy": 0.01, "earnings_date": 1.7e9, "total_points": points,
            "signals": [{"name": "Growth", "points": 2, "subs": [{"param": "rev_growth", "passed": True}]}],
            "themes": ["AI"], "tech_breakthrough": True, "dilution_warning": False, "us_listed": True,
            "source": "sec_edgar", "inst_holders": 120.0, "inst_new": 4, "inst_exited": 2, "inst_buy_flow": 1.5e7,
            "inst_sell_flow": 3.0e6, "inst_shares": 2.0e7, "inst_shares_delta_pct": 0.05}
    card.update(kw)
    return card


def _ag_result():
    from revenuechaser.module_asymmetric_growth import engine, freeze
    mv = freeze.model_version()             # rows of this version: the board shows no "scored before" banner
    ends = {"revenue": ["2025-12-31", "2024-12-31", "2023-12-31"], "balance_sheet": "2025-12-31", "cash_flow": None}
    cards = [_card("AAA", 9, tier=3, flags=[], model_version=mv, anchor_fy=2025, prior_fy=2024, period_ends=ends),
             _card("BBB", 6, rev_growth=None, themes=[], tier=None, flags=["mixed_share_basis"], model_version=mv),
             _card("CCC", 6, rev_growth=0.9, tier=2, flags=["suspicious_growth"], model_version=mv)]
    engine._sort_cards(cards)                # tier, points, capped growth, ticker (#380 S2)
    return {"asof": "2026-10-06T22:05:00+00:00", "data_as_of": "2026-10-06", "universe_total": 4187,
            "universe_generated_at": "2026-10-06T21:00:00",
            "universe_refreshed_by": "Asymmetric Growth", "universe_partial": True,
            "funnel_steps": [{"step": "universe", "names": 4187}, {"step": "scored", "names": 3}],
            "summary": {"scanned": 3, "excluded_types": 12, "pts_9": 1, "pts_8_7": 0, "pts_6_5": 2, "pts_lt5": 0,
                        "score_errors": 1, "score_error_types": {"ValueError": 1}},
            "cards": cards, "thresholds": __import__(
                "revenuechaser.module_asymmetric_growth.engine", fromlist=["THRESHOLDS"]).THRESHOLDS}


def _ag_payload():
    """The cards the AG page loads (S7, K10): the gzip payload file next to the page."""
    import gzip
    from revenuechaser.core.reporting_common import payload_path
    return json.loads(gzip.decompress(payload_path(runners.ASYMMETRIC_GROWTH_LATEST).read_bytes()))


@pytest.fixture
def ag_fetched(rawstore_tmp_db, out, monkeypatch):
    from revenuechaser.module_asymmetric_growth import engine, freeze
    universe_store.replace([{"ticker": "AAA", "market_cap": 1e9, "price": 10.0, "name": "A"}])
    monkeypatch.setattr(engine, "run_asymmetric_growth_hunter", lambda uw, **k: _ag_result())
    monkeypatch.setattr(freeze, "freeze_result", lambda *a, **k: None)
    monkeypatch.setattr(runners, "_freeze_run_id", lambda: "fetch-1")
    runners.run_asymmetric_growth(None)
    return _html(runners.ASYMMETRIC_GROWTH_LATEST), _ag_payload()








def test_ag_stored_cards_are_what_ticker_scores_holds(ag_fetched):
    from revenuechaser.module_asymmetric_growth import engine
    ticker_store.write_from_cards([{"ticker": t, "name": t, "sector": "Energy", "total_points": pts,
                                    "themes": [], "signals": [], "tech_breakthrough": False}
                                   for t, pts in (("YYY", 3), ("ZZZ", 5))],
                                  asof="2026-10-07T22:05:00+00:00")         # a later scan with no header
    res = engine.stored_result()
    assert [c["ticker"] for c in res["cards"]] == ["ZZZ", "YYY"]            # by points, as the Fetch sorts them
    # the header is not this scan's (its asof differs): the summary comes from the cards, no funnel
    assert res["summary"]["scanned"] == 2 and res["funnel_steps"] is None


def test_ag_a_fetch_embeds_the_stored_card_shape():
    from revenuechaser.module_asymmetric_growth.report import _card_rows
    card = _card("AAA", 9, index=["S&P 500"])
    shown = _card_rows([card])[0]
    assert "fiscal_year" not in shown and shown["index"] == ["S&P 500"]
    assert shown["inst_holders"] == 120 and isinstance(shown["fcf"], float)
    # The page row adds the shared filter fields at render (#383 R2b C1c), from a store read: the stored card stays.
    assert isinstance(shown.pop("gics"), list) and isinstance(shown.pop("theme_ids"), list)
    assert shown == ticker_store.card_view(ticker_store._row_to_card(ticker_store.rows_from_cards([card])[0])
                                           | {"index": ["S&P 500"]})


def test_ag_refresh_with_a_universe_but_no_stored_scan_says_so(rawstore_tmp_db, out, monkeypatch):
    _no_scoring(monkeypatch)
    universe_store.replace([{"ticker": "AAA", "market_cap": 1e9, "price": 10.0, "name": "A"}])
    runners.run_asymmetric_growth(None, no_fetch=True)
    assert "No stored scan yet" in runners.ASYMMETRIC_GROWTH_LATEST.read_text(encoding="utf-8")


# ── Swing and Fundamentals (K4) ──────────────────────────────────────────────────────────────────────────────────
BOARDS = [pytest.param(sp, "run_swing", "SWING_LATEST", scfg, "SWING_JSON", "module_swing_potential", id="swing"),
          pytest.param(fp, "run_fundamentals", "FUNDAMENTALS_LATEST", fcfg, "FUNDAMENTALS_JSON",
                       "module_fundamentals", id="fundamentals")]














@pytest.mark.parametrize("mod,runner,latest,cfg,saved,board", BOARDS)
def test_an_empty_store_still_says_no_universe(rawstore_tmp_db, out, monkeypatch, mod, runner, latest, cfg, saved,
                                              board):
    _no_scoring(monkeypatch)
    payload = mod.run_scan(no_fetch=True)
    assert payload["no_data_reason"] == "no_universe_stored"
