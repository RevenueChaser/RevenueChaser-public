"""``build/audit.py``: the sample that replaces the scheduled whole rebuild (#446 step 5).

A build on the live copy never looks at the rows it carries over, so each pass re-reads a few keys from Parquet
and compares them with the file. A difference is evidence - a build issue and a key dirty next build - never a
refusal.
"""
from __future__ import annotations

import pytest

from RevenueChaser.rcdata import ops
from RevenueChaser.rcdata.build import audit, base

ROWS = [("AAPL", 1, 10.0), ("AAPL", 2, 11.0), ("MSFT", 1, 20.0), ("GOOG", 1, 30.0)]
NAME = "test/one"
TABLE = "holding"


def _con(rows=ROWS):
    """A file holding the served table, and a ``source`` table standing in for what Parquet would answer."""
    con = base.scratch_con()
    for name in (TABLE, "source"):
        con.execute(f"CREATE TABLE {name} (ticker TEXT, period INTEGER, value DOUBLE)")
        con.execute(f"INSERT INTO {name} SELECT unnest(?::TEXT[]), unnest(?::INTEGER[]), unnest(?::DOUBLE[])",
                    ([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]))
    audit.ensure_tables(con)
    return con


def _subject(**kw) -> audit.Subject:
    return audit.Subject(dataset=NAME, table=TABLE, key="ticker",
                         recompute=lambda ctx, con, keys: "SELECT * FROM source", **kw)


def _rounds(con) -> dict:
    return {k: r for k, r in con.execute(f'SELECT key, result FROM {audit.ROUNDS}').fetchall()}


# ── what the driver does ──────────────────────────────────────────────────────────────────────────────────────

def test_a_file_that_matches_the_recompute_records_every_key_as_ok():
    con = _con()
    assert audit.run(None, con, [_subject()], {}) == {}
    assert _rounds(con) == {"AAPL": "ok", "MSFT": "ok", "GOOG": "ok"}
    assert con.execute(f"SELECT count(*) FROM {audit.DIRTY}").fetchone()[0] == 0


def test_a_row_the_file_has_wrong_is_a_difference_a_build_issue_and_a_dirty_key():
    con = _con()
    con.execute(f"UPDATE {TABLE} SET value = 99.0 WHERE ticker = 'MSFT'")
    assert audit.run(None, con, [_subject()], {}, "run-1") == {TABLE: ["MSFT"]}
    assert _rounds(con) == {"AAPL": "ok", "MSFT": "differs", "GOOG": "ok"}
    assert audit.dirty_keys(con, [TABLE]) == {"MSFT"}
    [issue] = [i for i in ops.rows("build_issues") if i["kind"] == audit.ISSUE]
    assert issue["dataset"] == NAME and issue["key"] == "MSFT" and TABLE in issue["detail"]


def test_a_row_the_file_is_missing_and_a_row_only_the_file_has_both_count():
    con = _con()
    con.execute(f"DELETE FROM {TABLE} WHERE ticker = 'AAPL' AND period = 2")      # the file is missing a row
    con.execute("DELETE FROM source WHERE ticker = 'GOOG'")                       # the file has one too many
    assert audit.run(None, con, [_subject()], {}) == {TABLE: ["AAPL", "GOOG"]}
    assert audit.dirty_keys(con, [TABLE]) == {"AAPL", "GOOG"}


def test_a_key_that_comes_out_ok_again_is_no_longer_dirty():
    con = _con()
    con.execute(f"UPDATE {TABLE} SET value = 99.0 WHERE ticker = 'MSFT'")
    audit.run(None, con, [_subject()], {})
    assert audit.dirty_keys(con, [TABLE]) == {"MSFT"}
    con.execute(f"UPDATE {TABLE} SET value = 20.0 WHERE ticker = 'MSFT'")
    assert audit.run(None, con, [_subject()], {}) == {}
    assert audit.dirty_keys(con, [TABLE]) == frozenset()


