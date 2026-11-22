"""``ownership/serve`` over the filings themselves: VALUE still reported in thousands after 2023 found from the 13F's
own prices, an exit that may not be a sale, a filer that starts, stops or is succeeded, each investor type's largest
names and dollar flow, and the ``short_interest`` bridge.

Each of these builds its own small world instead of the shared one (``ownership_serve_world.store``, 13-25 s a test),
which is why they are a file of their own (#1153).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from revenuechaser.core.providers import sec_edgar
from revenuechaser.rcdata import read, serving
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.ownership import finra, ibkr, sec, sec13f, serve

from . import ownership_fixture as ox
from . import prices_store
from .ownership_serve_world import (
    Q2, Q3, _book, _book_day, _f, _h, _issues, _serve, _served, _thirteen_f
)  # noqa: F401 (the shared world: its helpers and the fixtures a test asks for by name)


NOON_NY = datetime(2026, 10, 28, 16, 0, tzinfo=timezone.utc).timestamp()      # 12:00 New York, a session day


def _uw_ready(monkeypatch) -> None:
    from revenuechaser.core.providers import unusual_whales
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    monkeypatch.setenv("UNUSUAL_WHALES_API_KEY", "test-key")
    monkeypatch.setattr(unusual_whales, "BASE", "https://uw.test/api")
    monkeypatch.setattr(unusual_whales, "_sleep", lambda _s: None)


def _uw_institutions(http_mock, rows: list[dict]) -> None:
    """UW's ``/institutions`` answering ``rows`` on its first page, read once as of 12 Nov 2026."""
    from revenuechaser.rcdata.build.ownership import uw_institutions as uwi

    def answer(request):
        page = request.url.query.decode()
        return 200, json.dumps({"data": rows if "page=" not in page or "page=0" in page else []}), \
            {"content-type": "application/json"}
    http_mock.add("/institutions", answer)
    assert base.run_request({"dataset": uwi.NAME, "params": {"as_of": "2026-11-12"}},
                            sleep=lambda s: None)["result"] == "changed"


def _institution(cik: str, tags: list[str], predecessors: list[dict] = ()) -> dict:
    return {"cik": cik, "name": f"MANAGER {cik}", "tags": tags, "is_hedge_fund": False, "date": "2026-09-30",
            "filing_date": "2026-10-27", "total_value": "1", "share_value": "1",
            "succession": {"predecessors": list(predecessors), "current_holder": None, "succeeded_by": None}}


def _handover(monkeypatch, http_mock, effective: str, also: list[dict] = ()) -> dict:
    """#776 (AON, 2025 Q3 on the live board): HPS (4000002) is succeeded by BlackRock (4000001), which UW lists only
    in BlackRock's ``predecessors``. BlackRock's Q3 holds its own 100, HPS's 300 and 50 bought; 4000003 starts
    reporting and 4000004 really stops."""
    _uw_ready(monkeypatch)
    ox.make_spine()
    e = ox.Edgar()
    e.add_day("2026-08-14", [
        _f("0004000001-26-000001", 4000001, "2026-08-14", [_h("MICROSOFT CORP", "594918104", 40_000, 100)],
           period="06-30-2026"),
        _f("0004000002-26-000002", 4000002, "2026-08-14", [_h("MICROSOFT CORP", "594918104", 120_000, 300)],
           period="06-30-2026"),
        _f("0004000004-26-000004", 4000004, "2026-08-14", [_h("MICROSOFT CORP", "594918104", 80_000, 200)],
           period="06-30-2026")])
    e.add_day("2026-10-27", [
        _f("0004000001-26-000011", 4000001, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 180_000, 450)]),
        _f("0004000003-26-000013", 4000003, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 200_000, 500)])])
    e.install(http_mock)
    blackrock = _institution("0004000001", [], [{"cik": "0004000002", "name": "HPS INVESTMENT PARTNERS, LLC",
                                                 "effective_report_date": effective}])
    _uw_institutions(http_mock, [blackrock, *also])
    _thirteen_f(as_of="2026-10-28")
    _thirteen_f(mode="backfill", **{"from": "2026-08-14", "to": "2026-08-14"})
    return _serve(day="2026-11-20")                              # after the 30 Sep deadline (16 Nov): settled


def _split_book(monkeypatch, http_mock) -> None:
    """MSFT splits 2-for-1 on 3 Aug 2026. 4000001 (a value investor) held 100 before and 200 after: no trade.
    4000002 (untagged) held 100 before and 300 after, and bought 100 AAPL: a buy of 100 MSFT on the new basis."""
    _uw_ready(monkeypatch)
    ox.make_spine(sectors={"MSFT": "Technology"})
    prices_store.put_bars([{"ticker": "MSFT", "session_date": "2026-06-30", "close": 400.0},
                           {"ticker": "MSFT", "session_date": "2026-09-30", "close": 200.0}])
    prices_store.put_action("MSFT", "2026-08-03", "split", 2.0)
    e = ox.Edgar()
    e.add_day("2026-08-14", [
        _f("0004000001-26-000001", 4000001, "2026-08-14", [_h("MICROSOFT CORP", "594918104", 40_000, 100)],
           period="06-30-2026"),
        _f("0004000002-26-000002", 4000002, "2026-08-14", [_h("MICROSOFT CORP", "594918104", 40_000, 100)],
           period="06-30-2026")])
    e.add_day("2026-10-27", [
        _f("0004000001-26-000011", 4000001, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 40_000, 200)]),
        _f("0004000002-26-000012", 4000002, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 60_000, 300),
                                                         _h("APPLE INC", "037833100", 50_000, 100)])])
    e.install(http_mock)
    _uw_institutions(http_mock, [_institution("0004000001", ["value_investor"])])
    _thirteen_f(as_of="2026-10-28")
    _thirteen_f(mode="backfill", **{"from": "2026-08-14", "to": "2026-08-14"})
    _serve(day="2026-11-20")


