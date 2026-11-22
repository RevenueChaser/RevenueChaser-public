"""``ownership/serve``: the 13F totals per ticker and quarter over the real spine (the amendment rule, long equity
only), the period summary with the plan's two counts, the bridge view ``sec13f_totals``, the quarter's close on the
SEC's own data set, the read API, and a run of another ownership dataset that carries the 13F tables over instead of
deriving them again.

The world is ``ownership_serve_world`` (#1153); how a CUSIP is named is ``test_ownership_serve_cusips.py`` and what
the filings themselves say is ``test_ownership_serve_filings.py``.
"""

from __future__ import annotations

import json
from datetime import date

from revenuechaser.rcdata import ops, read
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.ownership import finra, sec13f, sec13f_listing, serve

from . import ownership_fixture as ox
from .ownership_serve_world import (
    OLD_VYLR, Q2, Q3, _issues, _serve, _served, built, store
)  # noqa: F401 (the shared world: its helpers and the fixtures a test asks for by name)


PER_QUARTER = ("_px", "_ratio", "_held", "_cp", "_m_hist", "_m_cur", "sec13f_cusip_map", "_filers", "_pos", "_tot",
               "_shape", "_pairs")


SERVED_13F = {"sec13f_filer_period": "cik, period", "sec13f_cusip_map": "cusip, period",
              "sec13f_ticker_period": "ticker, period", "sec13f_periods": "period"}


SUMMER_SET, SPRING_SET = "01jun2026-31aug2026_form13f.zip", "01mar2026-31may2026_form13f.zip"


def _listed(name: str) -> dict:
    first, last = sec13f_listing.sec13f_sets.window(name)
    return {"name": name, "first_day": first, "last_day": last}


def test_the_amendment_rule_long_equity_only_and_share_classes_apart(store):
    assert store["result"] == "changed"
    assert _served("SELECT ticker, shares, value, holders, cusips FROM sec13f_ticker_period WHERE period = ? "
                   "ORDER BY ticker", Q3) == [
        ("ETN", 500.0, 160_000.0, 1, 1), ("HEI", 100.0, 20_000.0, 1, 1), ("HEI-A", 100.0, 16_000.0, 1, 1),
        ("MSFT", 1550.0, 620_000.0, 2, 1), ("NVR", 50.0, 250_000.0, 1, 1), ("WFC", 200.0, 10_000.0, 1, 1),
        ("WFC-PC", 10.0, 250.0, 1, 1)]


def test_the_metrics_compare_with_the_calendar_quarter_before(store):
    cols = ("top10_pct, hhi, new_holders, exited_holders, buy_flow, sell_flow, breadth, breadth_chg, prev_period, "
            "filers")
    rows = {(t, p): r for t, p, *r in _served(f"SELECT ticker, period, {cols} FROM sec13f_ticker_period")}
    assert rows[("MSFT", Q3)] == [100.0, 6503.6, 0, 0, 250.0, 0.0, 50.0, -50.0, Q2, 4]
    assert rows[("ETN", Q3)] == [100.0, 10000.0, 0, 1, 0.0, 100.0, 25.0, -75.0, Q2, 4]
    # NVR's one holder is filer 1000003, which filed no report for the June quarter: it started reporting, so it is
    # neither a new holder nor a buy (#732).
    assert rows[("NVR", Q3)] == [100.0, 10000.0, 0, 0, 0.0, 0.0, 25.0, 25.0, Q2, 4]
    # The quarter before 30 Jun 2026 is not in the store: what it would compare with is unknown, never 0.
    assert rows[("MSFT", Q2)] == [100.0, 6449.7, None, None, None, None, 100.0, None, date(2026, 3, 31), 2]
    assert rows[("MSFT", date(2001, 9, 30))][6:] == [100.0, None, date(2001, 6, 30), 1]


def test_the_period_summary_and_the_plans_two_counts(store):
    assert _served("SELECT period, filers, filings_active, value_total, value_mapped, coverage, unmapped_cusips, "
                   "refused_value, filing_deadline, filed_through FROM sec13f_periods "
                   "ORDER BY period DESC LIMIT 2") == [
        (Q3, 4, 5, 1_077_750.0, 1_076_250.0, 0.9986, 2, 1_000.0, date(2026, 11, 16), date(2026, 10, 27)),
        (Q2, 2, 2, 700_000.0, 700_000.0, 1.0, 0, 0.0, date(2026, 8, 14), date(2026, 8, 14))]
    # 30 Sep is not complete before its deadline (16 Nov): the counts are the newest complete quarter's.
    assert store["coverage"] == 1.0
    assert "S&P 500 names with 13F holders in 2026-06-30: 2 of 5" in store["note"]
    assert "13F value mapped in 2026-06-30: 100.00%" in store["note"]


