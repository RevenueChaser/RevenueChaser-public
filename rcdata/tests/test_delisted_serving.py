"""The delisted serving layer (#1219; avo, 20 Nov 2026: "Delistedler icin ayri katman.").

The fixture is ``test_prices_wrds``' (a fake WRDS worker, never WRDS), with three delisted PERMNOs added to CRSP's
``dsf_v2`` and its ``stkdelists`` snapshot:

| PERMNO | Case |
|---|---|
| 99001 | the plain dead name: 4 sessions in 2024, a 2-for-1 split and a 0.50 dividend CRSP's own columns carry, its CUSIP is OLDCO's in ``comp.secd`` (so it links to ``099999:01``), and its ticker goes OLDA -> OLDB -> OLDA |
| 99002 | no Compustat CUSIP at all (no ``gvkey``), and it traded under **OLDA too**, in 2025: the ticker-reuse case |
| 99003 | a dead class whose CUSIP is Apple's, so it links to ``001690:01`` and takes that issuer's CIK from the live spine |

AAPL's own PERMNO (14593) has no delisting row, so it is the control: alive names must not be in this file.
"""
from __future__ import annotations

from datetime import date

import pytest

from RevenueChaser.rcdata import read, serving, serving_versions
from RevenueChaser.rcdata.build import DATASETS, base
from RevenueChaser.rcdata.build.delisted import serving as delisted
from RevenueChaser.rcdata.build.prices import serving as prices_serving, wrds_history
from RevenueChaser.rcdata.build.spine import wrds

from .test_prices_wrds import AAPL, FakeWrds, _data, env  # noqa: F401 - env is the autouse world

DEAD, GHOST, CLASS = "permno:99001", "permno:99002", "permno:99003"
MARCH = ["2024-03-01", "2024-03-04", "2024-03-05", "2024-03-06"]
DEAD_CLOSE = [10.0, 5.2, 5.0, 4.8]
#: 99001's cumulative price factor: 2.0 before the 2-for-1 of 4 Mar, 1.0 from it on (CRSP's direction, the older
#: days' factor the larger: checked on WRDS for AAPL's 2020 split, ``wrds_history``'s CRSP section).
DEAD_FACPR = [2.0, 1.0, 1.0, 1.0]
DEAD_TICKER = ["OLDA", "OLDB", "OLDA", "OLDA"]
DEAD_DIV = [0.0, 0.0, 0.50, 0.0]


def _dsf(permno, day, close, ticker, cusip, facpr=1.0, div=0.0, shrout=1_000.0):
    return {"permno": permno, "dlycaldt": day, "dlyprc": close, "dlyopen": close, "dlyhigh": close * 1.01,
            "dlylow": close * 0.99, "dlyvol": 50_000, "dlyret": None, "shrout": shrout, "hdrcusip": cusip,
            "cusip": cusip, "ticker": ticker, "dlycumfacpr": facpr, "dlycumfacshr": facpr, "dlyorddivamt": div}


def _world_data():
    data = _data()
    data["crsp.dsf_v2"] = [
        *data["crsp.dsf_v2"],
        *[_dsf("99001", d, c, t, "68000010", f, v)
          for d, c, t, f, v in zip(MARCH, DEAD_CLOSE, DEAD_TICKER, DEAD_FACPR, DEAD_DIV)],
        # A negative price is CRSP's bid/ask midpoint, served ``abs``.
        _dsf("99002", "2025-02-03", -1.25, "OLDA", "99999999"),
        _dsf("99002", "2025-02-04", 1.10, "OLDA", "99999999"),
        _dsf("99003", "2024-05-01", 3.0, "AAPLD", "03783310"),
    ]
    data["crsp_a_stock.stkdelists"] = [
        {"permno": "99001", "delistingdt": "2024-03-07", "deldtprc": 2.5, "delret": -0.42},
        {"permno": "99002", "delistingdt": "2025-02-05", "deldtprc": 0.1, "delret": -0.9},
        {"permno": "99003", "delistingdt": "2024-05-02", "deldtprc": 1.0, "delret": -0.6},
        # A PERMNO with no delisting day is not a delisted security, whatever else the row says.
        {"permno": "14593", "delistingdt": None, "deldtprc": None, "delret": None},
    ]
    # ``comp.secd`` already holds OLDCO (``099999:01``, CUSIP 680000101), the Compustat name the spine does not
    # hold: that is the CUSIP 99001's header CUSIP links to, so nothing is added here.
    return data


