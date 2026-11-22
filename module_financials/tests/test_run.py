"""Tests for module_financials/run.py orchestration.

``run.py`` was previously untested. The load-bearing behaviour is that a
store-only render (``no_fetch=True``) must never die writing its report because
the output directory is missing: ``.cache`` is regenerable and may be cleared
while the server runs, and this module's write was the one writer in the repo
that did not recreate its parent — a cleared cache turned Refresh into a
FileNotFoundError that the caller could only swallow.
"""
from __future__ import annotations

from revenuechaser.rcdata.tests import universe_store
import revenuechaser.module_financials.run as fm




def test_run_no_fetch_requires_a_cached_payload(rawstore_tmp_db, tmp_path, monkeypatch):
    """A store-only render for a ticker with no cached payload raises, so the
    caller can fall back to an empty state instead of touching the network."""
    monkeypatch.setattr(fm, "OUTPUT_DIR", tmp_path)

    import pytest
    with pytest.raises(fm._NoCachedData):
        fm.run("ZZZZ", modules=["dcf"], output="html", no_fetch=True)




def _row(ticker, market_cap, sector):
    return {"ticker": ticker, "cik": "", "name": ticker, "market_cap": market_cap, "price": 10.0,
            "sector": sector, "industry": "x", "industry_group": "", "sub_industry": "",
            "quote": {"symbol": ticker}}






# ── the sector band keys are the Morningstar names the spine stores (#266) ────────────────────────────
import pytest


def test_embedded_sector_bands_match_the_json_file():
    """The embedded fallback and ``config/sector_defaults.json`` carry the same keys and numbers, so the DCF band
    is the same whether or not the file is readable."""
    import json
    from revenuechaser.core.gics_map import MORNINGSTAR_SECTORS
    from revenuechaser.module_financials import config
    from_file = json.loads(config.SECTOR_DEFAULTS_FILE.read_text(encoding="utf-8"))
    assert set(config.SECTOR_DEFAULTS) == set(from_file)
    assert set(config.SECTOR_DEFAULTS) - {"default"} <= set(MORNINGSTAR_SECTORS)
    for key, band in from_file.items():
        assert {k: tuple(v) for k, v in band.items()} == {k: tuple(v) for k, v in config.SECTOR_DEFAULTS[key].items()}


@pytest.mark.parametrize("sector", ["Technology", "Consumer Defensive", "Financial Services", "Energy", "Healthcare"])
def test_dcf_band_is_the_sector_band_with_or_without_the_json_file(tmp_path, monkeypatch, sector):
    """Every banded Morningstar sector gets its own band, not ``default``, from the file and from the embedded copy."""
    from revenuechaser.module_financials import config
    default = config.sector_defaults("Unclassified")
    from_file = config.sector_defaults(sector)
    assert from_file != default
    monkeypatch.setattr(config, "SECTOR_DEFAULTS_FILE", tmp_path / "missing.json")
    embedded = config.sector_defaults(sector)
    assert {k: tuple(v) for k, v in embedded.items()} == {k: tuple(v) for k, v in from_file.items()}
    assert embedded != config.sector_defaults("Unclassified")
