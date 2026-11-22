"""``core/providers/tickerinside.py``: the keyless ETF holdings files, their key shapes and the one licence rule
the code has to enforce (#1365).

The shapes here are the live files of 22 Nov 2026: ``fund/smh.json`` (from a SEC filing, 25 positions),
``fund/voo.json`` (``BRK.B`` and ``BF.B`` among 504) and ``fund/efa.json`` (``7203.JP``, ``SAP.DE``, ``ASML.NL``).
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.core.providers import tickerinside as ti


def _file(ticker="SMH", holdings=None, **extra) -> bytes:
    body = {"ticker": ticker, "holdings": holdings if holdings is not None else {"NVDA": 19.3652, "TSM": 9.243},
            "holdings_as_of": "2026-09-30", "source_layer": "sec_nport", "positions": 25,
            "cite_as": "TickerInside, VanEck Semiconductor ETF (SMH), ... CC BY 4.0"}
    body.update(extra)
    return json.dumps(body).encode()


# ── The licence: history and flows may not be collected on a schedule ───────────────────────────────────────

@pytest.mark.parametrize("path", ["/history/smh.json", "/history/smh/2023-06-30.json", "/history.json",
                                  "/quarterly/smh.json", "/flows.json", "/flows/nvda.json"])
def test_the_history_and_flows_paths_are_refused_in_code(path):
    """Their terms (https://tickerinside.com/legal/#history) are not CC BY 4.0: free per request, but fetching many
    funds' history on a schedule to store it is not allowed, and a builder is a schedule. Our own history comes from
    the SEC's bulk sets (#354 C7), so no code path here may ask for these."""
    with pytest.raises(ti.LicenceError, match="history or flows"):
        ti.check_path(path)


def test_the_files_a_builder_does_read_are_allowed():
    assert ti.fund_url("SMH").endswith("/fund/smh.json")
    assert ti.funds_url().endswith("/funds.json")
    assert ti.check_path("/fund/voo.json") == "/fund/voo.json"


def test_a_fund_url_is_the_ticker_in_lower_case_and_nothing_else():
    assert ti.fund_url("brk.b").endswith("/fund/brk.b.json")
    for bad in ("", "../funds", "SMH/holdings", "a b"):
        with pytest.raises(ValueError):
            ti.fund_url(bad)


# ── Which keys are US tickers (the site's own keying, read 22 Nov 2026) ─────────────────────────────────────

@pytest.mark.parametrize("key, served", [
    ("NVDA", "NVDA"),
    ("BRK.B", "BRK-B"),          # a US share class keeps its dot there, and is our dash form here
    ("BF.B", "BF-B"),
    ("7203.JP", None),           # Toyota in Tokyo: a market, not a class
    ("SAP.DE", None),
    ("ASML.NL", None),
    ("JPM.PFD", None),           # a preferred share written under the common ticker
    ("", None),
])
def test_a_key_is_served_only_when_it_is_a_us_common_ticker(key, served):
    assert ti.served_ticker(key) == served


# ── The fund file ───────────────────────────────────────────────────────────────────────────────────────────

def test_a_fund_file_is_read_whole_heaviest_first_with_its_date_and_layer():
    answer = ti.parse_fund(_file(), "SMH")
    assert [h["ticker"] for h in answer["holdings"]] == ["NVDA", "TSM"]
    assert answer["holdings"][0]["weight"] == 19.3652
    assert answer["as_of"] == "2026-09-30" and answer["layer"] == "sec_nport" and answer["positions"] == 25
    assert "CC BY 4.0" in answer["cite_as"]


def test_a_holding_carries_no_cusip_and_no_name_because_the_source_serves_neither():
    """CUSIP and ISIN are licensed codes and are not published there, and the file gives no company name: a row
    from here says so instead of inventing either."""
    (line,) = ti.parse_fund(_file(holdings={"NVDA": 1.0}), "SMH")["holdings"]
    assert line == {"ticker_raw": "NVDA", "ticker": "NVDA", "cusip": None, "name": None, "weight": 1.0}


def test_a_foreign_line_keeps_its_raw_key_and_is_not_served_as_a_us_ticker():
    answer = ti.parse_fund(_file("EFA", {"NVDA": 2.0, "7203.JP": 1.0}, source_layer="issuer"), "EFA")
    assert [(h["ticker_raw"], h["ticker"]) for h in answer["holdings"]] == [("NVDA", "NVDA"), ("7203.JP", None)]
    assert answer["layer"] == "issuer"


def test_a_key_the_file_lists_under_abroad_is_not_served_as_the_us_company_of_that_ticker():
    """``abroad`` is the file's own list of foreign codes that the US list gives to another company. Serving one as
    that company would put a wrong holding on a board, so the line stays raw."""
    answer = ti.parse_fund(_file("EFA", {"RY": 2.0, "SAN": 1.0}, abroad=["SAN"]), "EFA")
    assert [(h["ticker_raw"], h["ticker"]) for h in answer["holdings"]] == [("RY", "RY"), ("SAN", None)]


def test_a_weight_that_is_not_a_number_is_none_and_sorts_last():
    answer = ti.parse_fund(_file(holdings={"NVDA": None, "TSM": 1.0}), "SMH")
    assert [(h["ticker"], h["weight"]) for h in answer["holdings"]] == [("TSM", 1.0), ("NVDA", None)]


@pytest.mark.parametrize("data, match", [
    (b"not json", "not JSON"),
    (b"[]", "not an object"),
    (json.dumps({"ticker": "VOO", "holdings": {}}).encode(), "holds VOO"),
    (json.dumps({"ticker": "SMH"}).encode(), "no holdings object"),
    (json.dumps({"ticker": "SMH", "holdings": []}).encode(), "no holdings object"),
])
def test_a_file_of_another_fund_or_another_shape_is_refused(data, match):
    """A moved URL answers a page and a changed shape answers something else: both fail the fund loudly instead of
    being read some other way."""
    with pytest.raises(ValueError, match=match):
        ti.parse_fund(data, "SMH")


def test_the_licence_and_the_attribution_target_are_stated_in_the_module():
    """The licence's condition is a link where a figure is shown, so the link has to live somewhere a caller can
    reach: here, and in every file's own ``cite_as``."""
    assert ti.LICENCE == "CC BY 4.0" and ti.SITE == "https://tickerinside.com"


# ── The index files: which fund files changed, and which the site kept at an older issuer file (plan B1) ────

def _index(lines: str, list_sha256: str | None = None, gz: bool = True) -> tuple[bytes, bytes]:
    import gzip
    import hashlib
    text = lines.encode()
    manifest = json.dumps({"manifest_version": 1, "files": {
        "list": "https://tickerinside.com/api/v1/sha256sums.txt.gz",
        "list_sha256": list_sha256 or hashlib.sha256(text).hexdigest()}}).encode()
    return manifest, gzip.compress(text) if gz else text


def test_the_index_files_are_allowed_paths():
    assert ti.manifest_url().endswith("/api/v1/manifest.json")
    assert ti.status_url().endswith("/api/v1/status.json")
    assert ti.sums_url().endswith("/api/v1/sha256sums.txt.gz")


def test_the_file_list_gives_each_fund_files_sha256_by_ticker_and_nothing_else():
    """The live list of 21 Nov 2026: 13,607 lines, 2,694 of them ``api/v1/fund/<t>.json``. Only those are read."""
    manifest, sums = _index("2850cee0  api/v1/fund/smh.json\n"
                            "e20c1d2a  api/v1/fund/brk.b.json\n"
                            "5ae6a302  api/v1/ai-infrastructure-debt/aligned.json\n"
                            "11111111  api/v1/history/smh.json\n")
    assert ti.fund_hashes(manifest, sums) == {"SMH": "2850cee0", "BRK.B": "e20c1d2a"}


def test_a_list_served_already_unzipped_is_read_the_same():
    manifest, sums = _index("2850cee0  api/v1/fund/smh.json\n", gz=False)
    assert ti.fund_hashes(manifest, sums) == {"SMH": "2850cee0"}


def test_a_list_that_is_not_the_one_the_manifest_names_is_refused():
    """``list_sha256`` is the sha256 of the uncompressed list (measured 22 Nov 2026). A list of another build would
    say a changed file is unchanged, so it is no list at all."""
    manifest, sums = _index("2850cee0  api/v1/fund/smh.json\n", list_sha256="0" * 64)
    with pytest.raises(ValueError, match="list_sha256"):
        ti.fund_hashes(manifest, sums)
    with pytest.raises(ValueError):
        ti.fund_hashes(b"{}", sums)


def test_kept_previous_is_read_from_the_status_file():
    status = json.dumps({"schema": 1, "run": {"fetch_holdings": {"funds_attempted": 425, "kept_previous": [
        {"ticker": "CLOU", "issuer": "Global X", "since": "2026-11-13", "holdings_as_of": "2026-11-11"}]}}}).encode()
    assert ti.kept_previous(status) == [
        {"ticker": "CLOU", "issuer": "Global X", "since": "2026-11-13", "holdings_as_of": "2026-11-11"}]
    with pytest.raises(ValueError):
        ti.kept_previous(json.dumps({"schema": 1}).encode())
