"""#354 C5: a fund the daily issuer or UW file does not hold is read from its newest Form N-PORT report, and each
stored list says which source served it -- including a UW list cut at UW's 250-line cap.

The fallback is what carries the Rotation board's holdings after Unusual Whales goes (avo's D3, 22 Nov 2026: an
ETF with no issuer file is read from the quarterly ``sec/nport`` Parquet, no UW sweep at any width)."""
from datetime import date

import pytest

from RevenueChaser.module_sector_rotation import etf_holdings
from RevenueChaser.module_sector_rotation.report import holdings_source_note, render_holdings_fragment
from RevenueChaser.rcdata import read

DAILY = date(2026, 11, 20)
REPORT = date(2026, 6, 30)


def _line(etf, ticker, weight, provider, as_of, name="", truncated=False):
    return {"etf": etf, "as_of": as_of, "provider": provider, "ticker": ticker, "name": name,
            "weight": weight, "truncated": truncated}


@pytest.fixture
def sources(monkeypatch):
    """SMH has a daily issuer list; PEJ has only an N-PORT report; VTI's UW list is cut at the cap."""
    daily = {"SMH": [_line("SMH", "NVDA", 20.0, "ishares", DAILY, "NVIDIA")],
             "VTI": [_line("VTI", f"T{i}", 1.0, "uw", DAILY, truncated=True)
                     for i in range(read.UW_HOLDINGS_CAP)]}
    nport = {"PEJ": [_line("PEJ", "MAR", 6.0, "nport", REPORT, "MARRIOTT INTL INC"),
                     _line("PEJ", None, 4.0, "nport", REPORT, "A FOREIGN LINE")]}
    asked_nport = []

    def fake_nport(etfs):
        asked_nport.extend(etfs)
        return [r for e in etfs for r in nport.get(e, [])]
    monkeypatch.setattr(read, "etf_holdings", lambda etfs: [r for e in etfs for r in daily.get(e, [])])
    monkeypatch.setattr(read, "etf_holdings_nport", fake_nport)
    return asked_nport


def test_a_fund_the_daily_file_does_not_hold_reads_its_newest_nport_report(sources):
    """Before this, the board showed "no stored holdings" for such a fund and the quarterly report it does hold
    went unread."""
    rows = etf_holdings.stored_holdings("PEJ")
    assert [r["ticker"] for r in rows] == ["MAR"]                 # the foreign line has no US ticker
    assert rows[0]["provider"] == "nport" and rows[0]["as_of"] == REPORT
    assert sources == ["PEJ"]


def test_a_fund_with_a_daily_list_is_served_from_it_and_nport_is_not_asked(sources):
    """The daily issuer file wins: the quarterly report is a fallback, never a second opinion."""
    rows = etf_holdings.stored_holdings("SMH")
    assert [(r["ticker"], r["provider"], r["as_of"]) for r in rows] == [("NVDA", "ishares", DAILY)]
    assert sources == []


def test_a_fund_neither_source_holds_is_still_no_rows(sources):
    assert etf_holdings.stored_holdings("KBE") == []


def test_a_stored_list_carries_the_cut_flag_of_its_source(sources):
    rows = etf_holdings.stored_holdings("VTI")
    assert len(rows) == read.UW_HOLDINGS_CAP and all(r["truncated"] for r in rows)
    assert not any(r["truncated"] for r in etf_holdings.stored_holdings("PEJ"))


# ── what the board says about the source (#354 C5: "says which") ────────────────────────────────────────────────

def test_the_note_names_the_source_and_the_day_it_was_published():
    note = holdings_source_note([_line("PEJ", "MAR", 6.0, "nport", REPORT)])
    assert "N-PORT" in note and "quarterly" in note and "2026-06-30" in note


def test_the_note_warns_that_a_cut_list_is_not_the_whole_fund():
    note = holdings_source_note([_line("VTI", "AAPL", 6.0, "uw", DAILY, truncated=True)])
    assert "250" in note and "not the whole fund" in note


def test_an_issuer_file_is_named_by_its_issuer_not_its_provider_key():
    """"Source: ishares" reads as a typo on a board; the issuers' keys get their own labels."""
    assert "iShares file" in holdings_source_note([_line("SMH", "NVDA", 20.0, "ishares", DAILY)])
    assert holdings_source_note([_line("X", "A", 1.0, "newissuer", DAILY)]).startswith("Source: newissuer")


def test_rows_without_a_provider_get_no_note():
    """The Rotation Fetch's own cached rows carry no provenance; inventing one would be a guess."""
    assert holdings_source_note([{"ticker": "AAPL", "weight": 6.0}]) == ""


def test_the_fragment_shows_the_source_note_and_escapes_it():
    frag = render_holdings_fragment([{"ticker": "MAR", "name": "Marriott", "weight": 6.0, "close": None,
                                      "rs_1w": None, "rs_1m": None, "rs_3m": None,
                                      "provider": "nport", "as_of": REPORT}])
    assert "SEC N-PORT (quarterly)" in frag and "2026-06-30" in frag
    plain = render_holdings_fragment([{"ticker": "MAR", "name": "Marriott", "weight": 6.0, "close": None,
                                       "rs_1w": None, "rs_1m": None, "rs_3m": None}])
    assert "Source:" not in plain
