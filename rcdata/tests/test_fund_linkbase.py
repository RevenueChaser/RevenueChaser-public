"""The annual report's definition linkbase (#1048): the parser (``linkbase.py``), its fetch beside the document
(``sec/filings``), ``segment_revenue.report_tables``, and the member sets that sum to the revenue
(``read.segment_sets``).

``amzn_def.xml`` and ``aapl_def.xml`` are hand-reduced from the two companies' real FY2025 linkbases: two roles
each, the ``ProductOrServiceAxis`` chain only."""
from __future__ import annotations

import pytest

from RevenueChaser.core.providers import sec_edgar
from RevenueChaser.rcdata import ops, read
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.fundamentals import filings, linkbase, tables

from . import fund_fixture as fx
from .sec_answers import MISSING_HEADERS, MISSING_OBJECT

AMZN_LINES = "SegmentInformationDisaggregationofRevenueDetails"
AMZN_STATEMENT = "ConsolidatedStatementsofOperations"
AAPL_LINES = "RevenueDisaggregatedNetSalesandPortionofNetSalesThatWasPreviouslyDeferredDetails"
AAPL_STATEMENT = "CONSOLIDATEDSTATEMENTSOFOPERATIONS"


# ── The parser ────────────────────────────────────────────────────────────────────────────────────────────────

def test_each_table_declares_its_own_members_on_the_product_axis(fixture_text):
    found = linkbase.parse(fixture_text("amzn_def.xml"))
    by_table: dict[str, set[str]] = {}
    for (axis, member), roles in found.items():
        assert axis == "product"
        for role in roles:
            by_table.setdefault(role, set()).add(member)
    assert by_table == {
        AMZN_STATEMENT: {"Product", "Service", "Products And Services Domain"},
        AMZN_LINES: {"Online Stores", "Physical Stores", "Third Party Seller Services", "Advertising",
                     "Subscription Services", "Amazon Web Services", "Other Services",
                     "Products And Services Domain"}}


def test_a_member_two_tables_declare_names_both(fixture_text):
    """Apple: Service stands on the income statement beside Product and in the net sales note beside the devices."""
    found = linkbase.parse(fixture_text("aapl_def.xml").encode("utf-8"))
    assert found[("product", "Service")] == [AAPL_STATEMENT, AAPL_LINES]
    assert found[("product", "Product")] == [AAPL_STATEMENT]
    assert found[("product", "I Phone")] == [AAPL_LINES]


def test_the_axis_is_named_as_the_inline_xbrl_names_it_and_another_axis_is_not_read():
    xml = fx.def_linkbase({"Note": {"us-gaap_StatementBusinessSegmentsAxis": ["msft_IntelligentCloudMember"],
                                    "srt_StatementGeographicalAxis": ["country_US"],
                                    "us-gaap_DebtInstrumentAxis": ["msft_SeniorNotesMember"]}})
    found = linkbase.parse(xml)
    assert found[("business", "Intelligent Cloud")] == ["Note"] and found[("geographic", "US")] == ["Note"]
    assert not [key for key in found if key[1] == "Senior Notes"]


def test_a_file_that_is_not_xml_declares_nothing():
    assert linkbase.parse(b"<html><body>Access Denied") == {}


def test_the_linkbase_is_named_by_the_filings_index():
    listing = {"directory": {"item": [{"name": "amzn-20251231.htm"}, {"name": "amzn-20251231_def.xml"},
                                      {"name": "amzn-20251231_pre.xml"}]}}
    assert linkbase.name(listing) == "amzn-20251231_def.xml"
    assert linkbase.name({"directory": {"item": [{"name": "amzn-20251231.htm"}]}}) is None
    assert linkbase.name({}) is None


def test_a_filing_with_no_def_xml_names_its_schema_file_and_the_def_xml_wins_when_both_are_listed():
    """#1066: Microsoft's FY2026 10-K lists no ``_def.xml``; its ``.xsd`` embeds the linkbases."""
    items = [{"name": "msft-20260630.htm", "size": "8585501"}, {"name": "msft-20260630.xsd", "size": "2170276"},
             {"name": "msft-20260630_htm.xml", "size": "10948157"}]
    assert linkbase.name({"directory": {"item": items}}) == "msft-20260630.xsd"
    both = items + [{"name": "msft-20260630_def.xml", "size": "9000"}]
    assert linkbase.name({"directory": {"item": both}}) == "msft-20260630_def.xml"
    two = [{"name": "other.xsd", "size": ""}, {"name": "small.xsd", "size": "900"}, {"name": "tm-20260331.xsd",
                                                                                     "size": "50000"}]
    assert linkbase.name({"directory": {"item": two}}) == "tm-20260331.xsd"      # the largest listed