def test_a_filers_value_off_by_1000_is_rescaled_once_its_prices_agree(monkeypatch, http_mock):
    """Real data, 2026-10-28: 332 of 8,848 filers of Q2 2026 still report thousands, one reports x1000 too high."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    filers = [_f(f"000200000{i}-26-00000{i}", 2000000 + i, "2026-10-27", _book()) for i in range(1, 5)]
    filers.append(_f("0002000005-26-000005", 2000005, "2026-10-27", _book(scale=0.001)))       # thousands
    filers.append(_f("0002000006-26-000006", 2000006, "2026-10-27", _book(scale=0.001, names=3)))  # too few names
    filers.append(_f("0002000007-26-000007", 2000007, "2026-10-27", _book(scale=1000)))        # x1000 too high
    e.add_day("2026-10-27", filers)
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")
    row = _serve()
    assert _served("SELECT cik, names, value_factor FROM sec13f_filer_period WHERE value_factor <> 1 ORDER BY cik") == [
        ("2000005", 6, 1000.0), ("2000007", 6, 0.001)]
    # The filer with too few names for the median test has its lines read at the consensus price instead (#780).
    assert _served("SELECT value FROM sec13f_ticker_period WHERE ticker = 'MSFT'") == [(40_000.0 * 7,)]
    assert "2 filer-quarters' VALUE off by a factor of 1,000 against the 13F's own prices: rescaled" in row["note"]
    # Review S2: the largest money change the store makes is on the issues board, one row per filer and quarter.
    issues = _issues()
    assert issues[("value_rescaled", "2000005|2026-09-30")] == (
        "MANAGER 2000005, 2026-09-30: VALUE read in thousands (median ratio 0.001 to the 13F's own prices over 6 "
        "names): $122 read as $122,300")
    assert issues[("value_rescaled", "2000007|2026-09-30")] == (
        "MANAGER 2000007, 2026-09-30: VALUE read as 1,000 times too high (median ratio 1000 to the 13F's own prices "
        "over 6 names): $122,300,000 read as $122,300")
    assert not any(k == "value_rescaled" and key.startswith("2000006") for k, key in issues)


def test_a_filer_writing_dollars_before_the_rule_change_is_read_in_dollars(monkeypatch, http_mock):
    """#780: before 2023-01-03 the rule said thousands (``value_scale`` 1,000), but some filers wrote dollars. The
    1,000 test ran only on filings made after the change, so their value went in 1,000 times too high and the
    pre-2023 quarters' totals with it (AAPL's implied price 6-41 times its close on the live store)."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    filers = [_f(f"000200000{i}-22-00000{i}", 2000000 + i, "2022-08-10", _book(scale=0.001), period="06-30-2022")
              for i in range(1, 5)]                                                            # thousands, as ruled
    filers.append(_f("0002000005-22-000005", 2000005, "2022-08-10", _book(), period="06-30-2022"))   # dollars
    e.add_day("2022-08-10", filers)
    e.install(http_mock)
    _thirteen_f(as_of="2022-08-11")
    _serve()
    assert _served("SELECT cik, period, value_factor FROM sec13f_filer_period WHERE value_factor <> 1") == [
        ("2000005", date(2022, 6, 30), 0.001)]
    assert _served("SELECT value FROM sec13f_ticker_period WHERE ticker = 'MSFT'") == [(40_000.0 * 5,)]


def test_a_filer_off_by_a_million_is_rescaled_too(monkeypatch, http_mock):
    """#780, live 12 Nov 2026: Palisades (2014 Q2) and SPX Equities (2018 Q2) sat at a median ratio of 1,000,000,
    outside the 1,000 band, and alone carried $56T and $147T."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    _book_day(http_mock, {"2026-10-27": [(1.0, "09-30-2026")] * 4 + [(1_000_000.0, "09-30-2026")]})
    row = _serve()
    assert _served("SELECT cik, value_factor FROM sec13f_filer_period WHERE value_factor <> 1") == [
        ("2000005", 0.000001)]
    assert _served("SELECT value FROM sec13f_ticker_period WHERE ticker = 'MSFT'") == [(40_000.0 * 5,)]
    assert _issues()[("value_rescaled", "2000005|2026-09-30")].startswith(
        "MANAGER 2000005, 2026-09-30: VALUE read as 1,000,000 times too high")
    assert "1 filer-quarters' VALUE off" in row["note"]


def test_a_quarters_consensus_price_1000_times_off_both_neighbours_is_moved_back(monkeypatch, http_mock):
    """#780, live 2022 Q3: most holders already wrote dollars while their filings were read in thousands, so the
    median price was 1,000 times too high and a filer writing thousands as ruled (Sanders Capital, $36B) was rescaled
    to $36T. The quarters beside it set the price right; then the dollar writers are the ones rescaled."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    thousands, dollars = 0.001, 1.0
    _book_day(http_mock, {
        "2022-08-10": [(thousands, "06-30-2022")] * 5,
        "2022-11-10": [(dollars, "09-30-2022")] * 3 + [(thousands, "09-30-2022")] * 2,
        "2023-02-10": [(dollars, "12-31-2022")] * 5})
    row = _serve()
    q3 = date(2022, 9, 30)
    assert _served("SELECT cik, value_factor FROM sec13f_filer_period WHERE period = ? ORDER BY cik", q3) == [
        ("2000006", 0.001), ("2000007", 0.001), ("2000008", 0.001), ("2000009", 1.0), ("2000010", 1.0)]
    assert _served("SELECT period, value FROM sec13f_ticker_period WHERE ticker = 'MSFT' ORDER BY period") == [
        (date(2022, 6, 30), 200_000.0), (q3, 200_000.0), (date(2022, 12, 31), 200_000.0)]
    assert "6 consensus prices 1,000 times off the quarters beside them: moved back" in row["note"]


