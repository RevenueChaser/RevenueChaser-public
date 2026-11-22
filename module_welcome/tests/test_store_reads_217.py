"""#217 (F12): every read of ``boards/welcome.duckdb`` goes through ``module_welcome/store_reads.py``.

Two halves, as the News (PR #1195), Relatedness (PR #1269) and Co-movement (PR #1280) steps have them. The first
is the invariant: no file outside the reader queries the Welcome store, no module of the board carries one of its
table names of its own, and every table the schema files under ``db="welcome"`` has a name here. The second is the
behaviour of each reader against a real temp store (``rawstore_tmp_db``).

What this board's step is about is the *pairs*: the card and the build each read the same table, and the two reads
have to mean the same thing. The newest close per series is one cut, now written once; the two days' earnings rows
are one cut, with the card's ``retired_at IS NULL`` the only difference between them — a card that forgot it would
show names the screener has dropped.

No network and no real store: ``conftest.py`` redirects the roots and the autouse fixture gives each test its own
file.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from revenuechaser.core import rawstore
from revenuechaser.module_welcome import build as wb
from revenuechaser.module_welcome import store_reads as sr

REPO = Path(__file__).resolve().parents[2]
#: The four tables of the board's file, as the names a stray ``SELECT`` would spell.
TABLE_NAMES = (sr.SNAPSHOT, sr.EARNINGS, sr.FRESHNESS, sr.META)
D1, D2 = date(2026, 11, 23), date(2026, 11, 24)


# ── the invariant ─────────────────────────────────────────────────────────────────────────────────────────────────
def _sources() -> list[Path]:
    """Every non-test Python file of the repository."""
    return [p for p in REPO.rglob("*.py")
            if "tests" not in p.parts and not p.name.startswith("test_") and ".git" not in p.parts]


def test_only_the_reader_queries_the_welcome_store():
    """A ``rawstore.query(..., db="welcome")`` anywhere else is embedded board SQL, which is what #217 is about.
    A write (``rawstore.write_rows``) is not a query and stays with the build that produces the rows;
    ``core/datasets.py`` names the db as the dataset's declaration, which is not a call.
    """
    call = re.compile(r"\.query\((?:[^()]|\([^()]*\))*db\s*=\s*[\"']welcome[\"']", re.S)
    offenders = [str(p.relative_to(REPO)) for p in _sources()
                 if p != Path(sr.__file__) and call.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"these files still query the Welcome store directly: {offenders}"


def test_no_module_of_the_board_spells_a_welcome_table_name_itself():
    """The board's modules take the names from the reader, so a rename is a change to one file.

    ``build.py`` re-exports them, because it has been their home since S16 and ``report.py``, the tests and
    ``app/runners.py`` reach them through it — a re-export is one name from the reader, not a second copy.
    """
    offenders = {}
    for p in sorted((REPO / "module_welcome").glob("*.py")):
        if p == Path(sr.__file__):
            continue
        text = p.read_text(encoding="utf-8")
        # Only a string literal counts: the docstrings name the tables in prose on purpose.
        named = [t for t in TABLE_NAMES if f'"{t}"' in text or f"'{t}'" in text]
        if named:
            offenders[p.name] = named
    assert offenders == {}, f"these modules carry a welcome table name of their own: {offenders}"


def test_every_welcome_table_in_the_schema_has_a_name_here():
    """A table added to the Welcome store without a reader seam would reopen the hole this PR closes."""
    schema = {name for name, spec in rawstore.MANIFEST.items() if spec.get("db") == sr.DB}
    assert schema, "the schema should file some table under the welcome store"
    assert schema == set(TABLE_NAMES), f"the reader names {sorted(TABLE_NAMES)}, the schema has {sorted(schema)}"


def test_the_names_the_build_writes_are_the_readers_names():
    """``build.py`` re-exports rather than spelling: the writes and the reads cannot drift apart."""
    assert (wb.SNAPSHOT, wb.EARNINGS, wb.FRESHNESS, wb.META) == TABLE_NAMES


# ── the newest close per series ───────────────────────────────────────────────────────────────────────────────────
def _snap(series: str, day: date, close: float, **kw) -> dict:
    row = {"series": series, "session_date": day, "close": close, "prev_close": None, "change": None,
           "change_pct": None, "spark": "[]"}
    row.update(kw)
    return row


def test_an_empty_store_reads_as_no_rows_everywhere(rawstore_tmp_db):
    assert sr.latest_snapshot_rows() == []
    assert sr.latest_snapshot_by_series() == {}
    assert sr.stored_snapshot_closes() == {}
    assert sr.earnings_rows((D1, D2)) == []
    assert sr.listed_earnings_rows((D1, D2)) == []
    assert sr.freshness_rows() == []


def test_the_snapshot_reads_the_newest_session_of_each_series(rawstore_tmp_db):
    """The table keeps every session it has written, so "the current close" is a window over the series."""
    rawstore.write_rows(sr.SNAPSHOT, [
        _snap("SPX", date(2026, 11, 18), 6000.0), _snap("SPX", date(2026, 11, 20), 6100.0),
        _snap("SPX", date(2026, 11, 19), 6050.0), _snap("VIX", date(2026, 11, 19), 15.0)])
    latest = sr.latest_snapshot_by_series()
    assert sorted(latest) == ["SPX", "VIX"]
    assert (latest["SPX"]["session_date"], latest["SPX"]["close"]) == (date(2026, 11, 20), 6100.0)
    assert latest["VIX"]["session_date"] == date(2026, 11, 19)


def test_the_card_and_the_build_read_the_same_newest_close(rawstore_tmp_db):
    """The one cut #217 is about on this board: the tile's row and the build's "what do I hold" are one read."""
    rawstore.write_rows(sr.SNAPSHOT, [_snap("SPX", date(2026, 11, 19), 6050.0),
                                      _snap("SPX", date(2026, 11, 20), 6100.0)])
    assert sr.stored_snapshot_closes() == {"SPX": (date(2026, 11, 20), 6100.0)}
    card = sr.latest_snapshot_by_series()["SPX"]
    assert sr.stored_snapshot_closes()["SPX"] == (card["session_date"], card["close"])


