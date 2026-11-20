"""The Stage 2 and Stage 3 tables of ``docs/data_architecture.md`` against ``rawstore.MANIFEST`` (#1209).

The doc's own banner says it: "the `DB` column of the Stage 2 and Stage 3 tables is stale for the rows that
name no `rawstore.MANIFEST` table (#1209)". #860 deleted ``raw.duckdb``, ``edgar.duckdb``, ``history.duckdb``
and ``.store/prices.duckdb``; #1167 rewrote the passages around them and left these rows on purpose, because
each one needs its own answer — #1209 sorts them into the three cases it names (served under the old name
through a bridge view, moved into a serving store that has its own section here, or gone with its writer).

This is the guard #1209 asks for, not the cleanup it asks for first. It does three things:

- a row whose table the manifest holds must name the manifest's own ``"db"`` in its ``DB`` cell, so that column
  cannot go stale again one row at a time;
- a row whose table the manifest does not hold must be in ``STALE_STAGE2`` / ``STALE_STAGE3`` below. Those are
  the measured size of #1209 in code rather than in prose, and they are closed lists, so a new such row fails
  instead of passing quietly;
- a name that leaves those lists cannot come back, and a name that reaches the manifest has to leave them in the
  same commit (``test_no_stale_name_is_in_the_manifest_after_all``), so the lists can only shrink.

#1209 is finished when both lists are empty. A VIEW row is not checked: a view is not a manifest table.
"""

from __future__ import annotations

import re
from pathlib import Path

from RevenueChaser.core import rawstore

_REPO = Path(__file__).resolve().parents[2]

# Stage 2 rows whose DB cell names a file #860 deleted. Measured 20 Nov 2026 on main 7bfbec1: 29 names, which is
# 28 tables plus the `tradewhisperer_*` prefix row (the parser reads it as `tradewhisperer_`). Each is #1209's
# work, not a decision — some keep their row with a serving file named, some go. Nothing may be added here.
STALE_STAGE2: frozenset[str] = frozenset({
    "catalyst_events", "cftc_cot", "earnings_calendar", "earnings_history", "economic_calendar",
    "edgar_documents", "edgar_financials", "equity_universe", "estimate_snapshots", "etf_holdings",
    "identity_cusip", "index_levels_daily", "macro_series", "orphan_designations", "orphan_lookups",
    "ownership_snapshot", "price_actions", "price_bars_daily", "price_checks", "sec13f_edgar_backfill",
    "sec13f_filers", "sec13f_security_meta", "sec_submissions", "short_interest", "source_checks",
    "tradewhisperer_", "vendor_financials", "vol_index_daily", "watchlist",
})

# The same for Stage 3, measured the same day: 7 names. The `sec13f_*` four and `sec13f_totals` are the tables
# G9 left without a writer (the ownership store serves them); G10 (#274) retires them.
STALE_STAGE3: frozenset[str] = frozenset({
    "index_constituents", "run_registry", "sec13f_cusip_names", "sec13f_holdings", "sec13f_ingested_zips",
    "sec13f_submissions", "sec13f_totals",
})


def _rows(heading: str, until: str, cells_wanted: int) -> list[tuple[list[str], list[str]]]:
    """``([table names], cells)`` per row of one stage's table; VIEW rows carry no names."""
    text = (_REPO / "docs" / "data_architecture.md").read_text(encoding="utf-8")
    section = text.split(heading, 1)[1].split(until, 1)[0]
    rows: list[tuple[list[str], list[str]]] = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != cells_wanted:
            continue
        names = [] if "(VIEW)" in cells[0] else re.findall(r"`([a-z0-9_]+)\*?`", cells[0])
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


def test_a_row_outside_the_manifest_is_one_of_the_known_stale_ones() -> None:
    unexpected = {
        "Stage 2": sorted({n for names, _ in _stage2() for n in names
                           if n not in rawstore.MANIFEST and n not in STALE_STAGE2}),
        "Stage 3": sorted({n for names, _ in _stage3() for n in names
                           if n not in rawstore.MANIFEST and n not in STALE_STAGE3}),
    }
    named = {k: v for k, v in unexpected.items() if v}
    assert not named, (
        f"rows for tables the manifest does not hold: {named}. A row describes a table that exists: if one of "
        "these is #1209's leftover, give the row its serving file or drop it — do not grow the STALE lists.")


def test_no_stale_name_is_in_the_manifest_after_all() -> None:
    """Keeps the #1209 lists shrinking: a name that reaches the manifest leaves the list in the same commit."""
    fixed = sorted(n for n in STALE_STAGE2 | STALE_STAGE3 if n in rawstore.MANIFEST)
    assert not fixed, f"these are manifest tables now and must leave the STALE lists: {fixed}"


def test_the_stale_lists_only_name_rows_that_are_really_there() -> None:
    """A row that was fixed or dropped must leave its list, so the lists never outlive the work."""
    stage2 = {n for names, _ in _stage2() for n in names}
    stage3 = {n for names, _ in _stage3() for n in names}
    assert not sorted(STALE_STAGE2 - stage2), f"no Stage 2 row any more: {sorted(STALE_STAGE2 - stage2)}"
    assert not sorted(STALE_STAGE3 - stage3), f"no Stage 3 row any more: {sorted(STALE_STAGE3 - stage3)}"
