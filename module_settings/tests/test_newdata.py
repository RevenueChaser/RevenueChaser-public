"""PR 2 step 4: ``module_settings/newdata.py``, the data of the "New data system" section of Settings.

Everything comes from ``ops.sqlite`` (through ``rcdata.ops``), the Parquet folder listing, the backup manifest and
one read-only handle on the live serving file per call, closed before the call returns. A fixed clock throughout.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

import duckdb
import pytest

from revenuechaser.core import calendar, config, llm_prices, llm_spend
from revenuechaser.module_settings import newdata
from revenuechaser.rcdata import caps, ops, serving
from revenuechaser.rcdata.build import uw_spot_expiry_strike as spx
from revenuechaser.module_watchlists import store as wl_store

# 23:00 New York on Wednesday 28 Oct 2026: the latest complete session is that day.
NOW = datetime(2026, 10, 29, 3, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 28)


@pytest.fixture(autouse=True)
def roots(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MARKET_DIR", tmp_path / "market")
    monkeypatch.setattr(config, "MARKET_RAW_DIR", tmp_path / "market_raw")
    monkeypatch.setattr(config, "RAW_STORE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(ops, "read_log", ops.ReadLog(process="test"))
    monkeypatch.delenv(newdata.RETENTION_ENV, raising=False)
    monkeypatch.setattr(calendar, "_now", lambda: NOW)
    return tmp_path


def _card(data: dict, dataset: str) -> dict:
    return next(c for c in data["datasets"] if c["dataset"] == dataset)


def _check(dataset="uw/spot_expiry_strike", result="changed", as_of="2026-10-28", on=None, **kw):
    ops.record_check(dataset, result, source_as_of=as_of, checked_on=on or as_of, **kw)


# ── statuses ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_dataset_never_built_says_so():
    card = _card(newdata.collect(NOW), "market_series")
    assert card["status"] == "never" and card["checked_on"] is None


@pytest.mark.parametrize("result,as_of,want", [
    ("changed", "2026-10-28", "fresh"),
    ("unchanged", "2026-10-28", "unchanged"),
    ("changed", "2026-10-27", "late"),        # one session missed
    ("changed", "2026-10-26", "stale"),       # two missed
    ("failed", "2026-10-28", "stale"),        # the last check failed
])
def test_daily_status_from_the_sessions_missed(result, as_of, want):
    _check(result=result, as_of=as_of, coverage=1.0)
    assert _card(newdata.collect(NOW), "uw/spot_expiry_strike")["status"] == want


def test_coverage_under_target_is_late():
    target = newdata.COVERAGE_TARGET["uw/spot_expiry_strike"]
    _check(coverage=round(target - 0.01, 4))
    card = _card(newdata.collect(NOW), "uw/spot_expiry_strike")
    assert card["status"] == "late" and "coverage" in card["status_reason"]


def test_a_skip_after_a_good_run_keeps_the_good_runs_status_and_shows_the_skip():
    _check(coverage=1.0)
    _check(result="skipped", as_of=None, on="2026-10-28", note="skipped: paused by settings at x")
    card = _card(newdata.collect(NOW), "uw/spot_expiry_strike")
    assert card["status"] == "fresh" and card["last_note"].startswith("skipped: paused")


def test_a_built_dataset_keeps_its_status_after_many_skipped_checks():
    """Review should-fix 2: 25 ``skipped: paused`` rows after one good run (a Fetch every pass while paused) are
    more than the 20 newest the card lists; the status still comes from the good run, never "never built"."""
    _check(coverage=1.0, rows=7)
    for _ in range(25):
        _check(result="skipped", as_of=None, on="2026-10-28", note="skipped: paused by settings at x")
    card = _card(newdata.collect(NOW), "uw/spot_expiry_strike")
    assert card["status"] == "fresh", card["status_reason"]
    assert card["rows"] == 7 and card["last_note"].startswith("skipped: paused")


@pytest.mark.parametrize("cadence,age,want", [
    ("weekly", 8, "fresh"), ("weekly", 9, "late"), ("weekly", 16, "late"), ("weekly", 17, "stale"),
    ("monthly", 35, "fresh"), ("monthly", 36, "late"), ("monthly", 71, "stale"),
])
def test_weekly_and_monthly_boundaries(cadence, age, want):
    ops.schedule_set("market_series", cadence, None)
    on = (TODAY - timedelta(days=age)).isoformat()
    _check("market_series", as_of=on, on=on)
    assert _card(newdata.collect(NOW), "market_series")["status"] == want


def test_cards_come_worst_first():
    _check("uw/spot_expiry_strike", result="changed", coverage=1.0)
    _check("market_series", result="failed")
    order = [c["dataset"] for c in newdata.collect(NOW)["datasets"]]
    assert order.index("market_series") == 0                         # stale first
    assert order.index("uw/spot_expiry_strike") == len(order) - 1    # fresh last, after the never-built spine ones


# ── the checks inside the card ────────────────────────────────────────────────────────────────────────────────

def test_the_dataset_checks_are_listed_inside_its_card():
    _check(coverage=1.0, rows=10, added=2, removed=1, calls=1)
    ops.record_issue("uw/spot_expiry_strike", "fetch_failed", "2026-10-20", "HTTP 500")
    ops.record_issue("market_series", "no_rows", "x", "y")
    card = _card(newdata.collect(NOW), "uw/spot_expiry_strike")
    labels = {c["label"]: c for c in card["checks"]}
    assert labels["Last run"]["ok"] is True
    assert labels["Rows removed"]["ok"] is False and labels["Rows removed"]["detail"] == "1"
    assert labels["Open build issues"]["ok"] is False and labels["Open build issues"]["detail"] == "1"
    assert [i["kind"] for i in card["issues"]] == ["fetch_failed"]
    assert card["wrds"] == {"text": "no WRDS run yet", "produced": False}      # S8: the slot says it has not run


# ── backfill progress ─────────────────────────────────────────────────────────────────────────────────────────

def test_backfill_progress_from_the_parquet_folder(roots):
    for day in ("2025-01-16", "2025-01-17", "2026-10-28"):
        p = spx.partition_path(date.fromisoformat(day))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"PAR1")
    (spx.partition_path(date(2025, 1, 21)).parent).mkdir(parents=True)        # a folder without its part file
    bf = _card(newdata.collect(NOW), "uw/spot_expiry_strike")["backfill"]
    expected = sum(1 for _ in calendar_sessions(spx.FIRST_SESSION, TODAY))
    assert bf["done"] == 3 and bf["expected"] == expected
    assert bf["last_partition"] == "2026-10-28" and bf["resumable"] is True
    assert bf["missing"][0] == "2025-01-21" and len(bf["missing"]) == expected - 3
    # A session that fills UW's page of 500 is paged: the days a first backfill leaves missing are mostly those, two
    # calls each (21 Mar 2025: 575 rows; 15 Oct 2026: 683), so the estimate is two calls a session, not one.
    assert bf["calls_per_partition"] == spx.CALLS_PER_SESSION_ESTIMATE == 2


def calendar_sessions(start, end):
    from revenuechaser.rcdata.build import base
    return base.iter_sessions(start, end)


def test_the_market_series_backfill_counts_partitions_per_source(roots):
    from revenuechaser.rcdata.build import market_series as ms
    for src, year in ((ms.SOURCES[0], 2025), (ms.SOURCES[0], 2026), (ms.SOURCES[1], 2026)):
        p = ms.partition_path(src, year)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"PAR1")
    bf = _card(newdata.collect(NOW), "market_series")["backfill"]
    assert bf["done"] == 3 and bf["expected"] is None and bf["missing"] is None
    assert bf["last_partition"] == "2026"


# ── spend, backups, retention, retirement, watch lists, queue ─────────────────────────────────────────────────

def test_spend_is_today_and_this_week_per_provider_against_the_caps(monkeypatch):
    monkeypatch.setitem(caps.DAY_CAPS, "uw", 100_000)              # UW has no cap since 2026-11-10: a test cap
    ops.count_calls("uw", 1200)
    ops.put_rows("provider_calls_daily", [{"provider": p, "ny_day": d, "calls": n, "failures": 0, "http_429": 0}
                                          for p, d, n in (("uw", "2026-10-26", 300), ("uw", "2026-10-25", 999),
                                                          ("fred", "2026-10-27", 4))])
    ops.sample_uw_headers({"x-uw-daily-req-count": "1300", "x-uw-req-per-minute-remaining": "118",
                           "x-uw-token-req-limit": "100000000"})
    spend = newdata.collect(NOW)["spend"]
    uw = next(p for p in spend["providers"] if p["provider"] == "uw")
    assert (uw["today"], uw["week"], uw["cap"]) == (1200, 1500, caps.DAY_CAPS["uw"])     # the week starts Monday
    fred = next(p for p in spend["providers"] if p["provider"] == "fred")
    assert (fred["today"], fred["week"]) == (0, 4)
    assert {p["provider"] for p in spend["providers"]} >= set(caps.DAY_CAPS)
    uw_sample = spend["uw_remaining"]
    assert (uw_sample["daily_req_count"], uw_sample["daily_cap"]) == (1300, caps.DAY_CAPS["uw"])
    assert uw_sample["daily_remaining_computed"] == caps.DAY_CAPS["uw"] - 1300
    assert uw_sample["per_minute_remaining"] == 118


def test_money_is_the_paid_writers_spend_today_and_this_week_with_its_unit(monkeypatch):
    """#166 item 3: the data half of the money picture, for the v2 board to draw (the Spend card is unchanged)."""
    monkeypatch.delenv(llm_spend.ENV, raising=False)
    monkeypatch.delenv(llm_spend.CAP_ENV, raising=False)
    monkeypatch.delenv(llm_prices.PRICES_ENV, raising=False)
    ops.put_rows("provider_spend_daily", [
        {"provider": "deepseek", "model": "deepseek-v4-flash", "ny_day": "2026-10-28", "calls": 300,
         "tokens_in": 9000, "tokens_out": 3000, "usd_micros": 540_000},
        {"provider": "deepseek", "model": "deepseek-v4-flash", "ny_day": "2026-10-26", "calls": 100,
         "tokens_in": 1000, "tokens_out": 500, "usd_micros": 180_000},
        {"provider": "deepseek", "model": "deepseek-v4-flash", "ny_day": "2026-10-25", "calls": 999,
         "tokens_in": 0, "tokens_out": 0, "usd_micros": 9_000_000},        # the Sunday before: another week
    ])
    money = newdata.collect(NOW)["money"]
    assert (money["day"], money["week_from"]) == ("2026-10-28", "2026-10-26")
    row = money["writers"][0]
    assert (row["provider"], row["model"], row["unit"]) == ("deepseek", "deepseek-v4-flash",
                                                            "measured cost a call")
    assert (row["calls_today"], row["calls_week"]) == (300, 400)
    assert (row["usd_today"], row["usd_week"]) == (0.54, 0.72)
    assert (row["tokens_in_week"], row["tokens_out_week"]) == (10_000, 3_500)
    assert money["usd_today"] == 0.54                      # the day's own figure, summed from the day's rows
    assert money["day_cap_usd"] == llm_spend.DEFAULT_DAY_CAP_USD and money["recording"] is True
    # The page never has to work the rule out itself: it is told whether a paid call would be refused.
    assert money["over_cap"] is False