def test_one_holding_far_from_its_price_in_a_clean_filer_is_read_at_that_price(monkeypatch, http_mock):
    """#780, live 2018 Q3: SPX Equities' median ratio was 1.02, but a few of its lines put $258T on the quarter."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    filers = [_f(f"000200000{i}-26-00000{i}", 2000000 + i, "2026-10-27", _book()) for i in range(1, 5)]
    odd = _book()
    odd[0] = _h("ISSUER 594918104", "594918104", 40_000 * 10_000.0, 100)              # MSFT line x10,000
    filers.append(_f("0002000005-26-000005", 2000005, "2026-10-27", odd))
    e.add_day("2026-10-27", filers)
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")
    row = _serve()
    assert _served("SELECT value_factor FROM sec13f_filer_period WHERE cik = '2000005'") == [(1.0,)]
    assert _served("SELECT value FROM sec13f_ticker_period WHERE ticker = 'MSFT'") == [(40_000.0 * 5,)]
    assert _issues()[("value_row_replaced", "2000005|2026-09-30|594918104")] == (
        "MANAGER 2000005, 2026-09-30, 594918104: $400,000,000 read at the 13F's own price, $40,000")
    assert "1 holdings 300 times or more from the 13F's own price: read at that price" in row["note"]


def test_a_quarter_whose_deadline_passed_before_the_first_13f_day_is_not_served(monkeypatch, http_mock):
    """Real data, 2026-10-28: 852 filings of 135 filers in the sets from 2025 report quarters back to 2001, filed
    late; only those late filers of such a quarter are stored, so its breadth and totals would mislead."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    e.add_day("2026-10-27", [_f("0002000001-26-000001", 2000001, "2026-10-27", _book()),
                             _f("0002000002-26-000002", 2000002, "2026-10-27", _book(), period="09-30-2001")])
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")       # the walk's first day is 2026-10-25, the first holdings report 2026-10-27
    row = _serve()
    assert _served("SELECT DISTINCT period FROM sec13f_ticker_period") == [(Q3,)]
    assert _served("SELECT period, filers FROM sec13f_periods") == [(Q3, 1)]
    assert _served(f"SELECT count(*) FROM {sec13f.TABLE} WHERE period = '2001-09-30'") == [(1,)]     # kept, raw
    assert ("1 filings of 1 quarters whose filing deadline passed before the first 13F day (2026-10-27) left out"
            in row["note"])


def test_a_new_holdings_report_without_the_a_suffix_adds_to_the_quarter(monkeypatch, http_mock):
    """Real data (01jun2025-31aug2025): one 13F-HR of 9,501 carries AMENDMENTTYPE NEW HOLDINGS without the /A. It
    adds to the filer's report for the quarter, as a 13F-HR/A of that type does; read as a new report it replaced
    the quarter with its few names and made every other position an exit."""
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    name = "01sep2026-30nov2026_form13f.zip"
    href = f"/files/structureddata/data/form-13f-data-sets/{name}"
    http_mock.add(ox.SETS_PAGE_PATH, ox.sets_page([href]))
    http_mock.add(href, ox.f13_set([
        ox.set_filing("0004000001-26-000001", 4000001, "14-OCT-2026", [
            _h("MICROSOFT CORP", "594918104", 400_000, 1000), _h("APPLE INC", "037833100", 23_000, 100)],
            period="30-SEP-2026"),
        ox.set_filing("0004000001-26-000002", 4000001, "20-OCT-2026", [_h("GAMESTOP CORP", "36467W109", 2_500, 100)],
                      period="30-SEP-2026", form="13F-HR", amendment_type="NEW HOLDINGS", amendment_no="1",
                      is_amendment="Y")]))
    ox.Edgar().install(http_mock)
    _thirteen_f(mode="backfill", **{"from": "2026-09-01", "to": "2026-10-27"})
    _serve()
    assert _served(f"SELECT form, is_amendment, amendment_type FROM {sec13f.TABLE} ORDER BY filed") == [
        ("13F-HR", False, None), ("13F-HR", False, "NEW HOLDINGS")]
    assert _served("SELECT ticker, shares, holders FROM sec13f_ticker_period WHERE period = ? ORDER BY ticker",
                   Q3) == [("AAPL", 100.0, 1), ("GME", 100.0, 1), ("MSFT", 1000.0, 1)]
    assert _served("SELECT filings, cusips FROM sec13f_filer_period") == [(2, 3)]