# ── The fetch ─────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sec(monkeypatch, http_mock):
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec_edgar, "SEC_DATA_BASE", "https://data.sec.test")
    fx.spine()
    fx.filing_routes(http_mock, {"789019": fx.submissions(789019, fx.MSFT_FILINGS, "MICROSOFT CORP")},
                     {"msft-10k.htm": fx.ixbrl_10k(), "msft-def14a.htm": fx.proxy()})
    return http_mock


def _issues() -> list[dict]:
    return [i for i in ops.open_issues(filings.NAME, limit=100)[1] if fx.K25 in str(i.get("key"))]


def test_the_annual_reports_linkbase_is_fetched_once_and_stored_beside_the_document(sec):
    fx.linkbase_routes(sec)
    check = fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert check["result"] == "changed", check["note"]
    stored = filings.stored_linkbase("789019", fx.K25)
    assert stored is not None and base.read_raw(stored).decode("utf-8") == fx.MSFT_DEF
    assert stored.parent == filings._doc_path("789019", fx.K25).parent
    assert "1 definition linkbases fetched, 0 annual reports without one" in check["note"]
    index, = sec.calls("index.json")                                     # the annual report's; the proxy has none
    assert f"/789019/{fx.K25.replace('-', '')}/index.json" in str(index.url)
    assert f"/789019/{fx.K25.replace('-', '')}/{fx.MSFT_DEF_NAME}" in str(sec.calls(fx.MSFT_DEF_NAME)[0].url)
    fx.run(filings.NAME, mode="backfill", to="2026-10-29")
    assert len(sec.calls("index.json")) == 1 and len(sec.calls(fx.MSFT_DEF_NAME)) == 1   # resumable
    assert sec.calls(fx.MSFT_XSD_NAME) == [], "the schema file is not asked for when a _def.xml is listed"


def test_a_filing_that_lists_no_linkbase_is_counted_not_an_issue_and_not_asked_again(sec):
    fx.linkbase_routes(sec, xml=None)
    check = fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert check["result"] == "changed", check["note"]
    assert "0 definition linkbases fetched, 1 annual reports without one" in check["note"]
    assert filings.stored_linkbase("789019", fx.K25) is None and _issues() == []
    assert fx.q("SELECT count(*), count(report_tables) FROM segment_revenue") == [(4, 0)]
    fx.run(filings.NAME, mode="backfill", to="2026-10-29")
    assert len(sec.calls("index.json")) == 1, "the stored index already says there is none"


def test_a_linkbase_the_archive_lists_but_does_not_hold_is_counted_too(sec):
    sec.add("index.json", {"directory": {"item": [{"name": fx.MSFT_DEF_NAME, "size": "9000"}]}})
    sec.add(f"/{fx.MSFT_DEF_NAME}", MISSING_OBJECT, status=403, headers=MISSING_HEADERS)
    check = fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert check["result"] == "changed", check["note"]
    assert "0 definition linkbases fetched, 1 annual reports without one" in check["note"]
    assert filings.stored_linkbase("789019", fx.K25) is None and _issues() == []


def test_a_linkbase_the_sec_fails_to_serve_does_not_stop_the_run_and_is_fetched_by_the_next(sec):
    sec.add(f"/{fx.MSFT_DEF_NAME}", b"busy", status=500)
    fx.linkbase_routes(sec)                                              # its linkbase route stands behind the 500
    check = fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert check["result"] == "changed", check["note"]                   # the linkbase is optional: the run goes on
    assert "0 definition linkbases fetched, 0 annual reports without one, 1 not served (asked again)" in check["note"]
    assert len(sec.calls(fx.MSFT_DEF_NAME)) == base.HTTP_ATTEMPTS
    assert filings.stored_linkbase("789019", fx.K25) is None and _issues() == []
    assert filings._doc_path("789019", fx.K25).exists(), "the document fetched before it is kept"
    assert fx.q("SELECT count(*), count(report_tables) FROM segment_revenue") == [(4, 0)]
    sec.routes = [r for r in sec.routes if r[2] != 500]
    check = fx.run(filings.NAME, mode="backfill", to="2026-10-29")
    assert "1 definition linkbases fetched" in check["note"], check["note"]
    assert filings.stored_linkbase("789019", fx.K25) is not None and len(sec.calls("msft-10k.htm")) == 1
    # the linkbase alone, arriving after the document, still reaches the served rows
    assert fx.q("SELECT count(report_tables) FROM segment_revenue")[0][0] > 0