def test_money_says_so_when_the_day_cap_is_spent(monkeypatch):
    monkeypatch.delenv(llm_spend.ENV, raising=False)
    monkeypatch.setenv(llm_spend.CAP_ENV, "1")
    ops.put_rows("provider_spend_daily", [
        {"provider": "deepseek", "model": "deepseek-v4-flash", "ny_day": "2026-10-28", "calls": 600,
         "tokens_in": 0, "tokens_out": 0, "usd_micros": 1_080_000}])
    money = newdata.collect(NOW)["money"]
    assert money["usd_today"] == 1.08 and money["day_cap_usd"] == 1.0
    assert money["over_cap"] is True


def _manifest(roots, step: str, files: dict, **top):
    """A ``weekly-v2/<step>/.manifest.json`` as the weekly job writes it (``rcdata/backup.py``)."""
    out = roots / "backups" / "weekly-v2" / step
    out.mkdir(parents=True, exist_ok=True)
    (out / ".manifest.json").write_text(json.dumps({"version": 2, "files": files, **top}), encoding="utf-8")


def _iso(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat()


def test_the_backups_card_reads_every_step_of_the_weekly_job(roots):
    """avo, 8 Nov 2026: one weekly job, 4 copies kept. The card shows each step's last good run and the newest
    copy of every file; amber past 8 days (a missed Sunday), red past 15 (two)."""
    _manifest(roots, "duckdb", {"market_20261025_000000_000000.duckdb": {"at": _iso(3), "source": "weekly"},
                                "market_20261018_000000_000000.duckdb": {"at": _iso(10), "source": "weekly"},
                                "prices_20261027_000000_000000.duckdb": {"at": _iso(1), "source": "manual"}},
              last_ok=_iso(3), last_run=_iso(3))
    _manifest(roots, "boards", {"raw_20261025_000000_000000.duckdb": {"at": _iso(3), "store_schema": 41},
                                "sec_13f_20261025_000000_000000.duckdb": {"at": _iso(3)}},
              last_ok=_iso(3), last_run=_iso(3))
    _manifest(roots, "ops", {"ops_20261025_000000_000000.sqlite": {"at": _iso(3), "backend": "sqlite"}},
              last_ok=_iso(3), last_run=_iso(3))
    _manifest(roots, "uw-raw", {"2026-W43/uw/a.json.gz": {"sha256": "x"}}, weeks=["2026-W42", "2026-W43"],
              last_ok=_iso(10), last_run=_iso(3), last_error="uw: copy of a.json.gz does not match")
    _manifest(roots, "edgar-docs", {"edgar_docs_20261011_000000_000000.zip": {"at": _iso(17), "documents": 5}},
              last_ok=_iso(3), last_run=_iso(3))
    b = newdata.collect(NOW)["backups"]
    assert b["configured"] is True and b["root"].endswith("weekly-v2")
    assert (b["warn_days"], b["alert_days"]) == (newdata.BACKUP_WARN_DAYS, newdata.BACKUP_ALERT_DAYS) == (8, 15)
    steps = {s["step"]: s for s in b["steps"]}
    assert list(steps) == ["duckdb", "boards", "ops", "uw-raw", "edgar-docs", "watchlists-daily"]
    assert steps["duckdb"] == {"step": "duckdb", "last_ok": _iso(3), "age_days": 3, "warn": False, "alert": False,
                               "error": None}
    assert steps["uw-raw"]["age_days"] == 10 and steps["uw-raw"]["warn"] is True and steps["uw-raw"]["alert"] is False
    assert steps["uw-raw"]["error"].startswith("uw: copy of")
    kinds = {k["kind"]: k for k in b["kinds"]}
    assert kinds["market"] == {"kind": "market", "step": "duckdb", "newest": _iso(3), "age_days": 3, "copies": 2,
                               "warn": False, "alert": False}
    assert kinds["prices"]["newest"] is None and kinds["prices"]["copies"] == 0, "a manual copy is not a weekly one"
    assert kinds["raw"]["copies"] == 1 and kinds["sec_13f"]["step"] == "boards" and kinds["ops"]["age_days"] == 3
    assert kinds["uw-raw"] == {"kind": "uw-raw", "step": "uw-raw", "newest": _iso(10), "age_days": 10, "copies": 2,
                               "warn": True, "alert": False}
    # an unchanged edgar_docs tree keeps its zip: the step's last good run, not the zip's age, is what counts
    assert kinds["edgar_docs"]["age_days"] == 3 and kinds["edgar_docs"]["warn"] is False
    assert "raw_copy" not in b and "portable" not in b


def test_a_step_that_never_ran_and_a_kind_past_15_days_are_red(roots):
    _manifest(roots, "duckdb", {"market_20261001_000000_000000.duckdb": {"at": _iso(16), "source": "weekly"}},
              last_ok=_iso(16), last_run=_iso(16))
    b = newdata.collect(NOW)["backups"]
    steps = {s["step"]: s for s in b["steps"]}
    assert steps["duckdb"]["warn"] is True and steps["duckdb"]["alert"] is True
    assert steps["ops"] == {"step": "ops", "last_ok": None, "age_days": None, "warn": True, "alert": True,
                            "error": None}
    kinds = {k["kind"]: k for k in b["kinds"]}
    assert kinds["market"]["age_days"] == 16 and kinds["market"]["alert"] is True
    assert kinds["ops"]["newest"] is None and kinds["ops"]["alert"] is True


def test_the_daily_watchlists_row_is_red_past_two_days_whatever_the_copy_age(roots):
    """Decision C (avo, 17 Nov 2026): an unchanged day writes no copy, so the last good run is what counts."""
    _manifest(roots, "watchlists-daily", {"watchlists_20261101_000000_000000.duckdb": {"at": _iso(9),
                                                                                         "source": "daily"}},
              last_ok=_iso(1.9), last_run=_iso(1.9))
    b = newdata.collect(NOW)["backups"]
    assert b["daily_alert_days"] == newdata.BACKUP_DAILY_ALERT_DAYS == 2
    step = next(s for s in b["steps"] if s["step"] == "watchlists-daily")
    assert step["alert"] is False and step["last_ok"] == _iso(1.9)
    row = next(k for k in b["kinds"] if k["kind"] == "watchlists-daily")
    assert row["copies"] == 1 and row["alert"] is False
    _manifest(roots, "watchlists-daily", {}, last_ok=_iso(2.1), last_run=_iso(0.1), last_error="boom")
    b = newdata.collect(NOW)["backups"]
    step = next(s for s in b["steps"] if s["step"] == "watchlists-daily")
    assert step["alert"] is True and step["warn"] is True and step["error"] == "boom"


def test_the_backups_with_no_folder_say_so(monkeypatch):
    monkeypatch.setattr(config, "RAW_STORE_BACKUP_DIR", "")
    b = newdata.collect(NOW)["backups"]
    assert b["configured"] is False and b["root"] is None
    assert all(k["age_days"] is None and k["alert"] for k in b["kinds"])
    assert all(s["last_ok"] is None and s["alert"] for s in b["steps"])


def test_a_damaged_manifest_reads_as_never_backed_up(roots):
    out = roots / "backups" / "weekly-v2" / "ops"
    out.mkdir(parents=True)
    (out / ".manifest.json").write_text("{not json", encoding="utf-8")
    b = newdata.collect(NOW)["backups"]
    assert next(s for s in b["steps"] if s["step"] == "ops")["last_ok"] is None


def test_the_raw_retention_warning_is_on_until_a_retention_is_set(monkeypatch):
    r = newdata.collect(NOW)["retention"]
    assert r["warn"] is True and newdata.RETENTION_ENV in r["text"]
    monkeypatch.setenv(newdata.RETENTION_ENV, "400")
    r = newdata.collect(NOW)["retention"]
    assert r["warn"] is False and "400" in r["text"] and newdata.RETENTION_ENV in r["source"]
    monkeypatch.delenv(newdata.RETENTION_ENV)
    ops.schedule_set(newdata.RETENTION_ROW, "365", None)
    r = newdata.collect(NOW)["retention"]
    assert r["warn"] is False and "dataset_schedule" in r["source"]


def test_the_options_datasets_have_a_card_each_with_their_label_and_target():
    """G8: the options datasets are cards (never built yet: held until their first build by hand), and every
    options table is counted by its session date."""
    data = newdata.collect(NOW)
    for name, target in (("uw/option_list", 0.95), ("uw/option_screener", 0.95), ("uw/far_contracts", 0.95),
                         ("ibkr/iv_history", None)):
        card = _card(data, name)
        assert card["label"] == newdata.LABELS[name] and card["label"] != name
        assert card["status"] == "never" and card["coverage_target"] == target
    from revenuechaser.rcdata.build.options import tables
    assert all(newdata.DATE_COLUMN[t] == "session_date" for t in tables.TABLES)


def test_a_zero_retention_is_no_retention(monkeypatch):
    """Zero days would remove the session just fetched: the card keeps warning (the rule is rcdata.retention's)."""
    monkeypatch.setenv(newdata.RETENTION_ENV, "0")
    assert newdata.collect(NOW)["retention"]["warn"] is True




def test_watch_list_counts_schedule_state_and_the_queue():
    wl_store.job_set("option", "spy", True, by="t")
    wl_store.job_set("stock", "aapl", True, by="t")
    wl_store.job_set("stock", "msft", True, by="t")
    ops.schedule_pause("market_series", by="settings")
    rid = ops.enqueue("market_series", None, by="settings")
    data = newdata.collect(NOW)
    assert {k: v["count"] for k, v in data["watchlists"].items()} == {"option": 1, "stock": 2}
    assert [r["ticker"] for r in data["watchlists"]["stock"]["rows"]] == ["AAPL", "MSFT"]
    assert data["watchlists"]["option"]["rows"][0]["added_by"] == "t"
    assert data["watchlists"]["option"]["rows"][0]["added_on"].endswith("+00:00")
    assert data["options_build"] == {"always": ["SPX"], "queued": ["SPY"]}
    assert _card(data, "market_series")["schedule"]["paused"] is True
    assert _card(data, "market_series")["schedule"]["paused_by"] == "settings"
    assert _card(data, "uw/spot_expiry_strike")["schedule"]["paused"] is False
    assert [r["id"] for r in data["queue"]["active"]] == [rid]


# ── the read-only, per-call handles ───────────────────────────────────────────────────────────────────────────

def _serving_file(rows: int, session: str = "2026-10-28", built_at: float = 1_700_000_000.0) -> None:
    path = serving.live_path("market")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("market.fixture.duckdb")
    con = duckdb.connect(str(tmp))
    try:
        con.execute("CREATE TABLE serving_schema_version (kind TEXT, version INTEGER, built_at DOUBLE, build_id TEXT)")
        con.execute("INSERT INTO serving_schema_version VALUES ('market', 1, ?, 'b')", [built_at])
        con.execute("CREATE TABLE spx_gamma_expiry_strike (session_date DATE)")
        con.execute(f"INSERT INTO spx_gamma_expiry_strike SELECT DATE '{session}' FROM range({rows})")
        con.execute("CREATE TABLE market_series (obs_date DATE)")
        con.execute("INSERT INTO market_series VALUES (DATE '2026-10-27')")
    finally:
        con.close()
    os.replace(tmp, path)


@pytest.fixture
def handles(monkeypatch):
    """Counts the handles ``newdata`` opens on a serving file and the ones it closed."""
    seen = {"opened": 0, "closed": 0}
    real = serving.open_read

    class Counted:
        def __init__(self, con):
            self._con = con

        def execute(self, *a, **k):
            return self._con.execute(*a, **k)

        def close(self):
            seen["closed"] += 1
            self._con.close()

    def counted(kind):
        con = real(kind)
        seen["opened"] += 1
        return Counted(con)
    monkeypatch.setattr(serving, "open_read", counted)
    return seen


def test_rows_and_the_newest_date_come_from_one_read_only_handle_closed_before_return(handles):
    _serving_file(3)
    data = newdata.collect(NOW)
    assert handles == {"opened": 1, "closed": 1}
    card = _card(data, "uw/spot_expiry_strike")
    assert card["table_rows"] == 3 and card["newest"] == "2026-10-28"
    assert _card(data, "market_series")["newest"] == "2026-10-27"
    assert data["verified"]["swaps"]["market"].startswith("2023-11-14")


def test_every_call_opens_its_own_handle_and_sees_a_swapped_file(handles):
    _serving_file(3)
    assert _card(newdata.collect(NOW), "uw/spot_expiry_strike")["table_rows"] == 3
    _serving_file(5)                                     # a swap between two requests
    assert _card(newdata.collect(NOW), "uw/spot_expiry_strike")["table_rows"] == 5
    assert handles == {"opened": 2, "closed": 2}


def test_no_serving_file_yet_is_no_rows_not_an_error(handles):
    card = _card(newdata.collect(NOW), "uw/spot_expiry_strike")
    assert card["table_rows"] is None and handles["opened"] == 0
    # Every serving kind, each without a swap yet (the kinds come from rcdata, so a new one needs no edit here).
    assert newdata.collect(NOW)["verified"]["swaps"] == {kind: None for kind in serving.KINDS}
    assert {"market", "spine", "options"} <= set(serving.KINDS)


def test_the_collect_never_creates_ops_sqlite_or_a_serving_file():
    newdata.collect(NOW)
    assert not ops.ops_path().exists() and not serving.live_path("market").exists()


def test_the_verified_running_line(roots):
    ops.start_run("r1", "market_series", "queue")
    ops.finish_run("r1", "ok")
    v = newdata.collect(NOW)["verified"]
    assert v["builder_last_run"]["run_id"] == "r1" and v["builder_last_run"]["status"] == "ok"
    assert v["ops_schema"] == ops.OPS_SCHEMA_VERSION


def test_an_ops_file_from_before_a_table_existed_reads_as_empty(sqlite_ops, roots):
    path = ops.ops_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(str(path)).close()                    # an empty file: no tables at all
    data = newdata.collect(NOW)
    assert data["queue"] == {"active": [], "finished": []} and data["verified"]["ops_schema"] is None