def test_a_period_that_is_not_a_quarter_end_is_read_as_its_calendar_quarter(monkeypatch, http_mock):
    """13F review B2 (2026-10-30): a filer that writes 09-29 or 10-01 for the September quarter (review S1: the
    nearest quarter end, not the quarter the day falls in) is one of that quarter's filers, not a quarter of its own (where it was the only filer, breadth 100 %, and its other quarters never
    paired with it: a new holder every quarter). The filing keeps the period as written."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    e.add_day("2026-08-14", [_f("0005000002-26-000001", 5000002, "2026-08-14",
                                [_h("MICROSOFT CORP", "594918104", 40_000, 100)], period="06-30-2026")])
    e.add_day("2026-10-27", [
        _f("0005000001-26-000011", 5000001, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 400_000, 1000)]),
        _f("0005000002-26-000012", 5000002, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 48_000, 120)],
           period="09-29-2026"),
        _f("0005000003-26-000013", 5000003, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 4_000, 10)],
           period="10-01-2026")])
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")
    _thirteen_f(mode="backfill", **{"from": "2026-08-14", "to": "2026-08-14"})
    _serve()
    assert _served(f"SELECT period FROM {sec13f.TABLE} WHERE accession = '0005000002-26-000012'") == [
        (date(2026, 9, 29),)]
    assert _served("SELECT period, filers FROM sec13f_periods ORDER BY period") == [(Q2, 1), (Q3, 3)]
    # #732: the two filers with no report in the June quarter started filing; they are not new holders.
    assert _served("SELECT period, shares, holders, new_holders, exited_holders, started_filers, breadth, filers "
                   "FROM sec13f_ticker_period WHERE ticker = 'MSFT' ORDER BY period") == [
        (Q2, 100.0, 1, None, None, None, 100.0, 1), (Q3, 1130.0, 3, 0, 0, 2, 100.0, 3)]
    assert _served("SELECT period, cusips FROM sec13f_filer_period WHERE cik = '5000002' ORDER BY period") == [
        (Q2, 1), (Q3, 1)]


def test_an_exit_whose_filer_omitted_holdings_in_confidence_or_did_not_file_is_counted_apart(monkeypatch, http_mock):
    """ownership_review.md: a position missing for confidential treatment must not read as sold."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    e.add_day("2026-08-14", [_f(f"000300000{i}-26-00000{i}", 3000000 + i, "2026-08-14",
                                [_h("MICROSOFT CORP", "594918104", 40_000, 100)], period="06-30-2026")
                             for i in range(1, 4)])
    e.add_day("2026-10-27", [
        _f("0003000001-26-000011", 3000001, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 40_000, 100)],
           confidential=False),
        # 3000002 asked for confidential treatment and left MSFT out; 3000003 has not filed the quarter.
        _f("0003000002-26-000012", 3000002, "2026-10-27", [_h("APPLE INC", "037833100", 23_000, 100)],
           confidential=True)])
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")
    _thirteen_f(mode="backfill", **{"from": "2026-08-14", "to": "2026-08-14"})
    _serve()
    assert _served(f"SELECT cik, period, confidential_omitted FROM {sec13f.TABLE} ORDER BY period, cik") == [
        ("3000001", Q2, None), ("3000002", Q2, None), ("3000003", Q2, None),
        ("3000001", Q3, False), ("3000002", Q3, True)]
    assert _served("SELECT cik, confidential_omitted FROM sec13f_filer_period WHERE period = ? ORDER BY cik",
                   Q3) == [("3000001", False), ("3000002", True)]
    # 3000003 stopped reporting: counted apart, not an exit and not a sale (#732); 3000002 reported and left MSFT
    # out in confidence: an exit, counted as one that may not be a sale.
    assert _served("SELECT holders, exited_holders, exited_confidential, exited_no_filing, sell_flow, stopped_shares "
                   "FROM sec13f_ticker_period WHERE ticker = 'MSFT' AND period = ?", Q3) == [(1, 1, 1, 1, 100.0, 100.0)]
    assert _served("SELECT exited_holders, exited_confidential, exited_no_filing FROM sec13f_ticker_period "
                   "WHERE ticker = 'MSFT' AND period = ?", Q2) == [(None, None, None)]


