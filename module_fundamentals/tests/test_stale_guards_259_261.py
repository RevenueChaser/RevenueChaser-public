"""#259/#261 on the Fundamentals path, and #645: the name and the cap are the spine row's, with no Yahoo ``.info`` read."""
from __future__ import annotations

import pandas as pd

from RevenueChaser.module_fundamentals import pipeline


def _patch_row_inputs(monkeypatch, frame: pd.DataFrame):
    monkeypatch.setattr(pipeline.sec_edgar, "get_fundamentals", lambda t, no_fetch=False: ([{"x": 1}], [], {}))
    monkeypatch.setattr(pipeline.screen_common, "load_bars", lambda *a, **k: (frame, frame))     # D01 (C12)
    monkeypatch.setattr(pipeline, "ohlc_drop_reason", lambda df: None)
    monkeypatch.setattr(pipeline, "compute_indicators", lambda df, spy, **k: {"price": 10.0, "sma200": 5.0,
                                                                              "within_52w_high_pct": 0.9})
    monkeypatch.setattr(pipeline, "_ttm_metrics", lambda q, a: {k: None for k in (
        "rev_growth_ttm", "fcf_margin", "ro40", "ro40_basis", "ttm_revenue", "ttm_net_income")})
    monkeypatch.setattr(pipeline, "_quality_metrics", lambda a, q=None, **_: {k: None for k in (
        "gross_margin", "roic", "net_debt_ebitda", "total_equity")})


def test_a_stale_bar_frame_is_counted_and_no_refetch_is_refused(monkeypatch):
    frame = pd.DataFrame({"Close": [1.0]})
    frame.attrs["stale"] = True
    frame.attrs["short_refetch_refused"] = True
    _patch_row_inputs(monkeypatch, frame)
    row = pipeline._compute_row({"ticker": "AAA"}, None, spine={})
    assert row["ohlc_stale"] is True and "short_refetch_refused" not in row    # D01 bars are never refused (PR 6)
    quality = pipeline.build_payload([row], run_stats={})["data_quality"]
    assert quality["short_refetch_refused"] == 0 and "stale_info" not in quality


def test_the_name_and_cap_are_the_spine_rows_and_yahoo_is_never_asked(monkeypatch):
    _patch_row_inputs(monkeypatch, pd.DataFrame({"Close": [1.0]}))
    assert not hasattr(pipeline, "load_ticker_info"), "#645: Fundamentals reads no Yahoo .info"
    row = pipeline._compute_row({"ticker": "AAA", "name": "Aaa Corp", "market_cap": 2e9}, None, spine={})
    assert row["name"] == "Aaa Corp" and row["market_cap"] == 2e9 and "info_stale" not in row
    bare = pipeline._compute_row({"ticker": "BBB"}, None, spine={})
    assert bare["name"] == "" and bare["market_cap"] is None
