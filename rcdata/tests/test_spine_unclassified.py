"""avo, 17 Nov 2026: the listed names the spine left ``Unclassified`` get a sector from a fallback.

(A) a SIC but no Compustat GICS: the SIC table (``gics_source = 'sic'``); (B) SIC 9995 / 6770: the ``Shell/SPAC``
bucket; (C) no Compustat link and no Compustat SIC: the SEC's own SIC (``gics_source = 'sec_sic'``, avo's K5,
18 Nov 2026; the eleven hand rows of ``gics_manual.json`` are gone), a sector code only.
"""
from __future__ import annotations

import json

import pytest

from RevenueChaser.core.gics_map import SHELL_SPAC, UNCLASSIFIED, canonical_sector
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.spine import security

from . import spine_fixture as fx
from .test_spine_security import run_all
from .test_spine_spac_sic_240 import _sec, built_with  # noqa: F401 - the fixture build with one SIC replaced

MSFT_GICS = {"gsector": "45", "ggroup": "4510"}


def test_a_sic_row_carries_the_gics_codes_its_names_came_from():
    assert security.bridge_sector("X", None, "7372", {})[3:] == ("45", "4510")


@pytest.mark.parametrize("sic, want", [
    ("7372", ("Technology", "Software & Services")),
    ("2836.0", ("Healthcare", "Pharmaceuticals, Biotechnology & Life Sciences")),
    ("6036", ("Financial Services", "Banks")),
    ("4412", ("Industrials", "Transportation")),
])
def test_a_name_with_a_sic_and_no_gics_takes_the_sic_tables_sector(sic, want):
    assert security.bridge_sector("X", None, sic, {})[:3] == (*want, "sic")


@pytest.mark.parametrize("sic", ["9995", "6770"])
def test_a_shell_sic_is_the_shell_bucket_not_a_sector(sic):
    assert security.bridge_sector("AESP", None, sic, {}) == (SHELL_SPAC, SHELL_SPAC, "sic", None, None)


def test_compustat_gics_beats_the_sic():
    assert security.bridge_sector("MSFT", MSFT_GICS, "9995", {}) == ("Technology", "Software & Services",
                                                                     "wrds/co_hgic", "45", "4510")


def test_the_manual_file_beats_everything():
    manual = {"MSFT": {"gsector": "50", "ggroup": "5020", "reason": "x"}}
    assert security.bridge_sector("MSFT", MSFT_GICS, "7372", manual) == (
        "Communication Services", "Media & Entertainment", "manual", "50", "5020")


@pytest.mark.parametrize("sic", [None, "", "9999", "nan"])
def test_an_unknown_sic_stays_unclassified_with_no_source(sic):
    assert security.bridge_sector("X", None, sic, {}) == (UNCLASSIFIED, UNCLASSIFIED, None, None, None)


# The eleven names avo approved by hand on 17 Nov 2026, each with the SIC the SEC assigns it (as the hand rows quoted
# it) and the GICS sector and group the hand row gave. K5, 18 Nov 2026: the rule must give the same, with no row.
ELEVEN = [("FWONA", "4833", "50", "5020"), ("FWONK", "4833", "50", "5020"), ("AGMB", "2836", "35", "3520"),
          ("DUKR", "3721", "20", "2010"), ("KNDI", "3714", "25", "2510"), ("NSTR", "4899", "50", "5010"),
          ("SOAR", "4522", "20", "2030"), ("UROY", "1090", "10", "1010"), ("WQEY", "7374", "45", "4510"),
          ("XHG", "6411", "40", "4030"), ("XTLB", "2834", "35", "3520")]


@pytest.mark.parametrize("ticker, sec_sic, gsector, ggroup", ELEVEN)
def test_the_eleven_hand_rows_are_gone_and_the_secs_sic_gives_each_the_same_sector(ticker, sec_sic, gsector, ggroup):
    assert security.gics_manual() == {}
    assert security.bridge_sector(ticker, None, None, {}, sec_sic)[2:] == ("sec_sic", gsector, ggroup)


@pytest.mark.parametrize("sec_sic", ["6770", "9995"])
def test_a_shell_code_of_the_secs_decides_nothing(sec_sic):
    """The SEC changes a code only on request: a company that merged with a blank check still reads 6770 there."""
    assert security.bridge_sector("X", None, None, {}, sec_sic) == (UNCLASSIFIED, UNCLASSIFIED, None, None, None)


def test_compustats_sic_beats_the_secs():
    assert security.bridge_sector("X", None, "7372", {}, "2834")[2:] == ("sic", "45", "4510")
    assert security.bridge_sector("X", None, "9995", {}, "2834")[:3] == (SHELL_SPAC, SHELL_SPAC, "sic")
    assert security.bridge_sector("MSFT", MSFT_GICS, None, {}, "2834")[2] == "wrds/co_hgic"


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
    assert (built["sector"], built["industry"], built["gics_source"], built["gsector"], built["ggroup"],
            built["gsubind"]) == ("Financial Services", "Insurance", "sic", "40", "4030", None)


def test_the_build_puts_a_shell_in_the_shell_bucket(no_cna_gics, built_with):
    built_with("002968", "9995")
    built = _sec("CNA")
    assert (built["sector"], built["gics_source"], built["tier"]) == (SHELL_SPAC, "sic", "A")


def _sec_header(cik: str, sic: str) -> None:
    """One company's ``header.parquet`` as ``sec/filings`` writes it (only the columns this build reads)."""
    import duckdb
    folder = base.parquet_root() / "sec" / "filings" / f"cik={cik}"
    folder.mkdir(parents=True, exist_ok=True)
    duckdb.connect().execute(f"COPY (SELECT '{cik}' AS cik, '{sic}' AS sic) TO '{folder / 'header.parquet'}' "
                             "(FORMAT parquet)")


def test_the_build_takes_the_sector_of_a_name_compustat_does_not_know_from_the_secs_sic(built_with):
    """K5: OTCX has no Compustat company at all, so no GICS and no Compustat SIC; the SEC's header has one."""
    _sec_header("3000001", "3721")
    built_with("002968", "6331")
    built = _sec("OTCX")
    assert (built["sector"], built["industry"], built["gics_source"], built["gsector"], built["ggroup"]) == (
        "Industrials", "Capital Goods", "sec_sic", "20", "2010")
    assert built["sic"] is None and built["gsubind"] is None         # the served ``sic`` stays Compustat's


def test_a_stale_blank_check_code_of_the_secs_never_types_a_name_a_spac(built_with):
    """The plan-v4 review's blocker: one ``sic`` value fed the sector AND the type rule, so the SEC's 6770 would
    have typed an operating company a SPAC, which is Tier B and out of My Universe."""
    _sec_header("3000001", "3721")
    built_with("002968", "6331")
    before = _sec("OTCX")
    assert before["gics_source"] == "sec_sic"                    # the header is read: the next build reads 6770
    _sec_header("3000001", "6770")
    run_all("2026-10-28", names=[security.NAME])
    after = _sec("OTCX")
    assert (after["security_type"], after["type_source"], after["tier"]) == (
        before["security_type"], before["type_source"], before["tier"])
    assert after["security_type"] != "spac" and after["sector"] == UNCLASSIFIED and after["sic"] is None
