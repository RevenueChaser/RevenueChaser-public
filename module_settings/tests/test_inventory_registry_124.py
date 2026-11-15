"""The registry's facts on each inventory row (S5 of the Data Health plan, #124).

``_collect`` keeps building the rows it always built; ``_attach_registry`` adds the registry's
source, writer, coverage and freshness to them, and the collected rows are ordered worst
coverage first. Store only: the seeded store is a temp DuckDB, no provider is asked.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.core import datasets, rawstore
from RevenueChaser.core.datahealth import Health
from RevenueChaser.module_settings import inventory, report


def _spec(key: str, **over) -> datasets.DatasetSpec:
    """A copy of the registry's spec for ``key`` with some fields replaced."""
    return replace(datasets.by_key(key), **over)


def _row(key: str, **over) -> dict:
    """One row shaped the way ``_collect`` builds it."""
    row = {"key": key, "label": key, "tables": [], "rows": 1, "last_date": inventory.DASH,
           "holes": None, "hole_label": "", "fetch": None, "note": "kept"}
    row.update(over)
    return row




# ── the default sort ────────────────────────────────────────────────────────








# ── source, writer, fresh ───────────────────────────────────────────────────






# ── S5b / G3 of the GUI brief (#124): one named state per kind of table ─────────────────────
# ``_fresh_record`` returns ``{state, date, text}``. Every state carries words: the Fresh cell must
# never print a bare dash, and a failed query must never read like a table that holds no rows.
def _epoch(text: str) -> float:
    """Epoch seconds of an ISO minute, the unit ``job_runs.started_at`` / ``finished_at`` hold."""
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()








def _fail_on(*tables: str):
    """``rawstore.query`` as it is, except a read naming one of ``tables`` raises."""
    real = rawstore.query

    def flaky(sql, *args, **kwargs):
        if any(name in sql for name in tables):
            raise RuntimeError("the freshness query failed")
        return real(sql, *args, **kwargs)

    return flaky






















# ── coverage ────────────────────────────────────────────────────────────────














# ── G6a (#124): the board card reads the coverage the inventory already attached ─────────────


# ── G5 (#124): the seconds the collect took, so the board can print them ─────────────────────
def test_collect_reports_a_non_negative_number_of_seconds(rawstore_tmp_db):
    seconds = inventory.collect()["timing"]["collect_seconds"]
    assert isinstance(seconds, (int, float)) and not isinstance(seconds, bool)
    assert seconds >= 0


def test_collect_measures_the_clock_around_the_collect(monkeypatch, rawstore_tmp_db):
    """The timing is the clock across ``_collect`` and nothing else: a fixed clock proves it."""
    class _Clock:
        def __init__(self):
            self.values = [10.0, 12.5]       # 2.5 s pass while the collect runs, then time stops

        def perf_counter(self):
            return self.values.pop(0) if len(self.values) > 1 else self.values[0]

    monkeypatch.setattr(inventory, "time", _Clock())
    assert inventory.collect()["timing"] == {"collect_seconds": 2.5}

# ── S6 of the Data Health plan (#124): "Other store tables" ─────────────────────────────────
# The backstop for a MANIFEST table no dataset claims. Empty today (the registry claims every
# table); a registry hole must be reported with the store file it lives in, its row count and its
# newest date — and an empty set must cost the store no query at all.
_NOW = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)


def _leave_unclaimed(monkeypatch, *tables: str) -> None:
    """Act as if the registry forgot ``tables`` (the real registry claims every one of them)."""
    claimed = datasets.tables_claimed() - set(tables)
    monkeypatch.setattr(datasets, "tables_claimed", lambda: claimed)










def test_the_payload_carries_the_other_tables_list(rawstore_tmp_db):
    assert inventory.collect(now=_NOW)["other_tables"] == []




# ── G11 of the GUI brief (#124): what is missing, and how it improves ───────────────────────










# ── S7 of the Data Health plan (#124): identity coverage ─────────────────────
