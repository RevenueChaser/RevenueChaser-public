"""OIPD board -> result history (#382, A3). Offline; the store is a temp DuckDB.

An OIPD Fetch records its run through ``core/history.record_run``: one ``result_runs`` header, the chain the fit used
in ``oipd_chain_history`` (the mirror of ``oipd_chain``, numbered by ``row_no``) and one ``oipd_fit_history`` row per
fitted expiry. OIPD is a run board: every run keeps its rows; a partial chain is kept and the run says 'partial'.
"""
from __future__ import annotations

import json
import zlib
from datetime import datetime, timezone

import pytest

from revenuechaser.core import ledger, rawstore
from revenuechaser.core.providers.result import ProviderResult
from revenuechaser.module_oipd import config, engine
from revenuechaser.module_oipd.tests.test_engine import _TRUE, _FakeUW, _chain_for, fixed_today  # noqa: F401

# 2026-10-06 is a Tuesday: 22:00 UTC = 18:00 ET (session complete); 14:00 UTC = 10:00 ET (intraday).
COMPLETE = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc).timestamp()
INTRADAY = datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc).timestamp()


class _PartialUW(_FakeUW):
    """The second expiry's page 2 failed: its contracts are the ones that arrived (half of them)."""

    def option_contracts_result(self, ticker, expiry=None, **kw):
        rows = _chain_for(expiry)
        if expiry == self.expiries[1]:
            return ProviderResult("partial", rows[: len(rows) // 2], {"page": 1, "status": 500}, "")
        return ProviderResult("ok", rows, None, "")


@pytest.fixture
def store(rawstore_tmp_db, fixed_today):  # noqa: F811
    ledger.take_notes()
    return rawstore_tmp_db


def _fetch(uw=None, ticker="TST"):
    capture: dict = {}
    payload = engine.run(uw or _FakeUW(), ticker, capture=capture)
    return payload, capture








def _unpack(cell):
    if isinstance(cell, (bytes, bytearray)):
        return json.loads(zlib.decompress(cell))
    return cell if not isinstance(cell, str) else json.loads(cell)


# ── the engine's capture ──

def test_a_fetch_captures_the_chain_it_saved_and_the_svi_of_each_fitted_expiry(store):
    payload, capture = _fetch()
    assert capture["status"] == "ok" and capture["errors"] == []
    stored = rawstore.query("SELECT * FROM oipd_chain WHERE ticker = 'TST' ORDER BY option_symbol", db="oipd")
    assert sorted(capture["chain"], key=lambda r: r["option_symbol"]) == stored
    assert sorted(capture["svi"]) == [e["date"] for e in payload["expiries"]]
    fitted = capture["svi"][payload["expiries"][0]["date"]]
    assert set(fitted) == {"a", "b", "rho", "m", "sigma"} and fitted["rho"] == pytest.approx(_TRUE["rho"], abs=0.05)


def test_the_payload_the_board_renders_is_unchanged_by_the_capture(store):
    with_capture, _ = _fetch()
    without = engine.run(_FakeUW(), "TST")
    for p in (with_capture, without):
        p.pop("generated_at"), p.pop("fetched_at")
    assert with_capture == without


def test_a_refresh_fills_no_capture(store):
    _fetch()
    capture: dict = {}
    engine.run(ticker="TST", no_fetch=True, capture=capture)
    assert capture == {}


# ── the record ──



_DENSITY = ("g_min_window", "clipped_pct", "min_var", "density_flag", "density_note", "density_g_min_shown")















# ── a degraded run: kept, partial (design C rule E) ──







