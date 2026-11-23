"""The data the Grafana Jobs board's "spine" group draws (avo, 23 Nov 2026; the mock is mock12 of the spine shots).

Two answers feed it, both read-only:

- ``GET /api/build/datasets?detail=1`` (``metrics.datasets_detail``): per dataset, what it fetches (``about``), its
  place in the kind's flow (``group``, ``order``), how long its own last run took (``took_s``), Settings' checks
  and last three checks, its open build issues by kind, and its coverage against its target;
- ``GET /api/build/served/<kind>`` and ``.../sample/<table>`` (``newdata.served``, ``newdata.read_served_sample``):
  the live file's schema version, last build, tables and views with their rows and columns, and for the spine the
  identity funnel, the tiers and ``my_universe``.
"""
from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pytest

from revenuechaser.core import calendar
from revenuechaser.core.tests.panel_client import panel_test_client
from revenuechaser.module_settings import metrics, newdata
from revenuechaser.rcdata import ops, serving
from revenuechaser.rcdata.build import DATASETS
from revenuechaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401 - market roots per test
from revenuechaser.rcdata.tests.test_spine_security import built, run_all  # noqa: F401 - the 10 names

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)

#: The mock's "what it fetches" column, row counts left out (they are ``rows``), in the mock's row order.
MOCK = {
    "sec/company_tickers_exchange": "Every listed name: ticker, exchange, CIK.",
    "sec/company_tickers_mf": "Every fund and share class; the ETF candidates.",
    "wrds/sec_idhist": "gvkey, CUSIP, active or delisted, delisting date.",
    "wrds/co_hgic": "GICS sector, company CIK, country.",
    "wrds/idxcst_his": "S&P 500 / 400 / 600 membership over time.",
    "openfigi/map": "CUSIP to FIGI and security type (stock, ETF, preferred).",
    "alphavantage/listing_status": "Active and delisted US names.",
    "sec/ncen": "Funds' annual reports: ETF facts.",
    "funds/index_holdings": "Membership of the indexes the fund files carry (S&P, Russell, Dow).",
    "funds/etf_holdings": "What each ETF holds, read daily.",
    "spine/security": "Link, type, tier, index vote, ETF identity, my_universe.",
}


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(calendar, "_now", lambda: NOW)
    newdata.clear_sample_cache()


@pytest.fixture
def client():
    from revenuechaser.app.dashboard import app
    return panel_test_client(app)


def _detail(**kw) -> dict[str, dict]:
    kw.setdefault("timer", {})
    kw.setdefault("providers", [])
    return {r["name"]: r for r in metrics.datasets_detail(NOW, **kw)}


# --- /api/build/datasets?detail=1 -----------------------------------------------------------------------------


def test_the_spine_rows_say_what_they_fetch_and_stand_in_the_flow_the_mock_draws():
    rows = _detail()
    spine = sorted((r for r in rows.values() if r["kind"] == "spine"), key=lambda r: r["order"])
    assert [r["name"] for r in spine] == list(MOCK), "weekly chain, then the daily files, then the build"
    assert {r["name"]: r["about"] for r in spine} == MOCK
    assert [r["group"] for r in spine] == ["weekly"] * 8 + ["daily"] * 2 + ["build"]
    assert [r["order"] for r in spine] == list(range(11))
    # every other dataset says something too: its card's label when it has no sentence of its own
    assert all(isinstance(r["about"], str) and r["about"] for r in rows.values())


def test_the_flow_is_derived_from_the_registry_and_the_cadence_not_from_a_list(monkeypatch):
    """A Settings override of the cadence moves the row: a weekly source made daily joins the daily files."""
    ops.schedule_set("openfigi/map", "daily", None)
    spine = sorted((r for r in _detail().values() if r["kind"] == "spine"), key=lambda r: r["order"])
    names = [r["name"] for r in spine]
    assert names.index("openfigi/map") > names.index("sec/ncen")
    assert names.index("openfigi/map") < names.index("spine/security") == len(names) - 1
    assert next(r for r in spine if r["name"] == "openfigi/map")["group"] == "daily"


def test_a_row_carries_its_own_took_its_checks_its_last_three_and_its_coverage():
    ds = "spine/security"
    for i, (result, note) in enumerate((("changed", "tier v4"), ("changed", "tier v6"), ("unchanged", None),
                                        ("unchanged", "last"))):
        run = f"run-{i}"
        ops.start_run(run, ds, "queue")
        # 30 s of its own and 200 s waiting for the other members of its pass: ``took_s`` is the 30
        ops.finish_run(run, "ok", None, {"steps": {"start": 1.0, "fetch": 4.0, "build": 20.0, "check": 5.0,
                                                   "waiting": 200.0}})
        ops.record_check(ds, result, source_as_of="2026-11-22", rows=10399, added=i, removed=0, coverage=0.994,
                         calls=0, next_check_due="2026-11-24", run_id=run, note=note)
    row = _detail()[ds]
    assert row["took_s"] == 30.0
    assert row["coverage"] == 0.994 and row["coverage_target"] == 0.98
    assert [c["label"] for c in row["checks"]][:3] == ["Last run", "Source as of", "Coverage"]
    assert next(c for c in row["checks"] if c["label"] == "Coverage")["ok"] is True
    assert [r["note"] for r in row["recent"]] == ["last", None, "tier v6"]
    assert set(row["recent"][0]) >= {"checked_on", "result", "source_as_of", "rows", "added", "removed", "calls"}
    assert row["rows"] == 10399, "the row count is its own field, never inside the sentence"


