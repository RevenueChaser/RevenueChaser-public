"""#217 (F12): every read of ``boards/sector_rotation.duckdb`` goes through
``module_sector_rotation/store_reads.py``.

Two halves, as the News (PR #1195), Relatedness (PR #1269), Co-movement (PR #1280) and Welcome (PR #1281) steps
have them. The first is the invariant: no file outside the reader queries the store, no module of the board
spells one of its table names, and every table the schema files under ``db="sector_rotation"`` has a name here.
The second is the behaviour of each reader against a real temp store (``rawstore_tmp_db``).

The read this step is for lived in ``core/provenance.py``: the board's **data date**, written three directories
from the tables it named. That is the shape of the bug the News step found — ``core/provenance._news_day()``
queried ``news_calendar``, a table that has never existed, and because a read swallows ``CatalogException`` the
board's date had been blank for ever with nothing failing. A date that comes from a board's own rows is read by
that board.

No network and no real store: ``conftest.py`` redirects the roots and the autouse fixture gives each test its own
file.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from RevenueChaser.core import provenance, rawstore
from RevenueChaser.module_sector_rotation import store_reads as sr

REPO = Path(__file__).resolve().parents[2]
#: The two tables of the board's file, as the names a stray ``SELECT`` would spell.
TABLE_NAMES = (sr.SNAPSHOTS, sr.HOLDINGS)
D1, D2, D3 = date(2026, 11, 18), date(2026, 11, 19), date(2026, 11, 20)


# ── the invariant ─────────────────────────────────────────────────────────────────────────────────────────────────
def _sources() -> list[Path]:
    """Every non-test Python file of the repository."""
    return [p for p in REPO.rglob("*.py")
            if "tests" not in p.parts and not p.name.startswith("test_") and ".git" not in p.parts]


def test_only_the_reader_queries_the_rotation_store():
    """A ``rawstore.query(..., db="sector_rotation")`` anywhere else is embedded board SQL, which is what #217 is
    about. A write (``rawstore.write_rows``) and a keyed ``rawstore.get`` are not queries and stay with the code
    that produces or fetches the rows; ``core/datasets.py`` names the db as the dataset's declaration.
    """
    call = re.compile(r"\.query\((?:[^()]|\([^()]*\))*db\s*=\s*[\"']sector_rotation[\"']", re.S)
    offenders = [str(p.relative_to(REPO)) for p in _sources()
                 if p != Path(sr.__file__) and call.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"these files still query the Rotation store directly: {offenders}"


def test_no_module_of_the_board_spells_a_rotation_table_name_itself():
    """The board's modules take the names from the reader, so a rename is a change to one file — the holdings
    writer and its keyed read included."""
    offenders = {}
    for p in sorted((REPO / "module_sector_rotation").glob("*.py")):
        if p == Path(sr.__file__):
            continue
        text = p.read_text(encoding="utf-8")
        # Only a string literal counts: the docstrings name the tables in prose on purpose.
        named = [t for t in TABLE_NAMES if f'"{t}"' in text or f"'{t}'" in text]
        if named:
            offenders[p.name] = named
    assert offenders == {}, f"these modules carry a rotation table name of their own: {offenders}"


def test_every_rotation_table_in_the_schema_has_a_name_here():
    """A table added to the store without a reader seam would reopen the hole this PR closes."""
    schema = {name for name, spec in rawstore.MANIFEST.items() if spec.get("db") == sr.DB}
    assert schema, "the schema should file some table under the rotation store"
    assert schema == set(TABLE_NAMES), f"the reader names {sorted(TABLE_NAMES)}, the schema has {sorted(schema)}"


def test_the_data_date_is_read_by_the_board_and_not_by_core_provenance():
    """``core/provenance`` held this board's SQL; a resolver written beside another board's tables is checkable
    against nothing, and a wrong name there reads as "no date" rather than failing (the News step's bug)."""
    text = (REPO / "core" / "provenance.py").read_text(encoding="utf-8")
    for name in TABLE_NAMES:
        assert f'"{name}"' not in text and f"'{name}'" not in text, f"{name} is still spelled there"
    assert "as_of_date" not in text, "the column is the board's too"
    assert "store_reads" in text, "the resolver reads the board's seam"


# ── rows ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _snap(day: date, ticker: str, *, group: str = "sector", quadrant: str = "leading",
          benchmark: str = "SPY", source: str = "live") -> dict:
    return {"as_of_date": day.isoformat(), "ticker": ticker, "name": f"{ticker} ETF", "group": group,
            "close_price": 100.0, "rs_ratio": 101.0, "rs_momentum": 100.5, "quadrant": quadrant,
            "benchmark": benchmark, "generated_at": f"{day.isoformat()}T20:00:00", "source": source}