def test_a_filer_that_starts_or_stops_reporting_is_not_a_trade_and_is_listed(monkeypatch, http_mock):
    """#732 (owner, 12 Nov 2026): the flows and new/exited holders count only filers that reported both quarters. A
    first report is not a buy of the whole position and a missing report is not a sale; both are counted apart and
    listed per ticker and settled quarter in ``sec13f_filer_breaks``."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    e.add_day("2026-08-14", [
        _f("0004000001-26-000001", 4000001, "2026-08-14", [_h("MICROSOFT CORP", "594918104", 40_000, 100)],
           period="06-30-2026"),
        _f("0004000002-26-000002", 4000002, "2026-08-14", [_h("MICROSOFT CORP", "594918104", 120_000, 300)],
           period="06-30-2026")])
    e.add_day("2026-10-27", [
        # 4000001 bought 50; 4000003 files its first report; 4000002 has no report for the quarter.
        _f("0004000001-26-000011", 4000001, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 60_000, 150)]),
        _f("0004000003-26-000013", 4000003, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 200_000, 500)])])
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")
    _thirteen_f(mode="backfill", **{"from": "2026-08-14", "to": "2026-08-14"})
    _serve(day="2026-11-20")                                     # after the 30 Sep deadline (16 Nov): settled
    assert _served("SELECT holders, new_holders, exited_holders, buy_flow, sell_flow, started_filers, started_shares, "
                   "exited_no_filing, stopped_shares FROM sec13f_ticker_period WHERE ticker = 'MSFT' AND period = ?",
                   Q3) == [(2, 0, 0, 50.0, 0.0, 1, 500.0, 1, 300.0)]
    assert _served("SELECT ticker, period, cik, kind, shares FROM sec13f_filer_breaks ORDER BY kind") == [
        ("MSFT", Q3, "4000003", "started", 500.0), ("MSFT", Q3, "4000002", "stopped", 300.0)]
    assert [(r["cik"], r["kind"]) for r in read.filer_breaks_13f(["msft"])] == [("4000003", "started"),
                                                                               ("4000002", "stopped")]
    assert read.filer_breaks_13f(["msft"], periods=[Q2]) == []      # the quarter before Q2 is not in the store


def test_a_filer_succeeded_in_the_quarter_it_stops_is_its_successor_not_a_stop(monkeypatch, http_mock):
    row = _handover(monkeypatch, http_mock, "2026-09-30")
    # BlackRock 450 against its own 100 plus HPS's 300: 50 bought, not 350; only 4000004 stopped.
    assert _served("SELECT holders, new_holders, exited_holders, buy_flow, sell_flow, started_filers, started_shares, "
                   "exited_no_filing, stopped_shares FROM sec13f_ticker_period WHERE ticker = 'MSFT' AND period = ?",
                   Q3) == [(2, 0, 0, 50.0, 0.0, 1, 500.0, 1, 200.0)]
    assert _served("SELECT cik, kind, shares FROM sec13f_filer_breaks ORDER BY kind") == [
        ("4000003", "started", 500.0), ("4000004", "stopped", 200.0)]
    assert "1 filers succeeded by another" in row["note"]
    # The quarter before keeps both filers as they reported.
    assert _served("SELECT holders FROM sec13f_ticker_period WHERE ticker = 'MSFT' AND period = ?", Q2) == [(3,)]


def test_a_succession_dated_another_quarter_leaves_the_stop_a_stop(monkeypatch, http_mock):
    """A hand-over UW dates to a quarter the filings do not show is never merged silently (#776): HPS's is dated
    Q2, when both filers still reported, so HPS stays a stop; 4000004's, dated Q3 to 4000003, is taken."""
    other = _institution("0004000003", [], [{"cik": "0004000004", "name": "OLD ADVISERS LLC",
                                             "effective_report_date": "2026-09-30"}])
    row = _handover(monkeypatch, http_mock, "2026-06-30", also=[other])
    assert _served("SELECT cik, kind FROM sec13f_filer_breaks ORDER BY kind, cik") == [("4000002", "stopped")]
    assert "1 filers succeeded by another" in row["note"]


def test_each_investor_type_lists_its_largest_names_and_the_rest_per_quarter(monkeypatch, http_mock):
    """#760: a type is a tag UW gives the filer's CIK (padded to ten digits there, not in a 13F filing), plus ``all``.
    4000001 is a value and an energy investor, 4000002 a value investor, 4000003 untagged. With the top cut to one
    name, the rest is one row with no ticker and every type's quarter adds up to 100 %."""
    _uw_ready(monkeypatch)
    monkeypatch.setattr(serve, "TYPE_TOP", 1)
    ox.make_spine()
    e = ox.Edgar()
    e.add_day("2026-10-27", [
        _f("0004000001-26-000011", 4000001, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 400_000, 1000),
                                                         _h("APPLE INC", "037833100", 200_000, 1000)]),
        _f("0004000002-26-000012", 4000002, "2026-10-27", [_h("APPLE INC", "037833100", 600_000, 3000)]),
        _f("0004000003-26-000013", 4000003, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 4_000_000, 10_000)])])
    e.install(http_mock)
    _uw_institutions(http_mock, [_institution("0004000001", ["energy", "value_investor"]),
                                 _institution("0004000002", ["value_investor"]),
                                 _institution("0004000003", ["all"]),                # not a second "all"
                                 _institution("0004000009", ["activist"])])          # files no 13F here
    _thirteen_f(as_of="2026-10-28")
    _serve(day="2026-11-20")
    assert _served("SELECT tag, ticker, rank, value, holders, share, type_value, type_filers, snapshot_date "
                   "FROM sec13f_type_holdings WHERE period = ? ORDER BY tag, rank NULLS LAST", Q3) == [
        ("all", "MSFT", 1, 4_400_000.0, 2, 84.6154, 5_200_000.0, 3, date(2026, 11, 12)),
        ("all", None, None, 800_000.0, None, 15.3846, 5_200_000.0, 3, date(2026, 11, 12)),
        ("energy", "MSFT", 1, 400_000.0, 1, 66.6667, 600_000.0, 1, date(2026, 11, 12)),
        ("energy", None, None, 200_000.0, None, 33.3333, 600_000.0, 1, date(2026, 11, 12)),
        ("value_investor", "AAPL", 1, 800_000.0, 2, 66.6667, 1_200_000.0, 2, date(2026, 11, 12)),
        ("value_investor", None, None, 400_000.0, None, 33.3333, 1_200_000.0, 2, date(2026, 11, 12))]
    assert [(r["ticker"], r["share"]) for r in read.type_holdings_13f(["Value_Investor"], periods=[Q3])] == [
        ("AAPL", 66.6667), (None, 33.3333)]
    assert read.type_holdings_13f(["activist"]) == []


def test_a_split_between_two_quarters_is_not_a_buy(monkeypatch, http_mock):
    """#253 (owner's decision E, 16 Nov 2026): the quarter before is put on the quarter's share basis with the
    prices store's split factor before the buy or sell is taken. Before, 4000001's 100 -> 200 read as a buy of 100
    and the flow was 300; ``shares`` stays as filed."""
    _split_book(monkeypatch, http_mock)
    assert _served("SELECT period, shares, buy_flow, sell_flow FROM sec13f_ticker_period WHERE ticker = 'MSFT' "
                   "ORDER BY period") == [(Q2, 200.0, None, None), (Q3, 500.0, 100.0, 0.0)]


