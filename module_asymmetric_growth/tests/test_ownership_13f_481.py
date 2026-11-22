"""#481: Asymmetric Growth takes the institutional share from 13F, as every other board does (owner, 9 Nov 2026:
"#481 de 13F den alsin, 13F henuz zip yayinlanmamis ceyrekleri de dolduruyor artik").

The share is the newest **settled** 13F quarter's shares divided by the stored shares outstanding — the 13F board's
``% Out`` rule (``module_sec_13f/report.py``), read through ``core/ownership``. The yfinance
``heldPercentInstitutions`` is no longer read: a name with no settled 13F quarter shows no share. A quarter whose
filing deadline has not passed holds a part of itself (#514), so it feeds neither the share nor the 13F block.

A scan of the synthetic store, no network.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from revenuechaser.core import ownership, rawstore
from revenuechaser.module_asymmetric_growth import engine
from revenuechaser.module_asymmetric_growth.tests.test_ag_info_only_150 import _QUOTE, _YF_ANNUAL

RUN_AT = datetime(2026, 1, 15, 21, 35, tzinfo=timezone.utc).timestamp()    # a complete session






def _q(shares: float, complete: bool = True) -> dict:
    return {"holders": 10, "new_holders": 2, "exited_holders": 1, "buy_flow": 5.0, "sell_flow": 1.0,
            "shares": shares, "complete": complete}


TOTALS = {"AAA": {"2025-12-31": _q(300.0), "2026-03-31": _q(400.0), "2026-06-30": _q(50.0, complete=False)},
          "NOSO": {"2026-03-31": _q(400.0)}}




def _cards(result: dict) -> dict[str, dict]:
    return {c["ticker"]: c for c in result["cards"]}










def test_a_summary_counted_from_stored_cards_reports_the_counts_as_unknown():
    """``ticker_scores`` keeps no provenance, so a Refresh with no Fetch header cannot count them."""
    card = {"ticker": "AAA", "sector": "Technology", "total_points": 1, "themes": [], "flags": [],
            "tech_breakthrough": False, "source": "sec_edgar"}
    assert engine._summary([card], None, {})["ownership"] == {"sec13f": None, "quarter": None}


# ── the measured gaps (live data, 9 Nov 2026): 1,219 of 4,159 names had a stored shares outstanding ─────────────





def test_a_share_above_100_percent_is_shown_as_a_check_not_a_number():
    """GOSS read 6,242 % on live data: 13F shares on a pre-reverse-split base. The card says so, not the number."""
    from revenuechaser.module_asymmetric_growth import report
    html = report.render_asymmetric_growth_hunter_html({"asof": "", "cards": [], "summary": {},
                                                        "thresholds": engine.THRESHOLDS})
    assert "inst_ownership_pct > 1" in html and "above 100%" in html


# ── a split after the 13F quarter (avo, 9 Nov 2026: "wrds ile bu bolunmeleri ... cekiyoruz ... oradan baksak?") ──

def _split_store(monkeypatch, factor: float) -> list:
    """The prices store at the read boundary: AAA's bar on the quarter end carries ``split_factor`` (a 1-for-25
    reverse split after it serves 25: today's shares are the quarter's ÷ 25). Returns the bar windows asked."""
    from revenuechaser.rcdata import read
    asked = []
    monkeypatch.setattr(read, "security_ids", lambda tickers: {t: f"sid:{t}" for t in tickers})

    def bars(ids, start=None, end=None, basis="nominal"):
        asked.append((sorted(ids), start, end, basis))
        return [{"security_id": "sid:AAA", "session_date": end, "split_factor": factor}]

    monkeypatch.setattr(read, "bars", bars)
    return asked




