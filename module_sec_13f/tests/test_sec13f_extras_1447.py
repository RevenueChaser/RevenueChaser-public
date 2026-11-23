"""#1447, #1449, #1450 (the board half; mock approved by avo 22 Nov 2026 23:09): a ticker's option holders and its
convertible notes in the row's detail, and the reported-by and late-reveal cards on the Investors tab."""
from __future__ import annotations

from revenuechaser.module_sec_13f import report


def _opt(cik, name, mm, cv=None, cs=None, pv=None, ps=None, contracts=0):
    return {"ticker": "NVDA", "period": "2026-06-30", "cik": cik, "filer_name": name, "market_maker": mm,
            "call_value": cv, "call_shares": cs, "put_value": pv, "put_shares": ps, "contracts_read": contracts}


def test_option_holders_split_into_funds_and_market_makers_largest_first():
    v = report.options_view([_opt("1", "SMALL FUND", False, cv=10.0, cs=1.0),
                             _opt("2", "BIG FUND", False, cv=50.0, cs=5.0, pv=50.0, ps=5.0),
                             _opt("3", "CITADEL SECURITIES", True, pv=300.0, ps=30.0, contracts=2)])
    assert (v["period"], v["filers"], v["call_value"], v["put_value"]) == ("2026-06-30", 3, 60.0, 350.0)
    assert v["mm_share"] == round(100 * 300 / 410, 1)
    assert [r["filer_name"] for r in v["funds"]] == ["BIG FUND", "SMALL FUND"]
    assert [(r["filer_name"], r["contracts_read"]) for r in v["market_makers"]] == [("CITADEL SECURITIES", 2)]


def test_no_option_lines_is_an_empty_view_not_a_ratio():
    v = report.options_view([])
    assert (v["period"], v["filers"], v["mm_share"], v["funds"], v["market_makers"]) == (None, 0, None, [], [])


def test_convertible_notes_sum_principal_by_filer_and_note():
    rows = [{"period": "2026-06-30", "cik": "1", "filer_name": "A", "cusip": "594972AA1", "name_of_issuer": "STRATEGY",
             "title_of_class": "NOTE 0% 2030", "par": 100.0, "value": 120.0},
            {"period": "2026-06-30", "cik": "2", "filer_name": "B", "cusip": "594972AA1", "name_of_issuer": "STRATEGY",
             "title_of_class": "NOTE 0% 2030", "par": 300.0, "value": 330.0},
            {"period": "2026-06-30", "cik": "2", "filer_name": "B", "cusip": "594972AB9", "name_of_issuer": "STRATEGY",
             "title_of_class": "NOTE 0.625% 2028", "par": 50.0, "value": 80.0}]
    v = report.prn_view(rows)
    assert (v["par"], v["value"], v["filers"], v["notes"]) == (450.0, 530.0, 2, 2)
    assert [(r["filer_name"], r["par"]) for r in v["rows"]] == [("B", 300.0), ("A", 100.0), ("B", 50.0)]


def test_reported_by_is_one_entry_per_filer_combination_reports_first():
    rows = [{"cik": "1", "filer_name": "ALPHA LLC", "period": "2026-06-30", "partial": False, "manager_name": "X"},
            {"cik": "1", "filer_name": "ALPHA LLC", "period": "2026-06-30", "partial": False, "manager_name": "Y"},
            {"cik": "2", "filer_name": "ZETA LP", "period": "2026-06-30", "partial": True, "manager_name": None}]
    v = report.reported_by_view(rows)
    assert v["total"] == 2
    assert [(e["filer_name"], e["partial"], e["managers"]) for e in v["filers"]] == [
        ("ZETA LP", True, []), ("ALPHA LLC", False, ["X", "Y"])]


def test_the_extras_routes_answer_from_the_store_readers(monkeypatch):
    from revenuechaser.app import dashboard
    from revenuechaser.core import ownership
    monkeypatch.setattr(ownership, "sec13f_ticker_extras", lambda t: {
        "options": [_opt("2", "BIG FUND", False, cv=50.0, cs=5.0)], "prn": []})
    monkeypatch.setattr(ownership, "sec13f_reported_by", lambda q: [
        {"cik": "2", "filer_name": "ZETA LP", "period": "2026-06-30", "partial": True, "manager_name": None}])
    monkeypatch.setattr(ownership, "sec13f_late_reveals", lambda n: [{"cik": "1", "filed": "2026-11-20"}])
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    r = c.get("/api/sec_13f/nvda/extras").get_json()
    assert (r["ok"], r["ticker"], r["options"]["filers"], r["prn"]["rows"]) == (True, "NVDA", 1, [])
    assert c.get("/api/sec_13f/bad ticker!/extras").status_code == 400
    assert c.get("/api/sec_13f/reported_by?q=zeta").get_json()["filers"][0]["partial"] is True
    assert c.get("/api/sec_13f/reveals").get_json()["reveals"] == [{"cik": "1", "filed": "2026-11-20"}]


def test_the_board_page_opens_the_extras_in_the_detail_and_on_the_investors_tab():
    assert "window.rcDetailExtras(td, t)" in report.JS and "window.rcInvExtrasOpen()" in report.INVESTORS_JS
    assert "window.rcDetailExtras = function" in report.EXTRAS_JS
    html = report.investors_html("")
    assert 'id="rb-list"' in html and 'id="rv-list"' in html