def test_the_snapshot_row_carries_every_column_so_an_older_store_still_loads(rawstore_tmp_db):
    rawstore.write_rows(sr.SNAPSHOT, [_snap("SPX", D1, 6100.0, change=50.0, change_pct=0.008, spark="[1, 2]")])
    row = sr.latest_snapshot_rows()[0]
    assert (row["change"], row["spark"]) == (50.0, "[1, 2]")
    assert "run_id" in row and row["run_id"] is None


# ── the two days' earnings ────────────────────────────────────────────────────────────────────────────────────────
def _earn(day: date, ticker: str, session: str = "amc", retired: float | None = None, move: float | None = None
          ) -> dict:
    return {"earnings_date": day, "ticker": ticker, "report_session": session, "full_name": f"{ticker} Inc",
            "expected_move_perc": move, "retired_at": retired}


def test_the_card_leaves_out_a_retired_name_and_the_build_still_sees_it(rawstore_tmp_db):
    """A retired row stays in the store (nothing about this board deletes), so the two reads differ by exactly
    that filter: the card must not print a name the screener has dropped, and the build must still find it to
    un-retire it."""
    rawstore.write_rows(sr.EARNINGS, [_earn(D1, "AAA"), _earn(D1, "BBB", retired=1_763_000_000.0),
                                      _earn(D2, "CCC")])
    assert sorted(r["ticker"] for r in sr.listed_earnings_rows((D1, D2))) == ["AAA", "CCC"]
    assert sorted(r["ticker"] for r in sr.earnings_rows((D1, D2))) == ["AAA", "BBB", "CCC"]


def test_only_the_two_days_asked_for_answer(rawstore_tmp_db):
    rawstore.write_rows(sr.EARNINGS, [_earn(D1, "AAA"), _earn(date(2026, 11, 25), "ZZZ")])
    assert [r["ticker"] for r in sr.listed_earnings_rows((D1, D2))] == ["AAA"]
    assert [r["ticker"] for r in sr.earnings_rows((D1, D2))] == ["AAA"]


def test_the_held_rows_are_keyed_the_way_the_table_is(rawstore_tmp_db):
    """``(earnings_date, ticker, report_session)``: one company reporting before and after the bell is two rows,
    and the build compares them one by one."""
    rawstore.write_rows(sr.EARNINGS, [_earn(D1, "AAA", "bmo"), _earn(D1, "AAA", "amc", move=0.05)])
    held = sr.earnings_held((D1, D2))
    assert sorted(held) == [(D1, "AAA", "amc"), (D1, "AAA", "bmo")]
    assert held[(D1, "AAA", "amc")]["expected_move_perc"] == 0.05


# ── the builder files ─────────────────────────────────────────────────────────────────────────────────────────────
def test_the_freshness_rows_read_unfiltered(rawstore_tmp_db):
    """The card decides what counts as quiet or failing, and a file whose last run is old is the thing the card
    exists to show: the reader must not drop it."""
    rawstore.write_rows(sr.FRESHNESS, [
        {"job": "market", "last_status": "ok", "last_finished_at": 1_763_000_000.0},
        {"job": "earnings", "last_status": "error", "last_finished_at": 1_000_000.0},
        {"job": "never_ran", "last_status": None, "last_finished_at": None}])
    rows = {r["job"]: r for r in sr.freshness_rows()}
    assert sorted(rows) == ["earnings", "market", "never_ran"]
    assert rows["never_ran"]["last_finished_at"] is None
    assert rows["earnings"]["last_status"] == "error"