def _build_delisted(**params):
    return base.run_request({"dataset": delisted.NAME, "requested_by": "cli",
                             "params": {"as_of": "2026-10-27", **params}})


@pytest.fixture
def world(monkeypatch):
    """The WRDS Parquet on disk (one attended backfill of ``wrds/prices``), then the delisted build over it."""
    conn = FakeWrds(_world_data())
    monkeypatch.setattr(wrds, "_factory", lambda: conn)
    wrds.reset()
    row = base.run_request({"dataset": wrds_history.NAME, "requested_by": "cli",
                            "params": {"mode": "backfill", "to": "2026-10-27"}})
    assert row["result"] == "changed", row
    built = _build_delisted()
    assert built["result"] != "failed", built
    yield built
    wrds.reset()


def _q(sql: str, params=()):
    with serving.open_read("delisted") as con:
        cur = con.execute(sql, list(params))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _prices(sql: str, params=()):
    with serving.open_read("prices") as con:
        cur = con.execute(sql, list(params))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# ── The kind itself ───────────────────────────────────────────────────────────────────────────────────────────

def test_the_delisted_history_is_its_own_serving_kind_and_file():
    """A file of its own, so a bad delisted build cannot touch live prices (#1219)."""
    assert "delisted" in serving.KINDS and serving.SERVING_SCHEMA_VERSION["delisted"] == 1
    assert serving.live_path("delisted").name == "delisted.duckdb"
    assert serving.live_path("delisted") != serving.live_path("prices")
    assert DATASETS[delisted.NAME] is delisted.DATASET and delisted.DATASET.kind == "delisted"


def test_it_is_append_only_so_every_shrink_refuses_the_swap():
    """The history only grows: a smaller table is a build from a partial Parquet tree, never a choice (#1219)."""
    assert not set(delisted.TABLES) & set(serving_versions.SHRINKS_BY_CHOICE)
    assert "delisted" not in serving.RETIRED_TABLES


def test_it_fetches_nothing_and_is_run_by_hand_with_the_monthly_wrds_run():
    ds = delisted.DATASET
    assert ds.providers == () and ds.fetch(None, date(2026, 10, 27)) == []
    assert base.attended(ds) and delisted.NAME in base.attended_names()
    assert ds.cadence == "monthly" and ds.parquet_reads == ("wrds/prices",)
    assert ds.feeds == ()


def test_the_bars_and_actions_carry_exactly_the_live_tables_columns():
    """A reader unions the two deliberately, so the shapes must match the live ones column for column (#1219)."""
    assert delisted.SCHEMAS[delisted.BAR] == list(prices_serving.PRICE_BAR)
    assert delisted.SCHEMAS[delisted.ACTION] == list(prices_serving.CORPORATE_ACTION)


# ── What is served ────────────────────────────────────────────────────────────────────────────────────────────

def test_a_delisted_names_bars_are_here_and_not_in_the_prices_store(world):
    bars = _q(f"SELECT * FROM {delisted.BAR} WHERE security_id = ? ORDER BY session_date", [DEAD])
    assert [str(b["session_date"]) for b in bars] == MARCH
    assert [b["close"] for b in bars] == DEAD_CLOSE
    assert {b["source"] for b in bars} == {wrds_history.CRSP}
    assert bars[0]["shares_outstanding"] == 1_000 * wrds_history.CRSP_SHARES_UNIT
    assert bars[0]["cik"] is None and bars[0]["vwap"] is None
    # The live store is untouched: nothing delisted entered it, and no delisted table was created in it.
    assert _prices("SELECT count(*) AS n FROM price_bar_daily WHERE security_id LIKE 'permno:%'")[0]["n"] == 0
    assert _prices("SELECT count(*) AS n FROM duckdb_tables() WHERE table_name LIKE 'delisted%'")[0]["n"] == 0


def test_a_negative_crsp_price_is_served_as_its_absolute_midpoint(world):
    bars = _q(f"SELECT session_date, close FROM {delisted.BAR} WHERE security_id = ? ORDER BY session_date", [GHOST])
    assert [(str(b["session_date"]), b["close"]) for b in bars] == [("2025-02-03", 1.25), ("2025-02-04", 1.10)]


