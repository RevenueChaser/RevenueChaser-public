"""``ownership/serve``'s 13F extras (#1447, #1449, #1450; ``build/ownership/sec13f_extras.py``): put/call exposure by
stock and filer with market makers apart, convertible par by issuer, "reported by X" for combination reports, and
late confidential reveals. Each over one small world of filings, never the long book's."""

from __future__ import annotations

from datetime import date

from revenuechaser.rcdata.build.ownership import sec, sec13f_extras

from . import ownership_fixture as ox
from .ownership_serve_world import _book, _f, _h, _serve, _served, _thirteen_f

MSFT = "594918104"


def _world(monkeypatch, http_mock, days: dict[str, list[tuple]]) -> None:
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    ox.make_spine()
    e = ox.Edgar()
    for day, rows in days.items():
        e.add_day(day, rows)
    e.install(http_mock)
    for day in days:
        _thirteen_f(mode="backfill", **{"from": day, "to": day})


def test_option_lines_are_exposure_by_stock_and_filer_with_market_makers_apart(monkeypatch, http_mock):
    """MSFT's consensus price is $400. A fund's put on 100 underlying shares is $40,000 of exposure; a market maker
    that wrote its call in contracts (10 lines' worth, $400,000: 100 times the price per "share") is read as 1,000
    underlying shares. Neither reaches the long book: MSFT keeps its four holders and their shares."""
    _world(monkeypatch, http_mock, {"2026-10-27": [
        _f("0002000001-26-000001", 2000001, "2026-10-27", _book() + [_h("MICROSOFT CORP", MSFT, 40_000, 100,
                                                                         put_call="Put")]),
        _f("0002000002-26-000002", 2000002, "2026-10-27", _book()),
        _f("0002000003-26-000003", 2000003, "2026-10-27", _book()),
        _f("0002000004-26-000004", 2000004, "2026-10-27", [_h("MICROSOFT CORP", MSFT, 40_000, 100),
                                                           _h("MICROSOFT CORP", MSFT, 400_000, 10, put_call="Call")],
           name="CTC LLC")]})
    _serve()
    assert _served("SELECT put_call, market_maker, filers, shares, value, contracts_read FROM sec13f_option_exposure "
                   "WHERE ticker = 'MSFT' ORDER BY put_call") == [("CALL", True, 1, 1000.0, 400_000.0, 1),
                                                                ("PUT", False, 1, 100.0, 40_000.0, 0)]
    assert _served("SELECT holders, shares FROM sec13f_ticker_period WHERE ticker = 'MSFT'") == [(4, 400.0)]
    assert _served("SELECT cik, filer_name, market_maker, put_call, names FROM sec13f_filer_options ORDER BY cik") == [
        ("2000001", "MANAGER 2000001", False, "PUT", 1), ("2000004", "CTC LLC", True, "CALL", 1)]


def test_the_market_maker_names_match_as_whole_words_only():
    import duckdb
    con = duckdb.connect()
    sql = sec13f_extras.market_maker_sql("n")
    got = con.execute(f"SELECT n, {sql} FROM (VALUES ('CTC LLC'), ('IMC-Chicago, LLC'), ('Susquehanna Intl Group'), "
                      f"('ARCTCO CAPITAL'), ('SIGMA PLANNING'), (NULL)) t(n)").fetchall()
    assert got == [("CTC LLC", True), ("IMC-Chicago, LLC", True), ("Susquehanna Intl Group", True),
                   ("ARCTCO CAPITAL", False), ("SIGMA PLANNING", False), (None, False)]


def test_convertible_par_sums_by_the_one_issuer_its_cusip6_names(monkeypatch, http_mock):
    """Two funds hold MSFT notes (CUSIP6 594918, MSFT's alone); a BF note's CUSIP6 is two share classes' and is left
    out rather than guessed. Par is principal, never shares, and stays off the long book."""
    _world(monkeypatch, http_mock, {"2026-10-27": [
        _f("0002000001-26-000001", 2000001, "2026-10-27", _book() + [
            _h("MICROSOFT CORP NOTE 0.5% 2030", "594918AX2", 1_100_000, 1_000_000, sh_type="PRN"),
            _h("BROWN FORMAN NOTE", "115637AB6", 500_000, 500_000, sh_type="PRN")]),
        _f("0002000002-26-000002", 2000002, "2026-10-27", _book() + [
            _h("MICROSOFT CORP NOTE 0.5% 2030", "594918AX2", 550_000, 500_000, sh_type="PRN")]),
        _f("0002000003-26-000003", 2000003, "2026-10-27", _book())]})
    _serve()
    assert _served("SELECT ticker, filers, cusips, par, value FROM sec13f_prn_par") == [
        ("MSFT", 2, 1, 1_500_000.0, 1_650_000.0)]
    assert _served("SELECT shares FROM sec13f_ticker_period WHERE ticker = 'MSFT'") == [(300.0,)]


def test_a_combination_report_is_partial_and_a_late_new_holdings_after_a_confidential_report_is_a_reveal(
        monkeypatch, http_mock):
    """Filer 1 left holdings out in confidence on 27 Oct and revealed an MSFT position on 15 Dec, 29 days after the
    16 Nov deadline. Filer 2's new-holdings amendment is not a reveal: nothing was omitted. Filer 3 files a
    combination report: other managers report part of its book."""
    _world(monkeypatch, http_mock, {
        "2026-10-27": [
            _f("0002000001-26-000001", 2000001, "2026-10-27", _book(names=3), confidential=True),
            _f("0002000002-26-000002", 2000002, "2026-10-27", _book(names=3)),
            _f("0002000003-26-000003", 2000003, "2026-10-27", _book(names=3), report_type="13F COMBINATION REPORT")],
        "2026-12-15": [
            _f("0002000001-26-000009", 2000001, "2026-12-15", [_h("MICROSOFT CORP", MSFT, 2_000_000, 5_000)],
               form="13F-HR/A", amendment_type="NEW HOLDINGS", amendment_no=1),
            _f("0002000002-26-000010", 2000002, "2026-12-15", [_h("MICROSOFT CORP", MSFT, 40_000, 100)],
               form="13F-HR/A", amendment_type="NEW HOLDINGS", amendment_no=1)]})
    _serve("2026-12-16")
    assert _served("SELECT cik, accession, filed, days_late, names, value, top_issuer FROM sec13f_late_reveals") == [
        ("2000001", "0002000001-26-000009", date(2026, 12, 15), 29, 1, 2_000_000.0, "MICROSOFT CORP")]
    assert _served("SELECT cik, report_type, partial, manager_name FROM sec13f_reported_by") == [
        ("2000003", "13F COMBINATION REPORT", True, None)]
