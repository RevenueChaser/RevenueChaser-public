"""#446 step 8B: ``rcdata.build.state`` says what the last build of a kind did, read from the live file.

The proof is a real build. ``market`` is the kind used here, as in ``test_market_incremental.py``: a whole build
first (nothing to copy from), then a second build that starts on the live copy, and the reader's answer has to
follow the file both times. The reader is then checked for the three things it must not do -- raise on a missing
file, read a missing table as zero, or open a file for writing.
"""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from RevenueChaser.rcdata import serving
from RevenueChaser.rcdata.build import audit, base, dirty, market_series as ms
from RevenueChaser.rcdata.build import uw_greek_expiry_strike as greek, uw_spot_expiry_strike as spot
from RevenueChaser.rcdata.build import state
from RevenueChaser.rcdata.build.sources import fred, treasury

MEMBERS = (ms.DATASET, spot.DATASET, greek.DATASET)
D1, D2, D3 = date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28)


def _uw(mod, day: date, value: float = 1.0) -> None:
    rows = [{"session_date": day, "expiry": date(2026, 11, 20), "strike": 7000.0 + 100 * k, "dte": 18,
             "source": "uw", "source_as_of": day, "fetched_at": 1.0, "run_id": "r",
             **{f: value * (k + 1) for f in mod.NUMERIC_FIELDS if f != "price"}} for k in range(3)]
    base.upsert_partition(rows, mod.SCHEMA, list(mod.KEY), mod.partition_path(day))


def _series(src, series_id: str, year: int, value: float) -> None:
    rows = [{"series_id": series_id, "obs_date": date(year, 3, d), "source": src.SOURCE, "value": value + d,
             "frequency": "daily", "source_as_of": date(year, 3, 31), "fetched_at": 1.0, "run_id": "r"}
            for d in (2, 3, 4)]
    base.upsert_partition(rows, ms.SCHEMA, ms.KEY, ms.partition_path(src, year))


@pytest.fixture
def seeded():
    base.parquet_root().mkdir(parents=True, exist_ok=True)
    for mod in (spot, greek):
        _uw(mod, D1)
        _uw(mod, D2)
    _series(treasury, "DGS10_T", 2025, 4.0)
    _series(fred, "DGS10", 2025, 4.1)
    for year in range(2020, 2025):              # enough untouched files to stay under dirty.MAX_DIRTY_SHARE
        _series(fred, "DGS10", year, 3.0)
    return None


def _build() -> None:
    ctxs = [(d, base.RunContext(run_id=f"t-{d.name}", dataset=d.name, as_of=D3, allow_shrink=True))
            for d in MEMBERS]
    base.build_kind_many("market", ctxs, lead=ctxs[0][1])


def test_nothing_built_yet_is_a_row_not_a_failure():
    """A kind with no live file still says how it would be built, so the board lists every kind from day one."""
    row = state.of("market")
    assert row["built"] is False
    assert row["kind"] == "market" and row["datasets"]
    assert row["incremental"] is True                   # market's datasets declare ``dirty``
    assert "error" not in row


def test_the_first_build_is_whole_and_the_second_one_is_on_the_live_copy(seeded):
    _build()
    first = state.of("market")
    assert first["built"] is True
    assert first["mode"] == "fresh"                     # there was no live file to copy
    assert first["built_at"] and first["build_id"]
    assert first["parquet_files"] == len(dirty.scan(MEMBERS))

    _series(fred, "DGS10", 2026, 4.2)                   # one new partition
    _build()
    second = state.of("market")
    assert second["mode"] == "live"
    assert second["build_id"] != first["build_id"]
    assert second["built_at"] >= first["built_at"]
    assert second["parquet_files"] == first["parquet_files"] + 1


def test_a_table_the_file_does_not_carry_is_empty_and_never_zero(seeded):
    """An audit that has never run and an audit that found nothing are different answers (the board draws the
    first as an empty cell), so the reader must not fold one into the other."""
    _build()
    with serving.open_read("market") as con:
        has_rounds = con.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", (audit.ROUNDS,)).fetchone()[0]
    row = state.of("market")
    if has_rounds:
        assert row["audit_dirty"] == 0 and row["audit"]["checked_at"] is None
    else:
        assert row["audit_dirty"] is None and row["audit"] == {}


def test_the_last_audit_round_is_counted_per_pass(seeded, monkeypatch):
    """Two keys checked in one pass and one of them differing is one round: 2 checked, 1 differs. The pass before
    it is not counted with it, which is what makes the number readable as "the last round"."""
    _build()
    path = serving.live_path("market")
    with duckdb.connect(str(path)) as con:
        audit.ensure_tables(con)
        con.execute(f'INSERT INTO {audit.ROUNDS} VALUES (?, ?, ?, ?)', (ms.TABLE, "old", 100.0, "ok"))
        con.execute(f'INSERT INTO {audit.ROUNDS} VALUES (?, ?, ?, ?)', (ms.TABLE, "a", 200.0, "ok"))
        con.execute(f'INSERT INTO {audit.ROUNDS} VALUES (?, ?, ?, ?)', (ms.TABLE, "b", 200.0, "differs"))
        con.execute(f'INSERT INTO {audit.DIRTY} VALUES (?, ?, ?)', (ms.TABLE, "b", 200.0))
    row = state.of("market")
    assert row["audit"] == {"checked_at": 200.0, "keys": 2, "differs": 1, "tables": [ms.TABLE]}
    assert row["audit_dirty"] == 1


def test_the_reader_never_opens_a_serving_file_for_writing(seeded, monkeypatch):
    """The dashboard holds the only writer there is. A read that opened a file read-write would take that lock, so
    every open of this module goes through ``serving.open_read``; a plain ``duckdb.connect`` here fails the test."""
    _build()
    opened: list[dict] = []
    real = duckdb.connect

    def spy(*a, **kw):
        opened.append(kw)
        return real(*a, **kw)

    monkeypatch.setattr(duckdb, "connect", spy)
    state.of("market")
    assert opened, "the reader opened no file at all"
    assert all(kw.get("read_only") is True for kw in opened), opened


def test_an_unreadable_file_is_that_kinds_error_and_the_other_kinds_still_answer(seeded):
    """One broken file must not take the Settings page down: it is one row with an ``error``."""
    _build()
    serving.live_path("market").write_bytes(b"not a duckdb file")
    row = state.of("market")
    assert "error" in row and row["kind"] == "market"
    rows = {r["kind"]: r for r in state.all_kinds()}
    assert set(rows) == set(serving.KINDS)
    assert "error" in rows["market"]
    assert all("error" not in r for k, r in rows.items() if k != "market")


def test_prices_holds_its_whole_build_for_a_person():
    """#446 step 8's declaration is what the board's ``by hand`` chip reads; until that lands the list is empty
    for every kind, which is what ``getattr`` in the reader is for."""
    row = state.of("prices")
    held = list(base.whole_build_by_hand("prices")) if hasattr(base, "whole_build_by_hand") else []
    assert row["by_hand"] == held