def test_the_audit_never_fails_the_build_when_a_subjects_own_sql_cannot_run():
    con = _con()
    broken = audit.Subject(dataset=NAME, table=TABLE, key="ticker",
                           recompute=lambda ctx, con, keys: "SELECT * FROM no_such_table")
    assert audit.run(None, con, [broken], {}) == {}


def test_a_kind_whose_datasets_declare_no_subject_is_not_audited():
    ds = type("Ds", (), {"name": NAME})()
    assert audit.subjects([ds], None) == []
    assert audit.run(None, _con(), [], {}) == {}


def test_a_dataset_that_answers_the_wrong_shape_raises():
    ds = type("Ds", (), {"name": NAME, "audit": lambda self, ctx: [{"table": TABLE}]})()
    with pytest.raises(TypeError, match="not a Subject"):
        audit.subjects([ds], None)


# ── how many keys, and which ──────────────────────────────────────────────────────────────────────────────────

def test_the_sample_is_bounded_and_the_lever_turns_it_off():
    assert audit.wanted({}) == audit.KEYS
    assert audit.wanted({audit.KEYS_ENV: "7"}) == 7
    assert audit.wanted({audit.KEYS_ENV: "0"}) == 0
    assert audit.wanted({audit.KEYS_ENV: "not a number"}) == audit.KEYS
    con = _con()
    con.execute(f"UPDATE {TABLE} SET value = 99.0")
    assert audit.run(None, con, [_subject()], {audit.KEYS_ENV: "0"}) == {}
    assert _rounds(con) == {}, "off is off: nothing recomputed, nothing recorded"
    assert len(audit.choose(con, _subject(), 2, 0.0)) == 2


def test_the_weight_a_subject_declares_decides_which_key_is_drawn():
    """A key worth looking at more often is drawn first; one weighted nothing waits for the others."""
    con = _con()
    weight = "SELECT * FROM (VALUES ('AAPL', 1.0), ('MSFT', 0.0), ('GOOG', 0.0)) AS t(key, weight)"
    subject = _subject(weight=weight)
    assert audit.weights(con, subject, 0.0)["MSFT"] == 0.0
    assert audit.choose(con, subject, 1, 0.0) == ("AAPL",), "a key weighted nothing is never drawn first"


def test_a_key_audited_just_now_is_worth_far_less_than_one_never_audited():
    """What makes the sample risk-weighted: the longer ago a key was read, the heavier it is."""
    con = _con()
    now = 1_700_000_000.0
    con.execute(f"INSERT INTO {audit.ROUNDS} VALUES (?, 'AAPL', ?, 'ok'), (?, 'MSFT', ?, 'ok')",
                (TABLE, now, TABLE, now - 86400.0 * 10))
    found = audit.weights(con, _subject(), now)
    assert found["AAPL"] == pytest.approx(1.0)                       # read just now
    assert found["MSFT"] == pytest.approx(11.0)                      # ten days ago
    assert found["GOOG"] == pytest.approx(1.0 + audit.NEVER_DAYS)    # never read
    assert audit.choose(con, _subject(), 1, now, rng=_Rng([0.5, 0.5, 0.5])) == ("GOOG",)


class _Rng:
    """A draw with no randomness left in it: the same number for every key, so the weights decide."""

    def __init__(self, numbers):
        self._numbers = list(numbers)

    def random(self) -> float:
        return self._numbers.pop(0)


def test_a_table_with_no_rows_is_audited_with_no_keys():
    con = _con()
    con.execute(f"DELETE FROM {TABLE}")
    assert audit.run(None, con, [_subject()], {}) == {}
    assert _rounds(con) == {}


def test_a_file_from_before_the_audit_has_no_dirty_keys_and_does_not_raise():
    con = base.scratch_con()
    assert audit.dirty_keys(con, [TABLE]) == frozenset()
    assert audit.dirty_keys(con, []) == frozenset()