def test_each_investor_types_sector_split_and_dollar_flow_per_quarter(monkeypatch, http_mock):
    """#788 A2: the type's portfolio by the spine's sector (a ticker with none is Unclassified), and its dollars
    bought and sold: per filer and ticker the split-adjusted change at the quarter's 13F price (MSFT $200, AAPL
    $500), over the filers that reported both quarters. Q2 has no quarter before in the store: no flow row."""
    _split_book(monkeypatch, http_mock)
    assert _served("SELECT tag, sector, value, share, tickers, filers, snapshot_date FROM sec13f_type_sector "
                   "WHERE period = ? ORDER BY tag, value DESC", Q3) == [
        ("all", "Technology", 100_000.0, 66.6667, 1, 2, date(2026, 11, 12)),
        ("all", "Unclassified", 50_000.0, 33.3333, 1, 1, date(2026, 11, 12)),
        ("value_investor", "Technology", 40_000.0, 100.0, 1, 1, date(2026, 11, 12))]
    assert _served("SELECT tag, period, bought, sold, net, filers FROM sec13f_type_flow ORDER BY tag, period") == [
        ("all", Q3, 70_000.0, 0.0, 70_000.0, 2), ("value_investor", Q3, 0.0, 0.0, 0.0, 1)]
    assert [r["sector"] for r in read.type_sector_13f(["Value_Investor"], periods=[Q3])] == ["Technology"]
    assert [(r["tag"], r["net"]) for r in read.type_flow_13f()] == [("all", 70_000.0), ("value_investor", 0.0)]
    assert read.type_flow_13f(["activist"]) == [] and read.type_sector_13f(periods=[]) == []
    # #779: the UW tags shown beside a filer's own style, matched on the CIK without its leading zeros.
    assert read.institution_tags("4000001") == ["value_investor"] and read.institution_tags("4000002") == []


def test_a_quarter_still_arriving_lists_no_breaks(monkeypatch, http_mock):
    """Before its deadline every filer that has not filed yet would read as stopped: no rows until it settles."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    e.add_day("2026-08-14", [
        _f("0004000002-26-000002", 4000002, "2026-08-14", [_h("MICROSOFT CORP", "594918104", 120_000, 300)],
           period="06-30-2026")])
    e.add_day("2026-10-27", [
        _f("0004000001-26-000011", 4000001, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 60_000, 150)])])
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")
    _thirteen_f(mode="backfill", **{"from": "2026-08-14", "to": "2026-08-14"})
    _serve(day="2026-10-28")
    assert _served("SELECT count(*) FROM sec13f_filer_breaks") == [(0,)]


def test_short_interest_joins_the_newest_settled_short_interest_to_each_session(monkeypatch, http_mock):
    monkeypatch.setenv("RC_FINRA_API_BASE", "https://finra.test")
    day = "2026-10-15"
    ox.Finra({day: [ox.finra_row("MSFT", day, 50_000_000), ox.finra_row("BFA", day, 120_000),
                    ox.finra_row("BRK.B", day, 9_000_000, dtc=2.5)]}).install(http_mock)
    fake = ox.FakeFtp(ox.ibkr_file())
    fake.sessions = []
    monkeypatch.setattr(ibkr, "_ftp_factory", fake)
    monkeypatch.setattr(ibkr, "_now", lambda: NOON_NY)
    monkeypatch.setenv("RC_IBKR_SHORT_FTP_HOST", "ftp.ibkr.test")
    ox.make_spine()
    base.run_request({"dataset": finra.NAME, "params": {"as_of": "2026-10-28"}})
    base.run_request({"dataset": ibkr.NAME, "params": {"as_of": "2026-10-28"}}, sleep=lambda s: None)
    with serving.open_read("ownership") as con:
        cols = [r[0] for r in con.execute("DESCRIBE short_interest").fetchall()]
        rows = con.execute("SELECT ticker, session_date, market_date, short_interest, days_to_cover, fee_rate, "
                           "rebate_rate, short_shares_available FROM short_interest "
                           "ORDER BY ticker, session_date").fetchall()
    assert cols == ["ticker", "session_date", "market_date", "short_interest", "si_float", "total_float",
                    "days_to_cover", "fee_rate", "rebate_rate", "short_shares_available", "payload", "source",
                    "fetched_at", "run_id", "run_at"]
    # #252: 15 Oct's numbers are published on the seventh business day after it (26 Oct), after the close, so the
    # first session that sees them is 27 Oct, not 15 Oct.
    oct15, oct27, oct28 = date(2026, 10, 15), date(2026, 10, 27), date(2026, 10, 28)
    assert rows == [
        ("AAPL", oct28, None, None, None, 0.25, 3.3383, 10_000_000.0),
        ("BF-A", oct27, oct15, 120_000.0, 1.5, None, None, None),
        ("BRK-B", oct27, oct15, 9_000_000.0, 2.5, None, None, None),
        ("BRK-B", oct28, oct15, 9_000_000.0, 2.5, 0.25, 3.1, 3_500_000.0),
        ("GME", oct28, None, None, None, 16.0, -12.5, 150_000.0),
        ("MSFT", oct27, oct15, 50_000_000.0, 1.5, None, None, None)]
    finra_rows = read.finra_short_interest(["brk-b", "MSFT"])
    assert [(r["ticker"], r["settlement_date"], r["current_short"]) for r in finra_rows] == [
        ("BRK-B", oct15, 9_000_000), ("MSFT", oct15, 50_000_000)]
    assert read.finra_short_interest(["MSFT"], end=date(2026, 10, 14)) == []
    assert [(r["ticker"], r["available"]) for r in read.shortable(["GME", "AAPL"])] == [("AAPL", 10_000_000),
                                                                                        ("GME", 150_000)]
    assert {r["session_date"] for r in read.shortable()} == {oct28}
    assert read.shortable(session=date(2026, 10, 27)) == []


def test_no_spine_names_nothing_and_is_one_issue():
    base.parquet_root().mkdir(parents=True, exist_ok=True)
    row = _serve()
    assert row["result"] == "unchanged" and row["rows"] == 0
    assert ("spine_missing", "spine") in _issues()
    with serving.open_read("ownership") as con:
        assert con.execute("SELECT count(*) FROM sec13f_totals").fetchone() == (0,)


def test_nothing_built_yet_is_no_rows_from_any_ownership_reader():
    assert read.holders_13f() == [] and read.periods_13f() == [] and read.finra_short_interest(["MSFT"]) == []
    assert read.shortable() == [] and read.threshold_list() == [] and read.fails_to_deliver(["MSFT"]) == []
    assert read.insider_transactions(["MSFT"]) == [] and read.beneficial_ownership(["MSFT"]) == []


def test_a_filer_ten_times_too_high_is_rescaled_down_and_one_ten_times_too_low_is_not(monkeypatch, http_mock):
    """#934, live v4: ALPS 2015 Q3 and Thornburg 2025 Q1 sat at a median ratio of exactly 10, outside the 1,000 band.
    Only down: a ratio of 1/10 can be share counts ten times too high, which a larger VALUE would make worse."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    _book_day(http_mock, {"2026-10-27": [(1.0, "09-30-2026")] * 4 + [(10.0, "09-30-2026"), (0.1, "09-30-2026")]})
    _serve()
    assert _served("SELECT cik, value_factor FROM sec13f_filer_period WHERE value_factor <> 1") == [("2000005", 0.1)]
    issues = _issues()
    assert issues[("value_rescaled", "2000005|2026-09-30")].startswith(
        "MANAGER 2000005, 2026-09-30: VALUE read as 10 times too high")
    # Q14 (avo, 16 Nov 2026): the one left as filed is listed, not changed.
    assert issues[("value_suspect", "2000006|2026-09-30")].startswith(
        "MANAGER 2000006, 2026-09-30: VALUE per share at 0.1 times the 13F's own prices over 6 names, left as filed")
    assert not any(k == "value_suspect" and key.startswith("2000005") for k, key in issues)