def test_an_alive_permno_is_not_a_delisted_security(world):
    """A ``stkdelists`` row with no delisting day is not a delisting, and AAPL stays out of this file."""
    assert _q(f"SELECT count(*) AS n FROM {delisted.SECURITY} WHERE permno = '14593'")[0]["n"] == 0
    assert _q(f"SELECT count(*) AS n FROM {delisted.BAR} WHERE security_id = 'permno:14593'")[0]["n"] == 0
    assert _prices("SELECT count(*) AS n FROM price_bar_daily WHERE security_id = ?", [AAPL])[0]["n"] > 0


def test_every_row_is_keyed_on_the_permno_never_on_a_ticker(world):
    for table in delisted.TABLES:
        ids = {r["security_id"] for r in _q(f"SELECT DISTINCT security_id FROM {table}")}
        assert ids and all(i.startswith("permno:") for i in ids), (table, ids)


def test_the_security_row_carries_the_delisting_the_link_and_the_span(world):
    row = _q(f"SELECT * FROM {delisted.SECURITY} WHERE security_id = ?", [DEAD])[0]
    assert str(row["delisting_date"]) == "2024-03-07"
    assert (row["delisting_price"], row["delisting_return"]) == (2.5, -0.42)
    assert (row["gvkey"], row["iid"], row["link"]) == ("099999", "01", "hdrcusip")
    assert row["cusip"] == "68000010" and row["last_symbol"] == "OLDA"
    assert (str(row["first_session"]), str(row["last_session"]), row["sessions"]) == (MARCH[0], MARCH[-1], 4)


def test_a_permno_with_no_compustat_cusip_has_no_gvkey_and_says_so(world):
    row = _q(f"SELECT * FROM {delisted.SECURITY} WHERE security_id = ?", [GHOST])[0]
    assert row["gvkey"] is None and row["iid"] is None and row["link"] is None and row["cik"] is None
    assert str(row["delisting_date"]) == "2025-02-05"


def test_a_linked_dead_class_takes_its_issuers_cik_from_the_live_spine(world):
    row = _q(f"SELECT * FROM {delisted.SECURITY} WHERE security_id = ?", [CLASS])[0]
    assert (row["gvkey"], row["iid"]) == ("001690", "01") and row["cik"] == "320193"


# ── Ticker reuse: the rule no reader may join around ──────────────────────────────────────────────────────────

def test_a_ticker_a_security_held_twice_is_two_dated_rows(world):
    rows = _q(f"SELECT symbol, valid_from, valid_to, sessions FROM {delisted.SYMBOL} WHERE security_id = ? "
              "ORDER BY valid_from", [DEAD])
    assert [(r["symbol"], str(r["valid_from"]), str(r["valid_to"])) for r in rows] == [
        ("OLDA", "2024-03-01", "2024-03-01"), ("OLDB", "2024-03-04", "2024-03-04"),
        ("OLDA", "2024-03-05", "2024-03-06")]
    assert [r["sessions"] for r in rows] == [1, 1, 2]


def test_one_ticker_two_dead_companies_stay_two_securities(world):
    """A dead company's ticker and another's are two securities, so OLDA resolves only with a day."""
    rows = _q(f"SELECT security_id, valid_from, valid_to FROM {delisted.SYMBOL} WHERE symbol = 'OLDA' "
              "ORDER BY valid_from")
    assert {r["security_id"] for r in rows} == {DEAD, GHOST}
    on_2025 = [r for r in rows if str(r["valid_from"]) <= "2025-02-03" <= str(r["valid_to"])]
    assert [r["security_id"] for r in on_2025] == [GHOST]


# ── The actions a dead name's returns need ────────────────────────────────────────────────────────────────────

def test_the_split_crsps_price_factor_records_is_served(world):
    rows = _q(f"SELECT * FROM {delisted.ACTION} WHERE security_id = ? AND action = 'split'", [DEAD])
    assert len(rows) == 1
    assert str(rows[0]["ex_date"]) == "2024-03-04" and rows[0]["ratio"] == pytest.approx(2.0)
    assert rows[0]["action_type"] == "forward_split" and rows[0]["applied"] is True
    assert rows[0]["source_id"] == "crspsplit:99001:2024-03-04" and rows[0]["source"] == wrds_history.CRSP


