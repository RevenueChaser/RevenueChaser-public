"""Fable review Part B (Earnings Radar, R5; #256). Offline.

``_parse_short_row`` made up a "utilization", short interest / (short interest + shares available), and R5 Z-scored
it at weight 0.2. UW's short screener serves no utilization field, and docs/module_earnings-radar/redesign.md R5 says "there is no
utilization field, never invent one". Since #256 the squeeze is a ``none`` / ``fuel`` tag off the short interest or
the borrow fee: no utilization, no Z ladder, and nothing derived from the shares available.
"""
import inspect

from RevenueChaser.core.providers.unusual_whales import UWClient
from RevenueChaser.module_earnings_radar.rules.rule5_positioning import score as r5_score


def test_the_short_row_carries_no_utilization():
    row = {"si_float": "0.017", "fee_rate": "0.2782", "days_to_cover": "2.1", "short_interest": "75000",
           "short_shares_available": "10000000"}
    assert sorted(UWClient._parse_short_row(row)) == ["borrow_fee", "days_to_cover", "si_pct"]
    assert UWClient._parse_short_row({}) == {"si_pct": None, "borrow_fee": None, "days_to_cover": None}


def test_the_squeeze_tag_reads_short_interest_and_the_fee_only():
    """No utilization argument, and nothing derived from the shares available."""
    assert "utilization" not in inspect.signature(r5_score).parameters
    r = r5_score(short_interest_pct_float=9, days_to_cover=2, borrow_fee=2)
    assert r.raw_metrics["squeeze_tag"] == "none"
    assert "utilization" not in r.raw_metrics
    assert not any("utilization" in reason for reason in r.reasons)
