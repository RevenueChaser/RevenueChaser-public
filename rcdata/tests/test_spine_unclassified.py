"""avo, 17 Nov 2026: the listed names the spine left ``Unclassified`` get a sector from a fallback.

(A) a SIC but no Compustat GICS: the SIC table (``gics_source = 'sic'``); (B) SIC 9995 / 6770: the ``Shell/SPAC``
bucket; (C) no Compustat link and no SIC: ``gics_manual.json`` (``gics_source = 'manual'``), one reason per row.
"""
from __future__ import annotations

import json

import pytest

from RevenueChaser.core.gics_map import SHELL_SPAC, UNCLASSIFIED, canonical_sector
from RevenueChaser.rcdata.build.spine import security

from . import spine_fixture as fx
from .test_spine_spac_sic_240 import _sec, built_with  # noqa: F401 - the fixture build with one SIC replaced

MSFT_GICS = {"gsector": "45", "ggroup": "4510"}


@pytest.mark.parametrize("sic, want", [
    ("7372", ("Technology", "Software & Services")),
    ("2836.0", ("Healthcare", "Pharmaceuticals, Biotechnology & Life Sciences")),
    ("6036", ("Financial Services", "Banks")),
    ("4412", ("Industrials", "Transportation")),
])
def test_a_name_with_a_sic_and_no_gics_takes_the_sic_tables_sector(sic, want):
    assert security.bridge_sector("X", None, sic, {}) == (*want, "sic")


@pytest.mark.parametrize("sic", ["9995", "6770"])
def test_a_shell_sic_is_the_shell_bucket_not_a_sector(sic):
    assert security.bridge_sector("AESP", None, sic, {}) == (SHELL_SPAC, SHELL_SPAC, "sic")


def test_compustat_gics_beats_the_sic():
    assert security.bridge_sector("MSFT", MSFT_GICS, "9995", {}) == ("Technology", "Software & Services",
                                                                     "wrds/co_hgic")


def test_the_manual_file_beats_everything():
    manual = {"MSFT": {"gsector": "50", "ggroup": "5020", "reason": "x"}}
    assert security.bridge_sector("MSFT", MSFT_GICS, "7372", manual) == (
        "Communication Services", "Media & Entertainment", "manual")


@pytest.mark.parametrize("sic", [None, "", "9999", "nan"])
def test_an_unknown_sic_stays_unclassified_with_no_source(sic):
    assert security.bridge_sector("X", None, sic, {}) == (UNCLASSIFIED, UNCLASSIFIED, None)


def test_the_checked_in_manual_file_holds_the_eleven_names_avo_approved():
    rows = security.gics_manual()
    assert set(rows) == {"FWONA", "FWONK", "AGMB", "DUKR", "KNDI", "NSTR", "SOAR", "UROY", "WQEY", "XHG", "XTLB"}
    assert security.bridge_sector("FWONK", None, None, rows)[:2] == ("Communication Services",
                                                                     "Media & Entertainment")


def test_a_manual_row_with_an_unknown_code_or_no_reason_fails_loudly(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"rows": {"X": {"gsector": "99", "ggroup": "4510", "reason": "r"}}}))
    with pytest.raises(ValueError):
        security.gics_manual(p)
    p.write_text(json.dumps({"rows": {"X": {"gsector": "45", "ggroup": "4510"}}}))
    with pytest.raises(ValueError):
        security.gics_manual(p)


def test_the_shell_bucket_survives_canonical_sector_so_boards_can_filter_on_it():
    assert canonical_sector(SHELL_SPAC) == SHELL_SPAC and canonical_sector("shell/spac") == SHELL_SPAC


# ── The build ────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def no_cna_gics(monkeypatch):
    monkeypatch.setattr(fx, "HGIC", [g for g in fx.HGIC if g["gvkey"] != "002968"])


def test_the_build_gives_a_linked_name_with_no_gics_its_sic_sector(no_cna_gics, built_with):
    built_with("002968", "6331")                        # CNA, with its GICS row taken away: insurance carriers
    built = _sec("CNA")
    assert (built["sector"], built["gics_source"]) == (UNCLASSIFIED, None)   # 6331 is not in the table


def test_the_build_writes_the_sic_sector_and_source(no_cna_gics, monkeypatch, built_with):
    monkeypatch.setitem(security.SIC_GICS, 6331, ("40", "4030"))
    built_with("002968", "6331")
    built = _sec("CNA")
    assert (built["sector"], built["industry"], built["gics_source"], built["gsector"]) == (
        "Financial Services", "Insurance", "sic", None)


def test_the_build_puts_a_shell_in_the_shell_bucket(no_cna_gics, built_with):
    built_with("002968", "9995")
    built = _sec("CNA")
    assert (built["sector"], built["gics_source"], built["tier"]) == (SHELL_SPAC, "sic", "A")