def test_the_totals_view_keeps_the_old_table_shape(store):
    (entry,) = _served("SELECT entry FROM sec13f_totals WHERE ticker = 'MSFT'")[0]
    entry = json.loads(entry)
    assert sorted(entry) == ["2001-09-30", "2026-06-30", "2026-09-30"]
    assert entry["2026-09-30"] == {"shares": 1550.0, "value": 620_000.0, "holders": 2, "new_holders": 0,
                                   "exited_holders": 0, "top10_pct": 100.0, "hhi": 6503.6, "buy_flow": 250.0,
                                   "sell_flow": 0.0, "breadth": 50.0, "breadth_chg": -50.0}


def test_the_filing_deadline_rolls_past_weekends_and_washingtons_birthday():
    assert serve.filing_deadline(date(2026, 9, 30)) == date(2026, 11, 16)       # 14 Nov is a Saturday
    assert serve.filing_deadline(date(2026, 6, 30)) == date(2026, 8, 14)
    assert serve.filing_deadline(date(2025, 12, 31)) == date(2026, 2, 17)       # Sat 14, Sun 15, Mon 16 a holiday
    assert serve.filing_deadline(date(2026, 3, 31)) == date(2026, 5, 15)


def test_another_datasets_run_carries_the_13f_tables_over(store, built, monkeypatch):
    before = _served("SELECT * FROM sec13f_ticker_period ORDER BY ticker, period")
    monkeypatch.setenv("RC_FINRA_API_BASE", "https://finra.test")
    ox.Finra({"2026-10-15": [ox.finra_row("MSFT", "2026-10-15", 50_000_000)]}).install(built)

    def never():
        raise AssertionError("a FINRA run derived the 13F tables again")
    monkeypatch.setattr(sec13f.DATASET, "holding_files", never)
    row = base.run_request({"dataset": finra.NAME, "params": {"as_of": "2026-10-28"}})
    assert row["result"] == "changed"
    assert _served("SELECT * FROM sec13f_ticker_period ORDER BY ticker, period") == before
    assert ("cusip_owner_differs", OLD_VYLR) in _issues()


def test_the_13f_derive_runs_one_quarter_at_a_time_with_the_same_rows(store, monkeypatch):
    """Queue #242, 10 Nov 2026: a median's or a DISTINCT's state and a join's build side sit partly outside DuckDB's
    memory_limit; over every quarter at once the whole build was OOM-killed at 7.2 GiB, in the CUSIP map step."""
    seen: list[str] = []

    class Recording:
        def __init__(self, con):
            self._con = con

        def execute(self, sql, *args):
            seen.append(" ".join(sql.split()))
            return self._con.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(self._con, name)

    derive = serve.OwnershipServe._derive
    monkeypatch.setattr(serve.OwnershipServe, "_derive", lambda self, ctx, con: derive(self, ctx, Recording(con)))
    before = {t: _served(f"SELECT * FROM {t} ORDER BY {k}") for t, k in SERVED_13F.items()}
    _serve()
    for t in PER_QUARTER:
        fills = [q for q in seen if q.startswith(f"INSERT INTO {t} ")]
        assert fills and all("period = ?" in q for q in fills), t
        assert not any(q.startswith(f"CREATE OR REPLACE TEMP TABLE {t} AS") for q in seen), t
    assert {t: _served(f"SELECT * FROM {t} ORDER BY {k}") for t, k in SERVED_13F.items()} == before


def test_the_page_is_awaited_from_a_passed_deadline_until_a_set_holds_it():
    # 30 Jun's deadline (14 Aug) has passed on 28 Oct, 30 Sep's (16 Nov) has not.
    assert sec13f_listing.awaited(date(2026, 10, 28), []) == date(2026, 8, 14)
    assert sec13f_listing.awaited(date(2026, 10, 28), [_listed(SPRING_SET)]) == date(2026, 8, 14)
    assert sec13f_listing.awaited(date(2026, 10, 28), [_listed(SUMMER_SET)]) is None
    # On 20 Nov the September quarter's deadline has passed: its set (Sep-Nov) is awaited until listed.
    assert sec13f_listing.awaited(date(2026, 11, 20), [_listed(SUMMER_SET)]) == date(2026, 11, 16)
    assert sec13f_listing.awaited(date(2026, 11, 20), [_listed(SUMMER_SET),
                                                      _listed("01sep2026-30nov2026_form13f.zip")]) is None


