"""The world ``prices``'s incremental tests are read in: the live copy, a whole build beside it, and the comparison.

Split out of ``test_prices_incremental.py`` (#1153), whose 30 tests measured 338 s in one file -- above a shard's
per-worker share, and ``pytest --dist loadfile`` gives a whole file to one worker, so that file alone set how short
the unit tier could run. The tests are now two files over this world:

- ``test_prices_incremental.py``: the metamorphic proof itself, over the ``live`` fixture.
- ``test_prices_incremental_classes.py``: the share classes, the aliases, the forced whole builds and the splits.

``test_prices_chunked.py`` reads this module too (it drives the same world a chunk at a time). Nothing here is a
test; pytest reads it only through those files.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core import calendar
from RevenueChaser.rcdata import ops, serving
from RevenueChaser.rcdata.build import base, dirty
from RevenueChaser.rcdata.build.prices import incremental, stage, wrds_history
from RevenueChaser.rcdata.build.prices import serving as prices_serving

from .prices_fixture import SPINE, write_spine
from .test_prices_wrds import AAPL, OLDCO, _build, _q, env, fake  # noqa: F401 (re-exported to the test files)


SCHEMA = wrds_history.SECD + wrds_history.PROVENANCE


VIEW_BUILD_COLUMNS = ("fetched_at", "run_at")          # a view's build time, not data


def _clock(day: date) -> None:
    calendar._now = lambda: datetime(day.year, day.month, day.day, 21, 0, tzinfo=timezone.utc)


def _serve() -> dict:
    row = base.run_request({"dataset": prices_serving.NAME, "params": {}})
    assert row["result"] != "failed", row
    return row


def _note(row: dict) -> str:
    return row.get("note") or ""


def _secd_rows(year: int) -> list[dict]:
    return stage.read_rows(wrds_history.partition_path("secd", year))


def _write_secd(year: int, rows: list[dict]) -> None:
    stage.write_rows(rows, SCHEMA, wrds_history.partition_path("secd", year), order="gvkey, iid, datadate")


def _aapl_day(day: date, close: float, **extra) -> dict:
    last = [r for r in _secd_rows(2026) if r["gvkey"] == "001690"][-1]
    return {**last, "datadate": day, "prccd": close, "prcod": close, "prchd": close * 1.01, "prcld": close * 0.99,
            "source_as_of": day, "run_id": last["run_id"], **extra}


def _respine(rows: list[dict]) -> None:
    serving.live_path("spine").unlink()
    write_spine(rows)


def _snapshot() -> dict[str, list]:
    out = {}
    with serving.open_read("prices") as con:
        for name in (*prices_serving.TABLES, *prices_serving.VIEWS):
            if name in incremental.KEPT:
                continue
            cols = [r[0] for r in con.execute(f"DESCRIBE {name}").fetchall()
                    if not (name in prices_serving.VIEWS and r[0] in VIEW_BUILD_COLUMNS)]
            rows = con.execute(f"SELECT {', '.join(chr(34) + c + chr(34) for c in cols)} FROM {name}").fetchall()
            out[name] = sorted(rows, key=repr)
    out["open issues"] = sorted((r["kind"], r["key"]) for r in _open_issues())
    return out


def _open_issues() -> list[dict]:
    # Through ``ops``, so it reads whichever backend holds the issues (Redis on the server, review B1 of #564).
    return [{"kind": r["kind"], "key": r["key"]} for r in ops.open_issues(prices_serving.NAME, 1_000_000)[1]]


def _report() -> list:
    return sorted(tuple(r.values()) for r in _q("SELECT * FROM wrds_price_diff"))


def _same_as_whole(monkeypatch, row: dict) -> dict[str, list]:
    """The live file was just built on the live copy: it serves what a whole build of the same tree serves."""
    assert "built on the live file" in _note(row), _note(row)
    got = _snapshot()
    monkeypatch.setenv(dirty.WHOLE_ENV, "1")
    whole = _serve()
    monkeypatch.delenv(dirty.WHOLE_ENV)
    assert "built whole" in _note(whole), _note(whole)
    want = _snapshot()
    for name in want:
        if got[name] != want[name]:
            print("DIFF", name, "\n inc-only", sorted(set(got[name]) - set(want[name]), key=repr)[:20],
                  "\n whole-only", sorted(set(want[name]) - set(got[name]), key=repr)[:20], "\nNOTE", _note(row))
        assert got[name] == want[name], name
    return want


OLD = [date(2015, 3, 2), date(2015, 3, 3), date(2015, 3, 4), date(2015, 3, 5)]


def _old_history() -> None:
    """AAPL in 2015, a year partition no later change touches: a build on the live copy stages none of it, so it
    must keep these rows (and the dividend and caps on them) exactly as the whole build made them."""
    template = [r for r in _secd_rows(2025) if r["gvkey"] == "001690"][0]
    rows = [{**template, "datadate": d, "prccd": c, "prcod": c, "prchd": c, "prcld": c, "ajexdi": 4.0,
             "trfd": 1.0 + 0.001 * i, "cshoc": 5.8e9, "divd": 0.47 if i == 2 else None, "div": None, "divsp": None,
             "source_as_of": date(2015, 3, 31), "run_id": "old"}
            for i, (d, c) in enumerate(zip(OLD, (128.0, 129.0, 127.5, 126.4)))]
    _write_secd(2015, rows)


@pytest.fixture
def live(fake, monkeypatch):
    """A whole build with an old year, then one on the live copy that changes nothing (the manifest)."""
    _build()
    _old_history()
    monkeypatch.setenv(dirty.WHOLE_ENV, "1")
    _serve()
    monkeypatch.delenv(dirty.WHOLE_ENV)
    assert len(_q("SELECT 1 FROM price_bar_daily WHERE session_date < '2016-01-01'")) == 4
    row = _serve()
    assert "built on the live file" in _note(row), _note(row)
    return fake


GOOGL, GOOG = "160329:01", "160329:03"


OCT = [date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23), date(2026, 10, 26), date(2026, 10, 27)]


@pytest.fixture
def alphabet(live, monkeypatch):
    from .prices_fixture import ALPHABET
    template = [r for r in _secd_rows(2026) if r["gvkey"] == "001690"][0]
    extra = [{**template, "gvkey": "160329", "iid": iid, "tic": tic, "cusip": None, "datadate": d,
              "prccd": c + i, "prcod": c + i, "prchd": c + i, "prcld": c + i, "cshoc": shares, "divd": None,
              "div": None, "divsp": None, "ajexdi": 1.0, "trfd": 1.0}
             for iid, tic, c, shares in (("01", "GOOGL", 170.0, 5.8e9), ("03", "GOOG", 171.0, 5.45e9))
             for i, d in enumerate(OCT) if iid == "01" or d <= OCT[2]]      # GOOG's last bar: the 23rd
    _write_secd(2026, _secd_rows(2026) + extra)
    _respine(SPINE + ALPHABET)
    monkeypatch.setenv(dirty.WHOLE_ENV, "1")
    _serve()
    monkeypatch.delenv(dirty.WHOLE_ENV)
    assert _serve()["result"] != "failed"
    caps = _q("SELECT market_cap, issuer_market_cap FROM market_cap_daily WHERE security_id = ? "
              "AND session_date = ?", [GOOGL, OCT[-1]])
    assert caps and caps[0]["issuer_market_cap"] > caps[0]["market_cap"]          # GOOG's cap of the 23rd in it
    return live


FIGI = "figi:BBG000BDTBL9"


SPY_DAYS = ["2025-06-02", "2025-06-03", "2025-06-04", "2025-06-05", "2025-06-06", "2026-10-26", "2026-10-27"]


def _spy_spine(inception, extra=()) -> None:
    """SPY without its own gvkey in the spine, so its Compustat series is a ticker pick until CRSP links it."""
    import duckdb
    rows = [{**r, "gvkey": None, "iid": None} if r["ticker"] == "SPY" else r for r in SPINE] + list(extra)
    p = serving.live_path("spine")
    if p.exists():
        p.unlink()
    write_spine(rows)
    con = duckdb.connect(str(p))
    try:
        con.execute("CREATE TABLE etf (ticker TEXT, aum DOUBLE, is_etn BOOLEAN, is_cef BOOLEAN, inception DATE)")
        con.execute("INSERT INTO etf VALUES ('SPY', 5e11, false, false, ?)", [inception])
    finally:
        con.close()


def _spy(fake, monkeypatch, extra=()) -> None:
    from .test_prices_wrds import _secd
    conn = fake[0]
    conn.data["comp.secd"] = conn.data["comp.secd"] + [
        _secd("001000", "01", d, "SPY", 500.0 + i, cusip="78462F103", exchg=17) for i, d in enumerate(SPY_DAYS)]
    conn.data["crsp.dsf_v2"] = conn.data["crsp.dsf_v2"] + [
        {"permno": "84398", "dlycaldt": d, "dlyprc": 500.0 + i, "dlyopen": 500.0, "dlyhigh": 501.0, "dlylow": 499.0,
         "dlyvol": 1e6, "dlyret": 0.001, "shrout": 900000, "hdrcusip": "78462F10", "cusip": "78462F10",
         "ticker": "SPY", "dlycumfacpr": 1.0, "dlycumfacshr": 1.0, "dlyorddivamt": 0.0}
        for i, d in enumerate(SPY_DAYS[:5])]
    _spy_spine(None, extra)
    _build()
    _spy_spine(None, extra)
    monkeypatch.setenv(dirty.WHOLE_ENV, "1")
    _serve()
    monkeypatch.delenv(dirty.WHOLE_ENV)
    _serve()


SPYX = {"ticker": "SPYX", "cik": "7777777", "name": "x", "exchange": "NYSE", "tier": "C", "security_type": "etf",
        "gvkey": "001000", "iid": "02", "composite_figi": None}