def _holdings(ticker: str, rows: list | None, day: str = "2026-11-20") -> dict:
    return {"ticker": ticker, "date": day, "rows": json.dumps(rows) if rows is not None else None}


def test_an_empty_store_reads_as_no_rows_everywhere(rawstore_tmp_db):
    assert sr.snapshot_rows(D1) == []
    assert sr.snapshot_dates() == []
    assert sr.snapshot_rows_between(D1, D3) == []
    assert sr.newest_snapshot_date() is None
    assert sr.etfs_with_holdings() == set()


def test_a_session_reads_its_own_rows_by_ticker(rawstore_tmp_db):
    """The order is the answer: the board renders the rows as they come, and a session is compared with another
    row by row."""
    rawstore.write_rows(sr.SNAPSHOTS, [_snap(D2, "XLK"), _snap(D2, "XLE"), _snap(D2, "XLF"), _snap(D1, "XLK")])
    assert [r["ticker"] for r in sr.snapshot_rows(D2)] == ["XLE", "XLF", "XLK"]
    assert [r["as_of_date"] for r in sr.snapshot_rows(D2)] == [D2.isoformat()] * 3
    assert sr.snapshot_rows(D3) == []


def test_a_snapshot_row_carries_every_column_so_an_older_store_still_loads(rawstore_tmp_db):
    rawstore.write_rows(sr.SNAPSHOTS, [_snap(D2, "XLK", source="backfill")])
    row = sr.snapshot_rows(D2)[0]
    assert (row["benchmark"], row["quadrant"], row["source"]) == ("SPY", "leading", "backfill")
    # ``SELECT *``: a column no writer filled is present and NULL, not missing (#374 added ``source`` this way).
    assert "rs_ratio_z" in row and row["rs_ratio_z"] is None


def test_the_stored_sessions_read_oldest_first_and_once_each(rawstore_tmp_db):
    rawstore.write_rows(sr.SNAPSHOTS, [_snap(D3, "XLK"), _snap(D1, "XLK"), _snap(D1, "XLE"), _snap(D2, "XLK")])
    assert sr.snapshot_dates() == [D1.isoformat(), D2.isoformat(), D3.isoformat()]


def test_a_range_includes_both_ends_and_reads_session_then_ticker(rawstore_tmp_db):
    rawstore.write_rows(sr.SNAPSHOTS, [_snap(D1, "XLK"), _snap(D2, "XLF"), _snap(D2, "XLE"), _snap(D3, "XLK")])
    got = [(r["as_of_date"], r["ticker"]) for r in sr.snapshot_rows_between(D1, D3)]
    assert got == [(D1.isoformat(), "XLK"), (D2.isoformat(), "XLE"), (D2.isoformat(), "XLF"),
                   (D3.isoformat(), "XLK")]
    assert [r["as_of_date"] for r in sr.snapshot_rows_between(D2, D2)] == [D2.isoformat()] * 2


def test_the_newest_session_is_the_boards_data_date(rawstore_tmp_db):
    """And ``core.provenance`` answers with it, through the reader."""
    rawstore.write_rows(sr.SNAPSHOTS, [_snap(D1, "XLK"), _snap(D3, "XLK"), _snap(D2, "XLK")])
    assert sr.newest_snapshot_date() == D3.isoformat()
    assert provenance.data_as_of("module_sector_rotation") == D3.isoformat()


def test_an_etf_whose_stored_holdings_are_empty_does_not_count_as_stored(rawstore_tmp_db):
    """``rows`` NULL or an empty array is a read that answered nothing: counting it would tell the Settings card
    an ETF is stored when the board has no holdings for it."""
    rawstore.write_rows(sr.HOLDINGS, [_holdings("XLK", [{"ticker": "AAPL", "weight": 0.1}]),
                                      _holdings("XLE", []),
                                      _holdings("XLF", None)])
    assert sr.etfs_with_holdings() == {"XLK"}