def test_a_quarter_closes_when_the_sec_lists_the_data_set_that_holds_its_deadline(store, built, monkeypatch):
    built.routes.insert(0, (ox.SETS_PAGE_PATH, ox.sets_page([f"/files/structureddata/data/form-13f-data-sets/{n}"
                                                             for n in (SUMMER_SET, SPRING_SET)]), 200, {}))
    built.requests.clear()
    request = {"dataset": sec13f_listing.NAME, "requested_by": "cli", "params": {"as_of": "2026-10-28"}}
    assert base.run_request(request)["result"] == "changed"
    assert len(built.calls(ox.SETS_PAGE_PATH)) == 1
    base.run_request(request)                                    # the set is listed: nothing awaited, no call
    assert len(built.calls(ox.SETS_PAGE_PATH)) == 1
    assert not built.calls("_form13f.zip")                       # listed, never downloaded
    _serve()
    assert _served("SELECT period, data_set, closed FROM sec13f_periods WHERE period >= ? ORDER BY period", Q2) == [
        (Q2, SUMMER_SET, True), (Q3, None, False)]
    # Past 30 Sep's deadline the quarter is still not complete: its set is not published yet.
    monkeypatch.setattr(read.calendar, "today_ny", lambda: date(2026, 11, 20))
    assert [(r["period"], r["complete"]) for r in read.holders_13f(["msft"])][-2:] == [(Q2, True), (Q3, False)]


def test_the_breaks_and_the_live_ticker_list_follow_the_closed_rule(store, built, monkeypatch):
    """#732 F3: past 30 Sep's deadline but before its set is listed, the quarter is not settled for the breaks or for
    ``tickers_13f`` either, as it is not for ``complete``: one rule for every reader."""
    built.routes.insert(0, (ox.SETS_PAGE_PATH, ox.sets_page([f"/files/structureddata/data/form-13f-data-sets/{n}"
                                                             for n in (SUMMER_SET, SPRING_SET)]), 200, {}))
    base.run_request({"dataset": sec13f_listing.NAME, "requested_by": "cli", "params": {"as_of": "2026-10-28"}})
    _serve(day="2026-11-20")
    assert _served("SELECT count(*) FROM sec13f_filer_breaks WHERE period = ?", Q3) == [(0,)]
    monkeypatch.setattr(read.calendar, "today_ny", lambda: date(2026, 11, 20))
    assert read.tickers_13f() == read.tickers_13f(Q2)


def test_with_no_listing_read_a_quarter_falls_back_to_its_deadline(store, monkeypatch):
    assert _served("SELECT DISTINCT closed FROM sec13f_ticker_period") == [(None,)]
    monkeypatch.setattr(read.calendar, "today_ny", lambda: date(2026, 11, 20))
    assert [r["complete"] for r in read.holders_13f(["msft"])][-1] is True


def test_the_read_api_gives_13f_holders_with_a_complete_flag(store, monkeypatch):
    monkeypatch.setattr(read.calendar, "today_ny", lambda: date(2026, 10, 28))
    rows = read.holders_13f(["msft"])
    assert [(r["period"], r["holders"], r["complete"]) for r in rows] == [
        (date(2001, 9, 30), 1, True), (Q2, 2, True), (Q3, 2, False)]        # 30 Sep is due 16 Nov
    assert {r["status"] for r in rows} == {ops.latest_check(serve.NAME)["result"]}
    assert {r["source"] for r in rows} == {serve.NAME}
    assert [r["ticker"] for r in read.holders_13f(periods=[Q3])] == ["ETN", "HEI", "HEI-A", "MSFT", "NVR", "WFC",
                                                                     "WFC-PC"]
    periods = read.periods_13f()
    assert [(p["period"], p["complete"], p["coverage"]) for p in periods] == [
        (date(2001, 9, 30), True, 1.0), (Q2, True, 1.0), (Q3, False, 0.9986)]


def test_each_filers_largest_names_per_quarter_and_the_rest_add_up_to_100(store):
    """#928 (avo, 16 Nov 2026, Q16): one investor's holdings over time. A filer's named tickers are ranked by value;
    the CUSIPs no source names (filer 1000004's) are one row with no ticker, and a quarter's weights add up to 100."""
    rows = _served("SELECT ticker, rank FROM sec13f_filer_holdings WHERE cik = '1000001' AND period = ? "
                   "ORDER BY rank NULLS LAST", Q3)
    assert rows[0] == ("MSFT", 1) and [r[1] for r in rows] == list(range(1, len(rows) + 1))
    assert _served("SELECT count(*) FROM sec13f_filer_holdings WHERE cik = '1000004' AND period = ? "
                   "AND ticker IS NULL AND rank IS NULL", Q3) == [(1,)]
    assert _served("SELECT cik, period, round(sum(weight), 6) FROM sec13f_filer_holdings GROUP BY ALL "
                   "HAVING round(sum(weight), 6) <> 100") == []
    mine = read.filer_holdings_13f("0001000001")                 # the reader takes the CIK with or without zeros
    assert [r["ticker"] for r in mine if r["period"] == Q3][:1] == ["MSFT"]
    assert [r["period"] for r in mine] == sorted(r["period"] for r in mine) and read.filer_holdings_13f("") == []
