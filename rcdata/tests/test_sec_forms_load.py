"""How ``sec/forms``' build loads its partitions into the build file (#1177).

The step's rows are the biggest text in the repository -- 14,142 ``filing_section`` rows held 4.1 GB of text on
20 Nov 2026, uncapped since ``ours-2`` -- and a whole build read every partition in **one**
``INSERT ... ORDER BY cik, accession, document``. DuckDB pins a sort's string blocks, so it had nothing to evict
and the spill folder did not save it: the 07:05 CET build of that day ended after 6,590 s on
``failed to pin block of size 612.0 KiB (4.5 GiB/4.5 GiB used)``, and the two runs after it failed the same way
while adding 62 sections. The tests below hold the two halves of the fix: the load is batched, and the rows still
land in the order the one sort gave them.
"""
from __future__ import annotations

from datetime import date

import pytest

from RevenueChaser.rcdata import serving
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.fundamentals import common
from RevenueChaser.rcdata.build.sec_forms import forms

#: Three companies whose number order and text order differ, because ``cik`` is a TEXT column: the rows must come
#: out in the text order a single ``ORDER BY cik`` gave them ('10', '100', '9'), not in number order.
CIKS = ("9", "10", "100")


class Recorder:
    """A build connection that remembers the statements it was given."""

    def __init__(self, con):
        self.con, self.sql = con, []

    def execute(self, sql, *args):
        self.sql.append(sql)
        return self.con.execute(sql, *args)


def _section(cik: str) -> dict:
    row = {c: None for c, _ in forms.SECTION}
    row.update(cik=cik, accession=f"{int(cik):010d}-26-000001", document="k.htm", form="10-K",
               filing_date=date(2026, 2, 1), report_date=date(2025, 12, 31), section=forms.WHOLE,
               text="Business." * 10, chars=90, quality="ok", method=forms.UNCUT,
               rules_version=forms.SECTIONS_VERSION, source_as_of=date(2026, 2, 1), fetched_at=1.0, run_id="t")
    return row


def _partition(cik: str) -> None:
    """One company's two Parquet files, as ``to_parquet_all`` writes them: a section row, and no note row."""
    folder = common.parquet_dir(forms.NAME) / f"cik={cik}"
    con = serving.connect_scratch()
    try:
        base.rows_table(con, "sections", forms.SECTION, [_section(cik)])
        base.write_parquet(con, "SELECT * FROM sections", folder / forms.SECTIONS_PARQUET)
        base.rows_table(con, "notes", forms.NOTE, [])
        base.write_parquet(con, "SELECT * FROM notes", folder / forms.NOTES_PARQUET)
    finally:
        con.close()


@pytest.fixture
def tree(monkeypatch):
    """The Parquet tree of :data:`CIKS`, and no predecessor pair (``_predecessor_rows`` reads the spine)."""
    monkeypatch.setattr(common, "predecessor_ciks", lambda *a, **k: {})
    for cik in CIKS:
        _partition(cik)


def _whole_build(monkeypatch, batch: int) -> Recorder:
    """A whole build (no incremental plan on the context) with :data:`forms.LOAD_BATCH` set to ``batch``."""
    monkeypatch.setattr(forms, "LOAD_BATCH", batch)
    con = Recorder(serving.connect_scratch())
    forms.DATASET.build(base.RunContext(run_id="t", dataset=forms.NAME), con)
    return con


def _loads(rec: Recorder, table: str, partition: str) -> list[int]:
    """How many partitions each ``INSERT`` into ``table`` read."""
    return [s.count(partition) for s in rec.sql if s.startswith(f"INSERT INTO {table} ")]


def test_a_whole_build_loads_the_partitions_in_batches_and_not_in_one_statement(tree, monkeypatch):
    rec = _whole_build(monkeypatch, 2)
    assert _loads(rec, forms.SECTION_TABLE, forms.SECTIONS_PARQUET) == [2, 1]
    assert _loads(rec, forms.NOTE_TABLE, forms.NOTES_PARQUET) == [2, 1]


def test_one_company_at_a_time_is_a_load_each(tree, monkeypatch):
    rec = _whole_build(monkeypatch, 1)
    assert _loads(rec, forms.SECTION_TABLE, forms.SECTIONS_PARQUET) == [1, 1, 1]


def test_the_batched_load_leaves_the_rows_in_the_order_one_sort_gave_them(tree, monkeypatch):
    """The ``cik`` order is the column's own, not ``_partitions``' number order: '10', '100', '9'."""
    rec = _whole_build(monkeypatch, 1)
    served = [c for c, in rec.con.execute(f"SELECT cik FROM {forms.SECTION_TABLE}").fetchall()]
    assert served == sorted(CIKS)


def test_every_row_still_reaches_the_table(tree, monkeypatch):
    rec = _whole_build(monkeypatch, 2)
    assert rec.con.execute(f"SELECT count(*) FROM {forms.SECTION_TABLE}").fetchone()[0] == len(CIKS)