def test_the_ordinary_cash_dividend_is_served(world):
    rows = _q(f"SELECT * FROM {delisted.ACTION} WHERE security_id = ? AND action = 'cash_dividend'", [DEAD])
    assert [(str(r["ex_date"]), r["amount"], r["currency"]) for r in rows] == [("2024-03-05", 0.50, "USD")]
    assert rows[0]["source_id"] == "crspdiv:99001:2024-03-05"


def test_a_name_with_no_factor_change_has_no_action(world):
    assert _q(f"SELECT count(*) AS n FROM {delisted.ACTION} WHERE security_id = ?", [GHOST])[0]["n"] == 0


# ── The start day, and the refusals ───────────────────────────────────────────────────────────────────────────

def test_the_history_starts_at_one_constant_avo_can_change(monkeypatch, world):
    """``HISTORY_FROM`` is the fetch's own start by default, and the build reads it at call time, so the number is
    one line and not a date baked into every query."""
    assert delisted.HISTORY_FROM == wrds_history.COMPUSTAT_START == date(1983, 12, 30)
    monkeypatch.setattr(delisted, "HISTORY_FROM", date(2025, 1, 1))
    # A narrowed window drops rows, which is a shrink the guard refuses unless the request says so: that is the
    # point of the guard, so the test asks for it explicitly rather than widening the rule.
    assert _build_delisted(allow_shrink=True)["result"] != "failed"
    assert _q(f"SELECT count(*) AS n FROM {delisted.BAR} WHERE security_id = ?", [DEAD])[0]["n"] == 0
    assert _q(f"SELECT count(*) AS n FROM {delisted.BAR} WHERE security_id = ?", [GHOST])[0]["n"] == 2
    # The security still has its delisting row: who delisted does not depend on the window.
    assert _q(f"SELECT sessions FROM {delisted.SECURITY} WHERE security_id = ?", [DEAD])[0]["sessions"] == 0


def test_a_repeated_key_fails_the_build_instead_of_being_served():
    """No ``PRIMARY KEY`` is written (the bars are a row per security and session), so the key is checked by query."""
    import duckdb
    con = duckdb.connect()
    cols = ", ".join(f'"{c}" {t}' for c, t in delisted.SCHEMAS[delisted.BAR])
    con.execute(f"CREATE TABLE {delisted.BAR} ({cols})")
    con.execute(f"INSERT INTO {delisted.BAR} (security_id, session_date) VALUES (?, DATE '2024-03-01'), "
                "(?, DATE '2024-03-01')", [DEAD, DEAD])
    assert delisted.duplicate_keys(con, delisted.BAR) == [(DEAD, date(2024, 3, 1), 2)]
    with pytest.raises(base.SourceError, match="repeated key"):
        delisted._refuse_duplicates(con, delisted.BAR)


# ── How it is read ────────────────────────────────────────────────────────────────────────────────────────────

def test_the_readers_answer_from_the_delisted_file(world):
    assert read.KIND_OF_TABLE[delisted.BAR] == "delisted"
    assert read.DATASET_OF_TABLE[delisted.SECURITY] == delisted.NAME
    bars = read.delisted_bars([DEAD], start="2024-03-04")
    assert [str(b["session_date"]) for b in bars] == MARCH[1:]
    assert read.delisted_bars([]) == []
    names = read.delisted_securities([DEAD, GHOST])
    assert [n["security_id"] for n in names] == [DEAD, GHOST]
    assert [n["security_id"] for n in read.delisted_securities(delisted_from="2025-01-01")] == [GHOST]
    assert {s["security_id"] for s in read.delisted_symbols(symbols=["OLDA"])} == {DEAD, GHOST}
    assert [a["action"] for a in read.delisted_actions([DEAD])] == ["split", "cash_dividend"]


def test_the_needs_layer_serves_it_and_never_calls_it_stale(world):
    from RevenueChaser.rcdata import needs
    from RevenueChaser.rcdata.needs import catalog
    for name in ("market.delisted_security", "market.delisted_price_bar"):
        need = catalog.NEEDS[name]
        assert need.kind == "delisted" and need.dataset == delisted.NAME
        # A history that is behind on purpose has no day of its own: present or absent, never stale.
        assert need.day_column is None
    answer = needs.ask("market.delisted_price_bar", security_ids=[DEAD])
    assert answer.fill is None and [str(r["session_date"]) for r in answer.rows] == MARCH
    assert needs.ask("market.delisted_security").state != "stale"
