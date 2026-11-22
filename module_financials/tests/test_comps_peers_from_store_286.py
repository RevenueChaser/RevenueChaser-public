"""#286: the comps peer side comes from the store, with EBITDA and enterprise value derived.

avo's decision, 20 Nov 2026: "Store'dan türet". Until then ``comps_engine._default_fetch`` spent one live Yahoo
``.info`` request **per peer** and read ``enterpriseValue`` and ``ebitda`` straight off the payload. The
fundamentals store carries neither, so both are built from the newest stored annual record:

* EBITDA = ``ebit + depreciation``
* enterprise value = ``market cap + total debt − cash``

which are not the numbers Yahoo returned, so the multiples, the percentiles and the implied values all move. That
is the point of the issue, and these tests pin the arithmetic, the markers and the label rather than any
particular company's figures.

Offline: ``peer_multiples``' two store readers are injected, so nothing opens a DuckDB file or sends a request.
"""
from __future__ import annotations

import pytest

from revenuechaser.module_financials import store_reads
from revenuechaser.module_financials.engines import comps_engine


def _record(**over) -> dict:
    """One annual record in the fundamentals layer's shape."""
    return {"fiscal_year": "2025", "ebit": 200.0, "depreciation": 50.0, "revenue": 1_000.0,
            "net_income": 120.0, "total_debt": 400.0, "cash": 100.0, **over}


@pytest.fixture
def store(monkeypatch):
    """Inject both readers of ``peer_multiples``; returns the dicts the test fills."""
    records: dict[str, list[dict]] = {}
    market: dict[str, dict] = {}
    monkeypatch.setattr(store_reads, "_records", lambda tickers: {t: records[t] for t in tickers if t in records})
    monkeypatch.setattr(store_reads, "_market", lambda tickers: {t: market[t] for t in tickers if t in market})
    return records, market


# --- the derivation ----------------------------------------------------------------------------------------

def test_ebitda_is_ebit_plus_depreciation(store):
    records, market = store
    records["AAA"] = [_record()]
    market["AAA"] = {"issuer_market_cap": 5_000.0, "cap_session": "2026-11-19"}
    got = store_reads.peer_multiples(["AAA"])["AAA"]
    assert got["ebitda"] == 250.0, "200 EBIT + 50 D&A"


def test_enterprise_value_is_market_cap_plus_debt_minus_cash(store):
    records, market = store
    records["AAA"] = [_record()]
    market["AAA"] = {"issuer_market_cap": 5_000.0, "cap_session": "2026-11-19"}
    got = store_reads.peer_multiples(["AAA"])["AAA"]
    assert got["enterpriseValue"] == 5_300.0, "5000 cap + 400 debt - 100 cash"


def test_the_issuer_cap_is_preferred_and_the_class_cap_is_the_fallback(store):
    records, market = store
    records["AAA"] = [_record()]
    market["AAA"] = {"issuer_market_cap": 5_000.0, "market_cap": 3_000.0, "cap_session": "2026-11-19"}
    assert store_reads.peer_multiples(["AAA"])["AAA"]["marketCap"] == 5_000.0
    market["AAA"] = {"issuer_market_cap": None, "market_cap": 3_000.0, "cap_session": "2026-11-19"}
    assert store_reads.peer_multiples(["AAA"])["AAA"]["marketCap"] == 3_000.0


@pytest.mark.parametrize("missing", ["ebit", "depreciation"])
def test_half_an_ebitda_is_no_ebitda(store, missing):
    records, market = store
    records["AAA"] = [_record(**{missing: None})]
    market["AAA"] = {"issuer_market_cap": 5_000.0}
    assert store_reads.peer_multiples(["AAA"])["AAA"]["ebitda"] is None


@pytest.mark.parametrize("missing", ["total_debt", "cash"])
def test_a_missing_balance_line_is_no_enterprise_value(store, missing):
    records, market = store
    records["AAA"] = [_record(**{missing: None})]
    market["AAA"] = {"issuer_market_cap": 5_000.0}
    assert store_reads.peer_multiples(["AAA"])["AAA"]["enterpriseValue"] is None


def test_no_market_cap_is_no_enterprise_value_but_the_peer_is_still_stored(store):
    records, _market = store
    records["AAA"] = [_record()]
    got = store_reads.peer_multiples(["AAA"])["AAA"]
    assert got["stored"] is True and got["marketCap"] is None and got["enterpriseValue"] is None
    assert got["ebitda"] == 250.0, "the income statement does not need a price"


def test_the_newest_record_is_the_one_read(store):
    records, market = store
    records["AAA"] = [_record(fiscal_year="2024", ebit=10.0, depreciation=1.0), _record()]
    market["AAA"] = {"issuer_market_cap": 5_000.0}
    got = store_reads.peer_multiples(["AAA"])["AAA"]
    assert (got["fiscal_year"], got["ebitda"]) == ("2025", 250.0)


def test_revenue_is_read_by_name_so_a_bank_top_line_is_not_revenue(store):
    """#450's rule, unchanged on the peer side: a bank carrying only its own top line gets no EV/Revenue."""
    records, market = store
    records["BNK"] = [_record(revenue=None, revenue_net_of_interest_expense=900.0)]
    market["BNK"] = {"issuer_market_cap": 5_000.0}
    assert store_reads.peer_multiples(["BNK"])["BNK"]["totalRevenue"] is None