def test_an_error_page_sent_as_the_linkbase_is_not_stored_and_is_asked_again(sec):
    sec.add(f"/{fx.MSFT_DEF_NAME}", b"<html><body>Undeclared Automated Tool</body></html>", status=200)
    fx.linkbase_routes(sec)                                              # the real linkbase stands behind the page
    check = fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert check["result"] == "changed", check["note"]
    assert "1 not served (asked again)" in check["note"]
    assert filings.stored_linkbase("789019", fx.K25) is None, "a page is not kept as the linkbase"
    sec.routes = [r for r in sec.routes if not (isinstance(r[1], bytes) and b"Undeclared" in r[1])]   # the page is gone
    fx.run(filings.NAME, mode="backfill", to="2026-10-29")
    assert filings.stored_linkbase("789019", fx.K25) is not None
    assert fx.q("SELECT count(report_tables) FROM segment_revenue")[0][0] > 0


# ── The linkbase embedded in the schema file (#1066) ─────────────────────────────────────────────────────────

def test_a_linkbase_embedded_in_the_schema_file_is_fetched_once_stored_and_names_the_rows_tables(sec):
    fx.linkbase_routes(sec, xml=None, xsd=fx.schema(fx.MSFT_DEF))
    check = fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert check["result"] == "changed", check["note"]
    assert "1 definition linkbases fetched, 0 annual reports without one" in check["note"]
    stored = filings.stored_linkbase("789019", fx.K25)
    assert stored is not None and stored.name.startswith(f"{fx.K25}.{fx.MSFT_XSD_NAME}")
    assert base.read_raw(stored).decode("utf-8") == fx.schema(fx.MSFT_DEF)
    assert f"/789019/{fx.K25.replace('-', '')}/{fx.MSFT_XSD_NAME}" in str(sec.calls(fx.MSFT_XSD_NAME)[0].url)
    assert fx.q("SELECT axis, segment, report_tables FROM segment_revenue ORDER BY axis, segment") == [
        ("business", "Intelligent Cloud", ["SegmentDetails"]),
        ("business", "More Personal Computing", ["SegmentDetails"]),
        ("geographic", "US", ["GeographicDetails", "SegmentDetails"]),
        ("product", "Xbox Content And Services", None)]
    fx.run(filings.NAME, mode="backfill", to="2026-10-29")
    assert len(sec.calls("index.json")) == 1 and len(sec.calls(fx.MSFT_XSD_NAME)) == 1   # resumable


def test_a_schema_file_with_no_linkbase_is_stored_counted_as_without_one_and_not_asked_again(sec):
    fx.linkbase_routes(sec, xml=None, xsd=fx.schema())
    check = fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert check["result"] == "changed", check["note"]
    assert "0 definition linkbases fetched, 1 annual reports without one" in check["note"]
    assert "not served" not in check["note"] and _issues() == []
    stored = filings.stored_linkbase("789019", fx.K25)
    assert stored is not None and base.read_raw(stored).decode("utf-8") == fx.schema(), "kept, so it is read once"
    assert fx.q("SELECT count(*), count(report_tables) FROM segment_revenue") == [(4, 0)]
    fx.run(filings.NAME, mode="backfill", to="2026-10-29")
    assert len(sec.calls(fx.MSFT_XSD_NAME)) == 1, "the stored schema is not downloaded again"
    assert fx.q("SELECT count(*), count(report_tables) FROM segment_revenue") == [(4, 0)]


def test_an_error_page_sent_as_the_schema_file_is_not_stored_and_is_asked_again(sec):
    sec.add(f"/{fx.MSFT_XSD_NAME}", b"<html><body>Undeclared Automated Tool</body></html>", status=200)
    fx.linkbase_routes(sec, xml=None, xsd=fx.schema(fx.MSFT_DEF))        # the real schema stands behind the page
    check = fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert check["result"] == "changed", check["note"]
    assert "0 definition linkbases fetched, 0 annual reports without one, 1 not served (asked again)" in check["note"]
    assert filings.stored_linkbase("789019", fx.K25) is None, "a page is not kept as the schema file"
    assert fx.q("SELECT count(*), count(report_tables) FROM segment_revenue") == [(4, 0)]
    sec.routes = [r for r in sec.routes if not (isinstance(r[1], bytes) and b"Undeclared" in r[1])]   # the page is gone
    fx.run(filings.NAME, mode="backfill", to="2026-10-29")
    assert len(sec.calls(fx.MSFT_XSD_NAME)) == 2
    assert filings.stored_linkbase("789019", fx.K25) is not None
    assert fx.q("SELECT count(report_tables) FROM segment_revenue")[0][0] > 0


