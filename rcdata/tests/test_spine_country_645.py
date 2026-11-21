"""``security.country``: where the company's business is, Compustat first (#645, avo 21 Nov 2026).

avo, 21 Nov 2026: "Wrds de ulke bilgisini de al". Compustat carries the company's own country
(``comp.company.loc``, alpha-3) and the spine already stages it; the SEC submissions header's business address,
added for the fundamentals freeze (#645 G2), stays the fallback for a name Compustat does not link or does not
place. Asymmetric Growth's non-US test is the reader (``module_asymmetric_growth/engine._cached_financials``).
"""
from __future__ import annotations

import duckdb
import pytest

from RevenueChaser.rcdata import serving
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.spine import iso3166, security

from .test_spine_spac_sic_240 import _sec, built_with  # noqa: F401 - the fixture build


# ── The rule ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_compustats_own_country_is_the_answer_and_is_read_alpha_2():
    assert security.bridge_country("JPN") == ("JP", security.LOC_SOURCE)
    assert security.bridge_country("USA") == ("US", security.LOC_SOURCE)
    assert security.bridge_country("irl") == ("IE", security.LOC_SOURCE)


def test_compustat_beats_the_sec_business_address():
    assert security.bridge_country("JPN", "US") == ("JP", security.LOC_SOURCE)


@pytest.mark.parametrize("loc", [None, "", "   ", "ZZZ", "nan"])
def test_without_compustat_the_sec_business_address_answers(loc):
    assert security.bridge_country(loc, "DE") == ("DE", security.SEC_COUNTRY_SOURCE)
    assert security.bridge_country(loc, " de ") == ("DE", security.SEC_COUNTRY_SOURCE)


@pytest.mark.parametrize("sec_country", [None, "", "  "])
def test_a_name_neither_places_has_no_country_and_no_source(sec_country):
    """Never a guess: a board reads NULL as unknown, and "not US" is a different statement."""
    assert security.bridge_country(None, sec_country) == (None, None)


def test_the_iso_map_is_the_one_published_list_both_readers_use():
    from RevenueChaser.rcdata.build.spine import etf_class
    assert etf_class.ISO_FILE == iso3166.FILE
    assert iso3166.alpha2("USA") == "US" and iso3166.alpha2("ZZZ") is None


# ── The build ────────────────────────────────────────────────────────────────────────────────────────────────

def _sec_header(cik: str, **columns: str) -> None:
    """One company's ``header.parquet`` as ``sec/filings`` writes it, with the columns named."""
    folder = base.parquet_root() / "sec" / "filings" / f"cik={cik}"
    folder.mkdir(parents=True, exist_ok=True)
    cols = ", ".join(f"'{v}' AS {c}" for c, v in {"cik": cik, **columns}.items())
    duckdb.connect().execute(f"COPY (SELECT {cols}) TO '{folder / 'header.parquet'}' (FORMAT parquet)")


def test_the_build_serves_compustats_country_for_a_linked_name(built_with):
    """TM's company is Compustat's Toyota (``loc`` JPN); MSFT's is USA."""
    built_with("002968", "6331")
    assert (_sec("TM")["country"], _sec("TM")["country_source"]) == ("JP", security.LOC_SOURCE)
    assert (_sec("MSFT")["country"], _sec("MSFT")["country_source"]) == ("US", security.LOC_SOURCE)
    assert _sec("ETN")["country"] == "IE"            # an Irish plc listed in the US


def test_the_build_falls_back_to_the_sec_address_for_a_name_compustat_does_not_know(built_with):
    """OTCX has no Compustat company at all, so no ``loc``; its submissions header has a business address."""
    _sec_header("3000001", sic="3721", business_country="CA")
    built_with("002968", "6331")
    assert (_sec("OTCX")["country"], _sec("OTCX")["country_source"]) == ("CA", security.SEC_COUNTRY_SOURCE)


def test_a_name_neither_source_places_is_served_with_no_country(built_with):
    built_with("002968", "6331")
    assert (_sec("OTCX")["country"], _sec("OTCX")["country_source"]) == (None, None)


def test_the_served_table_has_the_two_columns_so_a_reader_can_ask_for_them(built_with):
    built_with("002968", "6331")
    with serving.open_read("spine") as con:
        held = {r[0] for r in con.execute("DESCRIBE security").fetchall()}
    assert {"country", "country_source"} <= held


def test_a_filing_list_written_before_the_column_reads_as_not_known_not_as_an_error(built_with):
    """``sec/filings`` wrote no ``business_country`` before #645 G2: such a store builds, with no country."""
    _sec_header("3000001", sic="3721")
    built_with("002968", "6331")
    assert _sec("OTCX")["country"] is None


def test_the_spine_version_was_bumped_for_the_columns():
    """A change to a kind's served tables bumps its number in its own PR (the box rule)."""
    assert serving.SERVING_SCHEMA_VERSION["spine"] >= 10


def test_the_universe_row_the_boards_read_carries_the_country(monkeypatch):
    """``core.universe`` is how a board gets it: Asymmetric Growth reads the row, never the spine file.

    The spine rows are stubbed here (``read.universe`` is ``SELECT *``, so the column arrives by itself); the
    build above is what proves the column is served.
    """
    from RevenueChaser.core import universe
    monkeypatch.setattr(universe, "_universe_ids",
                        lambda: [{"ticker": "TM", "country": "JP", "security_type": "adr"},
                                 {"ticker": "MSFT", "country": "US", "security_type": "common"},
                                 {"ticker": "OTCX", "security_type": "common"}])
    monkeypatch.setattr("RevenueChaser.core.spine_reads.latest_market", lambda tickers: {})
    rows = {r["ticker"]: r for r in universe._spine_universe()}
    assert rows["TM"]["country"] == "JP"
    assert rows["MSFT"]["country"] == "US"
    assert rows["OTCX"]["country"] is None          # unknown, and the board must not read it as "not US"