def test_a_holding_whose_share_count_is_wrong_is_not_read_above_its_filings_cover_total(monkeypatch, http_mock):
    """#932, live v4: one MassMutual line of 2017 Q3 carried 836 trillion shares at a filed $15.8B; read at the 13F's
    own price it became $15,848T, the whole quarter's total. The filing's own cover total caps the replacement."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    filers = [_f(f"000200000{i}-26-00000{i}", 2000000 + i, "2026-10-27", _book()) for i in range(1, 5)]
    odd = _book()
    odd[0] = _h("ISSUER 594918104", "594918104", 40_000, 100 * 1_000_000_000)          # MSFT shares x1e9
    filers.append(_f("0002000005-26-000005", 2000005, "2026-10-27", odd))
    e.add_day("2026-10-27", filers)
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")
    _serve()
    assert _served("SELECT value FROM sec13f_ticker_period WHERE ticker = 'MSFT'") == [(40_000.0 * 5,)]
    assert not any(k == "value_row_replaced" for k, _ in _issues())


def test_a_quarter_whose_deadline_fell_before_the_first_holdings_report_is_not_served(monkeypatch, http_mock):
    """#935, live v4: the data-set fill moved the walk's first day to 2013-04-01, but the first holdings report is of
    2013-05-20, so 2013 Q1 (deadline 2013-05-15) was served with 232 filers against 3,425 the quarter after."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    e.add_day("2026-10-27", [_f("0002000001-26-000001", 2000001, "2026-10-27", _book()),
                             _f("0002000002-26-000002", 2000002, "2026-10-27", _book(), period="06-30-2026")])
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")
    monkeypatch.setattr(type(sec13f.DATASET), "first_day", lambda self: date(2026, 8, 1))    # before Q2's deadline
    _serve()
    assert _served("SELECT period, filers FROM sec13f_periods") == [(Q3, 1)]


def test_each_filers_style_over_the_settled_quarters(monkeypatch, http_mock):
    """#779 B2 (avo, 16 Nov 2026, Q12): every filer with 5 or more names in the newest settled quarter, its
    turnover (weights of value, so a split moves nothing), top-ten share and the share it held every quarter."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    e.add_day("2026-08-10", [_f("0002000001-26-000001", 2000001, "2026-08-10", _book(), period="06-30-2026"),
                             _f("0002000002-26-000002", 2000002, "2026-08-10", _book(names=5), period="06-30-2026")])
    e.add_day("2026-10-27", [_f("0002000001-26-000003", 2000001, "2026-10-27", _book()),
                             _f("0002000002-26-000004", 2000002, "2026-10-27", _book()),
                             _f("0002000003-26-000005", 2000003, "2026-10-27", _book(names=3))])     # too few
    e.install(http_mock)
    for day in ("2026-08-10", "2026-10-27"):
        _thirteen_f(mode="backfill", **{"from": day, "to": day})
    _serve("2026-11-20")                                           # both deadlines passed
    rows = {r[0]: r[1:] for r in _served("SELECT cik, period, quarters, names, turnover, top10_share, held_share "
                                         "FROM sec13f_filer_style ORDER BY cik")}
    assert set(rows) == {"2000001", "2000002"}
    assert rows["2000001"] == (Q3, 2, 6, 0.0, 1.0, 1.0)
    period, quarters, names, turnover, top10, held = rows["2000002"]
    assert (period, quarters, names, top10) == (Q3, 2, 6, 1.0)
    assert 0 < turnover < 1 and 0 < held < 1
    # #928's picker: a piece of the name or the CIK finds the filer, largest book first; nothing asked, nothing read.
    assert [r["cik"] for r in read.filer_style_13f(ciks=["0002000002"])] == ["2000002"]
    assert {r["cik"] for r in read.filer_style_13f("manager 200000")} == {"2000001", "2000002"}
    assert [r["cik"] for r in read.filer_style_13f("2000001")] == ["2000001"]
    assert read.filer_style_13f() == [] and read.filer_style_13f("   ") == [] and read.filer_style_13f(ciks=[]) == []


def test_a_filer_family_is_one_holder_for_the_top_10_and_hhi_but_not_for_the_holder_count(monkeypatch, http_mock):
    """#925 (avo, 16 Nov 2026, Q17 A, Q18 A): two filers of one family hold one name: HHI 10,000 (not 5,000), holders still 2."""
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    monkeypatch.setattr(serve, "family_roots", lambda edges, books, names=None: {"2000002": "2000001"})
    _book_day(http_mock, {"2026-10-27": [(1.0, "09-30-2026")] * 2})
    _serve()
    assert _served("SELECT holders, round(hhi, 6), round(top10_pct, 6) FROM sec13f_ticker_period "
                   "WHERE ticker = 'MSFT'") == [(2, 10000.0, 100.0)]      # HHI in points: 5,000 per filer