# ── The column ────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_segment_row_names_its_tables_and_every_other_column_is_built_as_before(sec):
    old = ", ".join(c for c, _ in tables.SEGMENT_REVENUE if c != "report_tables")
    fx.run(filings.NAME, mode="backfill", to="2026-10-27")               # no index.json yet: no linkbase
    before = fx.q(f"SELECT {old} FROM segment_revenue ORDER BY axis, member")
    assert len(before) == 4
    assert fx.q("SELECT count(report_tables) FROM segment_revenue") == [(0,)]
    fx.linkbase_routes(sec)
    fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    assert fx.q(f"SELECT {old} FROM segment_revenue ORDER BY axis, member") == before
    assert fx.q("SELECT axis, segment, report_tables FROM segment_revenue ORDER BY axis, segment") == [
        ("business", "Intelligent Cloud", ["SegmentDetails"]),
        ("business", "More Personal Computing", ["SegmentDetails"]),
        ("geographic", "US", ["GeographicDetails", "SegmentDetails"]),
        ("product", "Xbox Content And Services", None)]                   # tagged, but no table declares it
    assert [(r["segment"], r["report_tables"]) for r in read.segments("789019", axis="business")] == [
        ("Intelligent Cloud", ["SegmentDetails"]), ("More Personal Computing", ["SegmentDetails"])]


# ── The line rule ─────────────────────────────────────────────────────────────────────────────────────────────

# Amazon's product axis in the shape ``segment_revenue`` holds it: the income statement's two parents and the segment
# note's seven lines, one flat list. The values are chosen for the tests (each set sums to the total), not Amazon's.
AMZN_TOTAL = 716_924.0
AMZN_PARENTS = {"Product": 296_000.0, "Service": 420_924.0}
AMZN_SEVEN = {"Online Stores": 269_000.0, "Third Party Seller Services": 172_000.0, "Amazon Web Services": 128_725.0,
              "Advertising": 68_600.0, "Subscription Services": 49_600.0, "Physical Stores": 22_700.0,
              "Other Services": 6_299.0}


def _amzn_rows(fixture_text, **changed) -> list[dict]:
    declared = linkbase.parse(fixture_text("amzn_def.xml"))
    values = {**AMZN_PARENTS, **AMZN_SEVEN, **changed}
    return [{"axis": "product", "segment": name, "value": value, "report_tables": declared[("product", name)]}
            for name, value in values.items()]


def test_the_seven_lines_and_the_two_parents_are_each_a_set_the_most_members_first(fixture_text):
    rows = _amzn_rows(fixture_text)
    assert sum(r["value"] for r in rows) == pytest.approx(2 * AMZN_TOTAL), "the flat list is twice the revenue"
    seven, two = read.segment_sets(rows, AMZN_TOTAL)
    assert (seven["table"], seven["axis"]) == (AMZN_LINES, "product")
    assert seven["members"] == list(AMZN_SEVEN)                          # by value, the biggest first
    assert seven["shares"] == pytest.approx([v / AMZN_TOTAL for v in AMZN_SEVEN.values()])
    assert sum(seven["shares"]) == pytest.approx(1.0)
    assert (two["table"], two["members"]) == (AMZN_STATEMENT, ["Service", "Product"])


def test_a_set_outside_two_percent_is_not_returned(fixture_text):
    rows = _amzn_rows(fixture_text, **{"Online Stores": 269_000.0 - 0.03 * AMZN_TOTAL})
    assert [s["table"] for s in read.segment_sets(rows, AMZN_TOTAL)] == [AMZN_STATEMENT]
    inside = _amzn_rows(fixture_text, **{"Online Stores": 269_000.0 - 0.015 * AMZN_TOTAL})
    assert [s["table"] for s in read.segment_sets(inside, AMZN_TOTAL)] == [AMZN_LINES, AMZN_STATEMENT]


def test_rows_no_table_declares_and_a_missing_total_give_no_set(fixture_text):
    flat = [{**r, "report_tables": None} for r in _amzn_rows(fixture_text)]
    assert read.segment_sets(flat, AMZN_TOTAL) == []                     # Compustat's rows, or no linkbase stored
    assert read.segment_sets(_amzn_rows(fixture_text), None) == []
    assert read.segment_sets(_amzn_rows(fixture_text), 0) == []
