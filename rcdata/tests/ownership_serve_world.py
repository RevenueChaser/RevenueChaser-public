"""The world ``ownership/serve``'s tests are read in: the spine, the 13F filings over it, and one serve.

Split out of ``test_ownership_serve.py`` (#1153). The ``store`` fixture builds the whole spine, three 13F runs, the
OpenFIGI map and a serve, which measured 13-25 s a test; with all 48 tests in one file that file alone was 500 s and
the unit tier could not run shorter than it, because ``pytest --dist loadfile`` gives a whole file to one worker. So
the tests sit in three files beside each other and share this world:

- ``test_ownership_serve.py``: the served tables, the period summary, the quarter's close and the read API.
- ``test_ownership_serve_cusips.py``: how each CUSIP is named, refused, or left unmapped.
- ``test_ownership_serve_filings.py``: what the filings themselves say -- VALUE's scale, exits, successions,
  investor types and the ``short_interest`` bridge -- each over its own small world rather than this one.

Nothing here is a test; pytest reads it only through those three files.
"""

from __future__ import annotations

from datetime import date

import pytest

from revenuechaser.rcdata import ops, serving
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.ownership import sec, sec13f, serve
from revenuechaser.rcdata.build.spine import openfigi_map

from . import ownership_fixture as ox
from . import spine_fixture as fx
from .test_spine_security import built, run_all  # noqa: F401 (the spine built from every one of its sources)


Q2, Q3 = date(2026, 6, 30), date(2026, 9, 30)


MSFT_OLD, OLD_VYLR, WFC_PC, NOBODY = "594918100", "92921Q100", "949746804", "999999999"


def _h(issuer: str, cusip: str, value: float, shares: float, **kw) -> dict:
    return ox.f13_holding(issuer, cusip, value, shares, **kw)


def _f(acc: str, cik: int, day: str, holdings: list[dict], period: str = "09-30-2026", **kw) -> tuple:
    form = kw.get("form", "13F-HR")
    return (ox.idx_row(cik, f"MANAGER {cik}", form, day, acc), ox.f13_filing(acc, cik, day, holdings, period, **kw))


def _edgar(http_mock) -> ox.Edgar:
    e = ox.Edgar()
    e.add_day("2001-11-14", [_f("0001000001-01-000001", 1000001, "2001-11-14",
                                [_h("MICROSOFT CORP", MSFT_OLD, 6, 100)], period="09-30-2001")])
    e.add_day("2026-08-14", [
        _f("0001000001-26-000002", 1000001, "2026-08-14", [_h("MICROSOFT CORP", "594918104", 400_000, 1000),
                                                           _h("EATON CORP PLC", "G29183103", 150_000, 500)],
           period="06-30-2026"),
        _f("0001000002-26-000003", 1000002, "2026-08-14", [_h("MICROSOFT CORP", "594918104", 120_000, 300),
                                                           _h("EATON CORP PLC", "G29183103", 30_000, 100)],
           period="06-30-2026")])
    e.add_day("2026-10-27", [
        _f("0001000001-26-000010", 1000001, "2026-10-27", [
            _h("MICROSOFT CORP", "594918104", 480_000, 1200), _h("EATON CORP PLC", "G29183103", 160_000, 500),
            _h("MICROSOFT CORP", "594918104", 90_000, 400, put_call="Put"),
            _h("MICROSOFT CORP", "594918104", 10_000, 10_000, sh_type="PRN"),
            _h("HEICO CORP", "422806109", 20_000, 100), _h("HEICO CORP CL A", "422806208", 16_000, 100)]),
        # B's restatement replaces its holdings report: the FDX line is gone, MSFT is 350.
        _f("0001000002-26-000011", 1000002, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 120_000, 300),
                                                           _h("FEDEX CORP", "31428X106", 25_000, 100)]),
        _f("0001000002-26-000012", 1000002, "2026-10-27", [_h("MICROSOFT CORP", "594918104", 140_000, 350)],
           form="13F-HR/A", amendment_type="RESTATEMENT", amendment_no=1),
        # C's new-holdings amendment adds to its report.
        _f("0001000003-26-000013", 1000003, "2026-10-27", [_h("NVR INC", "62944T105", 250_000, 50)]),
        _f("0001000003-26-000014", 1000003, "2026-10-27", [_h("WELLS FARGO", "949746101", 10_000, 200)],
           form="13F-HR/A", amendment_type="NEW HOLDINGS", amendment_no=1),
        _f("0001000004-26-000015", 1000004, "2026-10-27", [
            _h("OLD VAYLOR CORP", OLD_VYLR, 1_000, 100), _h("NOBODY KNOWS INC", NOBODY, 500, 50),
            _h("WELLS FARGO PFD SER C", WFC_PC, 250, 10)])])
    e.install(http_mock)
    return e


def _thirteen_f(**params) -> dict:
    return base.run_request({"dataset": sec13f.NAME, "params": params}, sleep=lambda s: None)


def _serve(day: str = "2026-10-28", **params) -> dict:
    return base.run_request({"dataset": serve.NAME, "requested_by": "cli", "params": {"as_of": day, **params}})


@pytest.fixture
def store(built, monkeypatch):
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    # OpenFIGI still names the reused ticker for the old company's CUSIP; it names the preferred the spine holds
    # without a Compustat link.
    monkeypatch.setitem(fx.FIGI, OLD_VYLR, {"figi": "BBG000OLDVY1", "ticker": "VYLR", "exchCode": "US",
                                            "securityType": "Common Stock"})
    monkeypatch.setitem(fx.FIGI, WFC_PC, {"figi": "BBG000WFCPC1", "ticker": "WFC-PC", "exchCode": "US",
                                          "securityType": "Preferred"})
    _edgar(built)
    _thirteen_f(as_of="2026-10-28")
    _thirteen_f(mode="backfill", **{"from": "2026-08-14", "to": "2026-08-14"})
    _thirteen_f(mode="backfill", **{"from": "2001-11-14", "to": "2001-11-14"})
    built.requests.clear()
    run_all("2026-10-28", [openfigi_map.NAME])
    return _serve()


def _served(sql: str, *args) -> list[tuple]:
    with serving.open_read("ownership") as con:
        return con.execute(sql, list(args)).fetchall()


def _issues() -> dict[tuple[str, str], str]:
    return {(i["kind"], i["key"]): i["detail"] for i in ops.open_issues(serve.NAME, limit=500)[1]}


PRICES = {"594918104": 400.0, "115637100": 60.0, "115637209": 58.0, "084670702": 450.0, "037833100": 230.0,
          "36467W109": 25.0}


def _book(scale: float = 1.0, names: int = 6) -> list[dict]:
    return [_h(f"ISSUER {c}", c, round(px * 100 * scale, 2), 100) for c, px in list(PRICES.items())[:names]]


def _book_day(http_mock, days: dict[str, list[tuple[float, str]]]) -> None:
    """Each index day's filers, ``(scale, period)`` each, ingested one day at a time."""
    ox.make_spine()
    e = ox.Edgar()
    n = 0
    for day, books in days.items():
        rows = []
        for scale, period in books:
            n += 1
            rows.append(_f(f"0002{n:06d}-22-{n:06d}", 2000000 + n, day, _book(scale=scale), period=period))
        e.add_day(day, rows)
    e.install(http_mock)
    for day in days:
        _thirteen_f(mode="backfill", **{"from": day, "to": day})