def test_no_trailing_pe_is_claimed(store):
    """The store has none; the engine's cap-over-net-income fallback is the P/E, and it must be free to run."""
    records, market = store
    records["AAA"] = [_record()]
    market["AAA"] = {"issuer_market_cap": 5_000.0}
    assert store_reads.peer_multiples(["AAA"])["AAA"]["trailingPE"] is None


# --- the "not stored" marker -------------------------------------------------------------------------------

def test_a_peer_with_no_company_is_marked_not_stored(store):
    got = store_reads.peer_multiples(["ZZZ"])["ZZZ"]
    assert got["stored"] is False
    assert all(got[f] is None for f in store_reads.FIELDS), "a marker carries no half-figures"


def test_a_company_with_no_annual_record_is_marked_not_stored(store):
    records, _market = store
    records["AAA"] = []
    assert store_reads.peer_multiples(["AAA"])["AAA"]["stored"] is False


def test_a_record_without_a_fiscal_year_does_not_count_as_stored(store):
    records, _market = store
    records["AAA"] = [_record(fiscal_year=None)]
    assert store_reads.peer_multiples(["AAA"])["AAA"]["stored"] is False


def test_an_unstored_peer_reaches_the_card_marked_and_enters_no_percentile(financials):
    res = comps_engine.run_comps(
        financials, ["AAA", "ZZZ"],
        fetch_many=lambda peers: {
            "AAA": {"stored": True, "fiscal_year": "2025", "enterpriseValue": 1_000.0, "ebitda": 100.0,
                    "totalRevenue": 500.0, "marketCap": 800.0, "netIncomeToCommon": 40.0, "trailingPE": None},
            "ZZZ": {"stored": False, **{f: None for f in store_reads.FIELDS}},
        })
    by_ticker = {r["ticker"]: r for r in res["peers"]}
    assert by_ticker["ZZZ"]["stored"] is False and by_ticker["AAA"]["stored"] is True
    assert res["multiples"]["ev_ebitda"]["count"] == 1, "only the stored peer is in the percentile"
    assert by_ticker["AAA"]["ev_ebitda"] == 10.0


def test_the_card_says_a_peer_is_not_stored(financials):
    from revenuechaser.module_financials.reporting.html_builder import build_report_html
    res = comps_engine.run_comps(
        financials, ["ZZZ"],
        fetch_many=lambda peers: {"ZZZ": {"stored": False, **{f: None for f in store_reads.FIELDS}}})
    html = build_report_html({"ticker": "TEST", "financials": financials, "modules": {"comps": res},
                              "warnings": res["warnings"]})
    assert "not stored" in html, "a blank row reads as missing figures; this one has never been stored"


def test_a_peer_the_reader_left_out_entirely_is_not_assumed_stored(financials):
    """A reader that answers for fewer peers than it was asked about must not produce a blank-but-stored row."""
    res = comps_engine.run_comps(financials, ["AAA"], fetch_many=lambda peers: {})
    assert res["peers"][0]["stored"] is False


# --- no provider call --------------------------------------------------------------------------------------

def test_the_peer_read_makes_no_provider_call(financials, monkeypatch):
    """The whole point of the issue: a comps run must not touch Yahoo."""
    import yfinance

    def boom(*a, **k):
        raise AssertionError("the comps peer read called a provider")

    monkeypatch.setattr(yfinance, "Ticker", boom)
    monkeypatch.setattr(store_reads, "_records", lambda tickers: {t: [_record()] for t in tickers})
    monkeypatch.setattr(store_reads, "_market", lambda tickers: {t: {"issuer_market_cap": 5_000.0}
                                                                 for t in tickers})
    res = comps_engine.run_comps(financials, ["AAA"])
    assert res["peers"][0]["ev_ebitda"] == 5_300.0 / 250.0


def test_a_fundamentals_layer_error_is_nothing_stored_not_an_exception(monkeypatch):
    """A serving file being swapped under a read must not fail the Fetch (the shape of #1182)."""
    from revenuechaser.core import fundamentals_layer

    def boom(*a, **k):
        raise RuntimeError("the serving file is being swapped")

    monkeypatch.setattr(fundamentals_layer, "records_many", boom)
    assert store_reads._records(["AAA"]) == {}


def test_a_prices_store_error_leaves_every_peer_without_an_enterprise_value(monkeypatch):
    from revenuechaser.core import spine_reads

    def boom(*a, **k):
        raise RuntimeError("the serving file is being swapped")

    monkeypatch.setattr(spine_reads, "latest_market", boom)
    assert store_reads._market(["AAA"]) == {}


def test_the_peer_caps_come_through_the_same_wrapper_as_the_targets(monkeypatch):
    """The two caps divide into each other, so they must be one read of one session, not two opens."""
    from revenuechaser.core import spine_reads

    asked: list[tuple] = []
    monkeypatch.setattr(spine_reads, "latest_market",
                        lambda tickers: (asked.append(tuple(tickers)), {})[1])
    store_reads._market(["AAA", "BBB"])
    assert asked == [("AAA", "BBB")], "one call for the whole peer list, through core/spine_reads"


def test_an_empty_peer_list_reads_nothing(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("an empty peer list must cost no read")

    monkeypatch.setattr(store_reads, "_records", boom)
    monkeypatch.setattr(store_reads, "_market", boom)
    assert store_reads.peer_multiples([]) == {}
    assert store_reads.peer_multiples(None) == {}
    assert store_reads.peer_multiples(["", "  "]) == {}
