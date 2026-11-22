"""#41 (#66 checkbox 5): the AG run summary says how many scored names are thin and how many have no EDGAR numbers.

Both figures are reporting only. AG has no liquidity floor (a thin name still gets a card), so the thin count is a
funnel **note**, never a drop: the drops must still add up to ``universe - scored``. The unreadable-SEC count is the
scored card whose ``source`` is not EDGAR — the Yahoo-statements fallback the card already carries; a name that got
no card for a filings reason is a drop (``no_annual`` / ``fetch_failed``) and is never counted here too.

The two figures OVERLAP by design: they answer independent questions — is this name too thin to read, and were
its financials read from EDGAR — so a name that is both thin and non-EDGAR is counted in both. "Counted once"
belongs to drops, which must sum to the universe; ``core.funnel.validate`` sums only ``kind == "drop"`` (#106
review).

Synthetic store, pinned session, no network.
"""
from __future__ import annotations

import copy

from revenuechaser.rcdata.tests import fund_store
from revenuechaser.core import funnel
from revenuechaser.module_asymmetric_growth import engine
from revenuechaser.module_asymmetric_growth.report import render_asymmetric_growth_hunter_html
from revenuechaser.module_asymmetric_growth.tests.test_ag_dated_momentum_380 import bar, sessions
from revenuechaser.module_asymmetric_growth.tests.test_ag_info_only_150 import _QUOTE, _YF_ANNUAL, _edgar

# The bars close at 102 and their 63-session mean volume is 1.095x the base volume, so price * vol_90d is
# ~111.7 * base. 100 a day is thin (11,171); 10,000 a day is not (1.1M).
THIN_VOLUME = 100.0
LIQUID_VOLUME = 10_000.0




def _edgar_rows(*tickers) -> None:
    fund_store.put_edgar([_edgar(t) for t in tickers])






def _steps(result):
    return {s["key"]: s for s in result["funnel_steps"]}


# ── A. low liquidity: a note about scored names, never a drop ────────────────────────────────────────────────────



# ── B. unreadable SEC: the scored card whose financials are not EDGAR's ──────────────────────────────────────────



# ── C. counted exactly once: low liquidity first, then unreadable SEC ───────────────────────────────────────────







# ── the zero case and the untested case ─────────────────────────────────────────────────────────────────────────





# ── no network: a store-only scan reads the store and nothing else ──────────────────────────────────────────────



def test_a_summary_counted_from_cards_alone_reports_unknown_liquidity_not_zero():
    """A Refresh whose stored header does not match the table counts the summary from the cards, which do not carry
    ``vol_90d``. ``low_liquidity`` is then None (unknown) and never 0: printing 0 for a figure nobody measured
    would be a claim about data that was never read. ``unreadable_sec`` is a card property, so it still counts."""
    cards = [{"ticker": "AAA", "sector": "Technology", "total_points": 5, "tier": 2, "themes": [],
              "tech_breakthrough": False, "flags": [], "source": "yfinance"},
             {"ticker": "BBB", "sector": "Technology", "total_points": 5, "tier": 2, "themes": [],
              "tech_breakthrough": False, "flags": [], "source": "sec_edgar"}]

    summary = engine._summary(cards, None, {})

    assert summary["low_liquidity"] is None
    assert summary["unreadable_sec"] == 1
    # the funnel leaves an unknown note out rather than showing it as zero
    steps = engine._funnel_steps(2, 0, engine._Drops(), {}, 2,
                                 summary["low_liquidity"], summary["unreadable_sec"])
    assert [st["key"] for st in steps if st["kind"] == "note"] == ["unreadable_sec"]
    assert funnel.validate(steps) == []