def test_a_run_with_no_step_times_has_no_took():
    ops.start_run("r0", "sec/ncen", "queue")
    ops.finish_run("r0", "ok")
    ops.record_check("sec/ncen", "unchanged", run_id="r0")
    assert _detail()["sec/ncen"]["took_s"] is None
    assert _detail()["wrds/co_hgic"]["took_s"] is None, "never run"


def test_the_open_issues_come_grouped_by_kind_with_the_first_ten_of_each():
    ds = "spine/security"
    for i in range(12):
        ops.record_issue(ds, "tier_a_no_figi", f"T{i:02d}", f"CUSIP {i}: absent")
    ops.record_issue(ds, "member_not_in_sec", "sp500:HOLX", "ishares IVV holds HOLOGIC INC")
    ops.record_issue("funds/index_holdings", "elsewhere", "X", "not this dataset's")
    row = _detail()[ds]
    assert row["open_issues"] == 13
    kinds = row["issue_kinds"]
    assert [(k["kind"], k["count"]) for k in kinds] == [("tier_a_no_figi", 12), ("member_not_in_sec", 1)]
    assert len(kinds[0]["rows"]) == 10 and set(kinds[0]["rows"][0]) == {"key", "detail", "found_on"}
    assert kinds[0]["rows"][0]["key"] == "T11", "newest first"
    assert kinds[1]["rows"] == [{"key": "sp500:HOLX", "detail": "ishares IVV holds HOLOGIC INC",
                                 "found_on": kinds[1]["rows"][0]["found_on"]}]


def test_the_detail_route_serves_the_new_fields(client):
    one = next(d for d in client.get("/api/build/datasets?detail=1").get_json()["datasets"]
               if d["name"] == "spine/security")
    assert {"about", "group", "order", "took_s", "checks", "recent", "issue_kinds", "coverage",
            "coverage_target"} <= set(one)


#: The mock's job names, in its row order.
LABELS = ["SEC tickers + exchange", "SEC fund file", "Compustat securities", "Compustat companies",
          "S&P constituents history", "OpenFIGI map", "Alpha Vantage listing", "SEC N-CEN", "Index fund files",
          "ETF holdings", "Spine build"]


def test_every_row_has_a_short_label_and_the_spine_ones_are_the_mock_s():
    rows = _detail()
    spine = sorted((r for r in rows.values() if r["kind"] == "spine"), key=lambda r: r["order"])
    assert [r["label"] for r in spine] == LABELS
    assert rows["market_series"]["label"] == "Market series", "without a short name: Settings' card label"


def test_a_kind_s_whole_open_issue_list_has_a_route_the_row_links_to(client):
    ds = "spine/security"
    for i in range(25):
        ops.record_issue(ds, "tier_a_no_figi", f"T{i:02d}", "absent")
    ops.record_issue(ds, "member_not_in_sec", "sp500:HOLX", "ishares IVV holds HOLOGIC INC")
    [k] = [k for k in _detail()[ds]["issue_kinds"] if k["kind"] == "tier_a_no_figi"]
    assert k["issues_url"] == "/api/build/issues/spine/security?kind=tier_a_no_figi"
    body = client.get(k["issues_url"]).get_json()
    assert body["ok"] is True and body["dataset"] == ds and body["kind"] == "tier_a_no_figi"
    assert body["count"] == 25 and len(body["issues"]) == 25 and body["issues"][0]["key"] == "T24"
    assert set(body["issues"][0]) == {"kind", "key", "detail", "found_on"}
    every = client.get("/api/build/issues/spine/security").get_json()
    assert every["count"] == 26 and len(every["issues"]) == 26 and every["kind"] is None
    assert client.get("/api/build/issues/no/such").status_code == 404


# --- /api/build/served/<kind> -----------------------------------------------------------------------------------


def _hand_made_market_file() -> None:
    """A served ``market`` file written by hand: two tables, a view, and the build's own bookkeeping."""
    path = serving.live_path("market")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute(f"CREATE TABLE {serving.VERSION_TABLE} (kind TEXT, version INTEGER, built_at DOUBLE, "
                    "build_id TEXT, build_mode TEXT)")
        con.execute(f"INSERT INTO {serving.VERSION_TABLE} VALUES ('market', 7, 1763862420.0, "
                    "'20261123T014757Z-dad8a007', 'live')")
        con.execute("CREATE TABLE build_manifest (path TEXT, size BIGINT, mtime DOUBLE)")
        con.execute("CREATE TABLE market_series (series_id TEXT, obs_date DATE, value DOUBLE)")
        con.execute("INSERT INTO market_series SELECT 's' || (i % 3), DATE '2026-01-01' + CAST(i AS INTEGER), i "
                    "FROM range(9) t(i)")
        con.execute("CREATE TABLE other (x INTEGER)")
        con.execute("CREATE VIEW series_ids AS SELECT DISTINCT series_id FROM market_series")
    finally:
        con.close()


