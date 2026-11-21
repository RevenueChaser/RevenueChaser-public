"""The Stage 2 and Stage 3 tables of ``docs/data_architecture.md`` against the code that owns them (#1209).

#860 deleted ``raw.duckdb``, ``edgar.duckdb``, ``history.duckdb`` and ``.store/prices.duckdb``; #1167 rewrote the
passages around them, and #1209 walked these two tables row by row: a row whose table is still served under its old
name became a bridge-view row naming the serving kind, a row whose data moved kept the name the serving layer uses,
and a row with no live home was dropped into the ``*(retired with the old files)*`` row, which says where its data
went. The first guard (#1224) carried the leftovers as two closed ``STALE_*`` lists; both are empty now, so the lists
are gone and the rule is absolute instead:

- a row may name a ``rawstore.MANIFEST`` table, a serving table (``rcdata/read.DATASET_OF_TABLE``) or a bridge view
  — nothing else, so a row cannot describe a table that does not exist;
- a row whose table the manifest holds names the manifest's own ``"db"``, so that column cannot go stale one row at
  a time;
- a bridge view is marked ``(VIEW)`` and its Stage 2 ``DB`` cell names the serving kind that creates it, and a row
  **not** so marked names no bridge view, so the bridge cannot be re-described as a cache of a board's own.

A VIEW row used to be skipped here, which is how two dead ones survived: ``core/rawstore.py`` creates no view any
more, so the Stage 3 ``index_tickers`` row belonged to the spine and the ``company_profile`` row to nothing at all.
Views are parsed now.
"""

from __future__ import annotations

import re
from pathlib import Path

from RevenueChaser.core import rawstore
from RevenueChaser.rcdata import read
from RevenueChaser.rcdata.build.fundamentals import tables as fundamentals_tables
from RevenueChaser.rcdata.build.ownership import serve as ownership_serve
from RevenueChaser.rcdata.build.prices import serving as prices_serving
from RevenueChaser.rcdata.build.spine import views as spine_views

_REPO = Path(__file__).resolve().parents[2]

#: Serving kind -> the views that kind's build creates under the old store's names (decision D4). Taken from the
#: build modules themselves, so a view added or dropped there moves this set with it.
BRIDGE_VIEWS: dict[str, frozenset[str]] = {
    "spine": frozenset(spine_views.VIEWS),
    "prices": frozenset(prices_serving.VIEWS),
    "fundamentals": frozenset(fundamentals_tables.VIEWS),
    "ownership": frozenset(ownership_serve.VIEWS),
}
#: Every bridge view, whichever kind serves it.
BRIDGES: frozenset[str] = frozenset().union(*BRIDGE_VIEWS.values())
#: A name a row may carry: a board's own store table, a served table, or a bridge view.
LIVE: frozenset[str] = frozenset(rawstore.MANIFEST) | frozenset(read.DATASET_OF_TABLE) | BRIDGES


def _rows(heading: str, until: str, cells_wanted: int) -> list[tuple[list[str], list[str]]]:
    """``([table names], cells)`` per row of one stage's table."""
    text = (_REPO / "docs" / "data_architecture.md").read_text(encoding="utf-8")
    section = text.split(heading, 1)[1].split(until, 1)[0]
    rows: list[tuple[list[str], list[str]]] = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != cells_wanted:
            continue
        names = re.findall(r"`([a-z0-9_]+)\*?`", cells[0])
        if names:
            rows.append((names, cells))
    return rows


def _stage2() -> list[tuple[list[str], list[str]]]:
    return _rows("### Stage 2 — Raw caches", "### Stage 3", 4)   # Table | Content | DB | TTL


def _stage3() -> list[tuple[list[str], list[str]]]:
    return _rows("### Stage 3 — Normalized / derived stores", "### Stage 4", 3)   # Table | Derived from | Notes


def test_the_parse_finds_both_tables_at_all() -> None:
    """A renamed heading or a reshaped table would make every assertion below vacuous."""
    assert len(_stage2()) >= 20, f"only {len(_stage2())} Stage 2 rows parsed; the table's shape changed"
    assert len(_stage3()) >= 10, f"only {len(_stage3())} Stage 3 rows parsed; the table's shape changed"


def test_every_stage_2_row_names_the_db_the_manifest_names() -> None:
    wrong = []
    for names, cells in _stage2():
        for name in names:
            spec = rawstore.MANIFEST.get(name)
            if spec is None:
                continue
            code_db = spec.get("db") or "—"
            if cells[2].strip("` ") != code_db:
                wrong.append(f"{name}: doc says {cells[2].strip('` ')!r}, MANIFEST says {code_db!r}")
    assert not wrong, "the Stage 2 DB column disagrees with rawstore.MANIFEST:\n  " + "\n  ".join(wrong)


def test_every_row_names_a_table_or_a_view_that_exists() -> None:
    """#1209's rule, and the end of its two STALE lists: a row describes a table that is really there."""
    dead = {
        "Stage 2": sorted({n for names, _ in _stage2() for n in names if n not in LIVE}),
        "Stage 3": sorted({n for names, _ in _stage3() for n in names if n not in LIVE}),
    }
    named = {k: v for k, v in dead.items() if v}
    assert not named, (
        f"rows for tables neither the manifest, the serving layer nor a bridge view holds: {named}. #860 deleted "
        "raw.duckdb, edgar.duckdb, history.duckdb and .store/prices.duckdb: give the row the name its data is "
        "served under now, or move it into the '(retired with the old files)' row, which says where the data went.")


def test_a_bridge_view_row_is_marked_and_names_the_kind_that_serves_it() -> None:
    """The Stage 2 DB cell of a bridge view is the serving kind whose build creates it, not `raw` and not a board."""
    wrong = []
    for names, cells in _stage2():
        for name in names:
            if name not in BRIDGES or name in rawstore.MANIFEST:
                continue
            kind = next(k for k, views in BRIDGE_VIEWS.items() if name in views)
            if "(VIEW)" not in cells[0]:
                wrong.append(f"{name}: a bridge view, so its row is marked (VIEW)")
            if cells[2].strip("` ") != kind:
                wrong.append(f"{name}: doc says DB {cells[2].strip('` ')!r}, {kind}'s build creates the view")
    assert not wrong, "bridge-view rows of Stage 2:\n  " + "\n  ".join(wrong)


def test_a_row_that_is_not_marked_a_view_names_no_bridge_view() -> None:
    """So a view rcdata serves cannot be described again as a cache a board writes itself."""
    wrong = []
    for stage, rows in (("Stage 2", _stage2()), ("Stage 3", _stage3())):
        for names, cells in rows:
            if "(VIEW)" in cells[0]:
                continue
            for name in names:
                if name in BRIDGES and name not in rawstore.MANIFEST:
                    wrong.append(f"{stage}: {name} is a bridge view; mark its row (VIEW)")
    assert not wrong, "\n  ".join(wrong)


def test_no_row_names_a_file_number_eight_six_zero_deleted() -> None:
    """The reason the DB column was stale at all: a row may not point at a deleted file."""
    gone = ("raw", "edgar", "history", "prices.duckdb")
    wrong = [f"{names[0]}: DB {cells[2]!r}" for names, cells in _stage2()
             if cells[2].strip("` ") in gone]
    assert not wrong, ("these Stage 2 rows still name a file #860 deleted:\n  " + "\n  ".join(wrong)
                       + "\n(the prices store in RC_MARKET_DIR is the kind `prices`, not the old .store file)")