def test_two_sibling_filers_of_one_firm_are_one_holder_in_the_metrics_and_the_type_views(monkeypatch, http_mock):
    """#925 (avo, 21 Nov 2026): the live case. Two Vanguard filers, no included-manager link between them, each
    holding the same book: as one holder the name's HHI is 10,000 (not 5,000) and the type views count one filer.

    The ticker's own ``holders`` stays 2, per Q18 A, and a third filer of another firm is its own holder.
    """
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    e.add_day("2026-10-27", [
        _f("0002100119-26-000001", 2100119, "2026-10-27", _book(), name="VANGUARD CAPITAL MANAGEMENT LLC"),
        _f("0002100121-26-000002", 2100121, "2026-10-27", _book(), name="VANGUARD PORTFOLIO MANAGEMENT LLC")])
    e.install(http_mock)
    _thirteen_f(as_of="2026-10-28")
    _serve()
    assert _served("SELECT holders, round(hhi, 6), round(top10_pct, 6) FROM sec13f_ticker_period "
                   "WHERE ticker = 'MSFT'") == [(2, 10000.0, 100.0)]
    assert _served("SELECT holders, type_filers FROM sec13f_type_holdings WHERE ticker = 'MSFT'") == [(1, 1)]
    assert _served("SELECT DISTINCT filers FROM sec13f_type_sector") == [(1,)]


def test_a_family_needs_the_included_manager_link_and_the_same_firm_word():
    """Q17 A: the SEC's List of Other Included Managers, guarded by the firm word (a filer also lists sub-advisers).

    Every member of a family is returned, keyed on the family's largest filer by book (#925, 21 Nov 2026), so the
    holder the metrics count is the firm's own largest filer and not whichever small entity a filing named.
    """
    edges = [("11", "1", "VANGUARD ADVISERS INC", "VANGUARD GROUP INC"),
             ("12", "1", "WELLINGTON MANAGEMENT CO", "VANGUARD GROUP INC"),          # a sub-adviser: not a family
             ("13", "11", "Vanguard Fiduciary Trust", "VANGUARD ADVISERS INC"),     # two hops to the top
             ("1", "13", "VANGUARD GROUP INC", "Vanguard Fiduciary Trust"),         # would close a cycle
             ("21", "2", "The BlackRock Japan Co", "BlackRock, Inc."),              # "The" names no firm
             ("21", "3", "BLACKROCK SMALL LTD", "BLACKROCK ADVISORS")]              # the larger parent wins
    roots = serve.family_roots(edges, {"1": 9.0, "2": 8.0, "3": 1.0})
    assert roots == {"1": "1", "11": "1", "13": "1", "2": "2", "21": "2"}
    # The link points at a small entity (``11``, no book), but ``1`` holds the family's largest book: it is the root.
    assert serve.family_roots([("1", "11", "VANGUARD GROUP INC", "VANGUARD ADVISERS INC")],
                              {"1": 9.0}) == {"1": "1", "11": "1"}


def test_sibling_filers_of_a_curated_firm_are_one_family_with_no_included_manager_link():
    """#925 (avo, 21 Nov 2026): Vanguard's two 2026 CIKs name each other nowhere, so no edge joins them; the firm
    word does, and any family the included managers built around one of them joins the same family.

    A firm that is not curated keeps needing the link, and a curated firm with one filer is no family.
    """
    names = {"2100119": "VANGUARD CAPITAL MANAGEMENT LLC", "2100121": "VANGUARD PORTFOLIO MANAGEMENT LLC",
             "102909": "VANGUARD GROUP INC", "1767306": "Vanguard Personalized Indexing Management",
             "9": "WELLINGTON MANAGEMENT CO", "10": "WELLINGTON TRUST CO"}
    books = {"102909": 9.0, "2100119": 8.0, "1767306": 0.02}
    edges = [("1767306", "102909", "Vanguard Personalized Indexing Management", "VANGUARD GROUP INC")]
    assert serve.family_roots(edges, books, names) == {c: "102909" for c in
                                                      ("102909", "1767306", "2100119", "2100121")}
    assert "9" not in serve.family_roots([], books, names)                  # WELLINGTON is not a curated firm
    assert serve.family_roots([], books, {"2100119": "VANGUARD CAPITAL MANAGEMENT LLC"}) == {}
    assert "VANGUARD" in serve.FAMILY_FIRMS
