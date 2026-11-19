"""#80: a board rendered from a run whose provider health has a failure shows the banner.

The five data boards (and Settings) call ``provider_health_html(payload.get("provider_health"))``
and nothing used to write that key, so the banner was always empty. Each test builds the board
from a run that already has a failure and asserts the banner is non-empty. Offline; temp store.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from RevenueChaser.core import rawstore, screen_common

COMPLETE = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc).timestamp()
_BANNER = "rc-provider-health"


# ── Asymmetric Growth: the run's Yahoo ProviderHealth ────────────────────────────────────────────


# Swing: no test here. Its scan makes no provider call (#645, Swing review F1, 17 Nov 2026); the banner's
# render on that tab stays covered by test_provider_banner_every_tab.py.


# ── Fundamentals: an EDGAR fetch that raised ─────────────────────────────────────────────────────
def test_fundamentals_rendered_from_a_failed_edgar_run_shows_the_banner(rawstore_tmp_db, monkeypatch):
    from RevenueChaser.module_fundamentals import pipeline, report

    frame = pd.DataFrame({"Close": [10.0, 11.0, 12.0]})

    monkeypatch.setattr(pipeline, "fetch_universe_stats",
                        lambda **_k: ([{"ticker": "AAA", "market_cap": 1e9}], {}))
    monkeypatch.setattr(pipeline, "prefilter",
                        lambda rows: screen_common.Prefiltered(list(rows), {}, None, 0, []))
    monkeypatch.setattr(screen_common, "load_bars", lambda _t: (frame, frame))
    monkeypatch.setattr(pipeline, "ohlc_drop_reason", lambda _df: None)
    monkeypatch.setattr(pipeline._universe, "excluded_tickers", lambda: set())
    monkeypatch.setattr(pipeline._universe, "spine_gics", lambda *_a, **_k: {})

    class _Gics:
        sector = "Technology"
        industry = "Software"

    monkeypatch.setattr(pipeline._universe, "gics_of", lambda *_a, **_k: _Gics())

    def boom(*_a, **_k):
        raise RuntimeError("HTTP 503")

    monkeypatch.setattr(pipeline.sec_edgar, "get_fundamentals", boom)
    payload = pipeline.run_scan(no_fetch=False)
    html = report.render_fundamental_dashboard(payload)
    assert _BANNER in html
    assert "503" in html


# ── Co-movement: the fetch report the run already has ───────────────────────────────────────────
def test_comovement_rendered_from_a_failed_fetch_shows_the_banner(rawstore_tmp_db, monkeypatch):
    from RevenueChaser.module_comovement import engine, report

    monkeypatch.setattr(engine.ohlc, "fetch_bulk", lambda *_a, **_k: {
        "requested": 4, "cached": 1, "pending": 1, "fetched": 0, "failed": 2, "no_fetch": False})
    monkeypatch.setattr(engine.ohlc, "price_frame", lambda *_a, **_k: pd.DataFrame())
    payload = engine.run(no_fetch=False, tickers=["AAA", "BBB"])
    html = report.render_comovement_dashboard(payload)
    assert _BANNER in html
    assert "4 daily_bars çağrısının 2 tanesi başarısız" in html


# ── Relatedness: a provider stop the run already records ────────────────────────────────────────
def test_relatedness_rendered_from_an_auth_stop_shows_the_banner(rawstore_tmp_db, monkeypatch, tmp_path):
    from RevenueChaser.module_relatedness import engine, report

    monkeypatch.setattr(engine.config, "RELATEDNESS_JSON", tmp_path / "r.json")
    monkeypatch.setattr(engine.vc_engine, "fetch_corpus", lambda *_a, **_k: {"no_fetch": True})

    def auth(*_a, **_k):
        raise engine.RunStopped("auth", None, "DeepSeek rejected the API key (HTTP 401)")

    monkeypatch.setattr(engine, "build_profiles", auth)
    payload = engine.run(no_fetch=False, tickers=["AAA"], run_id="r1")
    html = report.render_relatedness_dashboard(payload)
    assert _BANNER in html
    assert "401" in html


# ── Settings: the stored column, not a live client ──────────────────────────────────────────────