def test_a_served_file_lists_its_tables_and_views_with_rows_and_columns_and_its_build():
    _hand_made_market_file()
    got = newdata.served("market")
    assert got["kind"] == "market" and got["file"] == "market.duckdb" and got["schema_version"] == 7
    assert got["build"]["build_id"] == "20261123T014757Z-dad8a007" and got["build"]["mode"] == "live"
    assert got["build"]["built_at"] is not None
    tables = {t["name"]: t for t in got["tables"]}
    assert set(tables) == {"market_series", "other"}, "the version row and the manifest are bookkeeping"
    assert tables["market_series"]["rows"] == 9 and tables["other"]["rows"] == 0
    assert tables["market_series"]["columns"] == [{"name": "series_id", "type": "VARCHAR"},
                                                  {"name": "obs_date", "type": "DATE"},
                                                  {"name": "value", "type": "DOUBLE"}]
    assert got["views"] == [{"name": "series_ids", "rows": 3, "columns": [{"name": "series_id", "type": "VARCHAR"}]}]
    assert "identity" not in got and "my_universe" not in got, "the spine's own parts are the spine's"


def test_the_served_routes_answer_and_say_why_when_they_cannot(client):
    assert client.get("/api/build/served/nope").status_code == 404
    r = client.get("/api/build/served/market")
    assert r.status_code == 409 and "not been built" in r.get_json()["error"]
    _hand_made_market_file()
    body = client.get("/api/build/served/market").get_json()
    assert body["ok"] is True and body["schema_version"] == 7
    sample = client.get("/api/build/served/market/sample/market_series").get_json()
    assert sample["ok"] is True and sample["kind"] == "market" and sample["table"] == "market_series"
    assert len(sample["rows"]) == newdata.SERVED_SAMPLE_ROWS == 6
    assert [c["name"] for c in sample["columns"]] == ["series_id", "obs_date", "value"]
    assert sample["rows"][0][1] == "2026-01-09", "newest first, by the table's date column"
    view = client.get("/api/build/served/market/sample/series_ids").get_json()
    assert view["ok"] is True and len(view["rows"]) == 3
    assert client.get("/api/build/served/market/sample/serving_schema_version").status_code == 404
    assert client.get("/api/build/served/market/sample/x%22%3BDROP%20TABLE%20other%3B--").status_code == 404
    assert client.get("/api/build/served/nope/sample/market_series").status_code == 404


def test_a_sample_is_read_once_an_hour_per_file(monkeypatch):
    _hand_made_market_file()
    opened = []
    real = serving.open_read
    monkeypatch.setattr(serving, "open_read", lambda kind: opened.append(kind) or real(kind))
    first = newdata.read_served_sample("market", "market_series", NOW)
    assert newdata.read_served_sample("market", "market_series", NOW) == first
    assert opened == ["market"]


@pytest.mark.usefixtures("built")
def test_the_served_spine_carries_the_funnel_the_tiers_and_my_universe():
    got = newdata.served("spine")
    names = {t["name"] for t in got["tables"]}
    assert {"security", "index_membership", "my_universe", "my_universe_changes"} <= names
    assert {"equity_universe", "security_master", "index_constituents", "index_tickers"} <= {
        v["name"] for v in got["views"]}
    assert got["tier_rule"] is not None
    assert got["tiers"] == {"A": 10, "B": 2, "C": 1, "D": 1}
    steps = {s["key"]: s["count"] for s in got["identity"]["steps"]}
    assert steps["sec"] == 14 and steps["tier_a"] == 10
    mu = got["my_universe"]
    assert mu["built"] is True and mu["total"] == mu["kinds"]["stock"]
    assert sum(mu["by_tier"]["stock"].values()) == mu["kinds"]["stock"]
    assert mu["entered_names"] == sorted(mu["entered_names"]) and len(mu["entered_names"]) == min(mu["entered"], 20)
    assert mu["left_names"] == []
    assert mu["rule_values"]["etf_aum_floor"] == 100_000_000 and mu["rule_values"]["etf_aum_exit_floor"] == 80_000_000
    assert mu["rule_values"]["etf_adv_floor"] == 10_000_000 and mu["rule_values"]["etf_adv_exit_floor"] == 8_000_000
    sample = newdata.read_served_sample("spine", "equity_universe", NOW)
    assert 0 < len(sample["rows"]) <= 6 and sample["columns"][0]["name"] == "ticker"
