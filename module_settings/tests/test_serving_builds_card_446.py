"""#446 step 8: the Serving builds card says how each kind's live file was built, what has changed in Parquet
since, and what the last audit round found.

Two halves, as the card has two: ``newdata._build_of`` reads a real built file (the numbers are the ones steps 1,
2 and 5 wrote into it), and ``control_render`` draws them without a second copy of the data anywhere.
"""
from __future__ import annotations

import time

import duckdb
import pytest

from RevenueChaser.module_settings import control_render, newdata, report
from RevenueChaser.module_settings.tests.test_control_view import control_nd
from RevenueChaser.rcdata import serving
from RevenueChaser.rcdata.build import audit, base, dirty
from RevenueChaser.rcdata.build.sources import fred


# ── what the card reads out of a file ─────────────────────────────────────────────────────────────────────────

def _built(kind: str = "market", mode: str | None = None) -> None:
    with serving.build(kind) as b:
        b.con.execute("CREATE TABLE t (i INTEGER)")
        b.con.execute("INSERT INTO t SELECT range FROM range(3)")
        b.swap({"t": 3})
    if mode is not None:
        con = duckdb.connect(str(serving.live_path(kind)))
        try:
            con.execute(f"UPDATE {serving.VERSION_TABLE} SET build_mode = ? WHERE kind = ?", (mode, kind))
        finally:
            con.close()


def _read(kind: str = "market") -> dict:
    with serving.open_read(kind) as con:
        names = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        return newdata._build_of(kind, con, names)


def _write(kind: str, sql: list[tuple[str, tuple]]) -> None:
    con = duckdb.connect(str(serving.live_path(kind)))
    try:
        audit.ensure_tables(con)
        for statement, args in sql:
            con.execute(statement, args)
    finally:
        con.close()


def test_a_file_from_before_446_reads_as_a_whole_build_with_no_manifest():
    """None of the tables is there, which is every file built before this landed: not an error, and not zeroes."""
    _built()
    got = _read()
    assert got["files"] is None and got["changed"] is None, "no manifest is not an empty manifest"
    assert got["audited_at"] is None and got["owed"] is None
    assert got["built_at"] is not None, "the swap stamps every file, old or new"


def test_the_mode_is_the_base_the_build_really_got():
    _built(mode="live")
    assert _read()["mode"] == "live"
    _built(mode="fresh")
    assert _read()["mode"] == "fresh"


def test_the_parquet_count_is_the_manifest_and_what_differs_from_the_tree_right_now():
    """The card's own comparison is ``dirty.changes``': a file whose size or mtime differs, a new one, a gone one.

    The files go in a real ``market`` source's folder (``fred/series``), because the card asks that kind's own
    datasets where their Parquet is, exactly as a build does."""
    folder = base.parquet_root() / fred.SOURCE / fred.DATASET_DIR / "year=2026"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "part-0.parquet").write_bytes(b"one")
    (folder / "part-1.parquet").write_bytes(b"two")
    _built()
    held = dirty.scan(base.kind_datasets("market"))
    assert len(held) == 2, held
    con = duckdb.connect(str(serving.live_path("market")))
    try:
        dirty.write_manifest(con, dirty.Plan(None, {}, held, {}, ()))
    finally:
        con.close()
    got = _read()
    assert got["files"] == 2 and got["changed"] == 0, "nothing has moved since the manifest was written"

    (folder / "part-1.parquet").write_bytes(b"restated, and longer")
    (folder / "part-2.parquet").write_bytes(b"new")
    got = _read()
    assert got["files"] == 2 and got["changed"] == 2, "one restated and one new; the untouched one is not changed"

    (folder / "part-0.parquet").unlink()
    assert _read()["changed"] == 3, "a gone file is changed too"


def test_the_last_audit_round_is_counted_and_an_older_round_is_not_mixed_into_it():
    """One round stamps its keys together; the round before it is a separate build and must not be added in."""
    _built()
    now = time.time()
    _write("market", [(f'INSERT INTO {audit.ROUNDS} VALUES (?, ?, ?, ?)', ("t", key, when, result))
                      for key, when, result in
                      [("AAPL", now - 7200, "differs"), ("MSFT", now - 7200, "ok"), ("NVDA", now - 7200, "ok"),
                       ("AAPL", now, "ok"), ("MSFT", now, "differs")]])
    got = _read()
    assert got["audited"] == 2 and got["differs"] == 1, "the newest round only"
    assert got["audited_at"] is not None


def test_the_keys_owed_are_the_ones_the_audit_still_has_marked():
    _built()
    now = time.time()
    _write("market", [(f'INSERT INTO {audit.DIRTY} VALUES (?, ?, ?)', ("t", key, now))
                      for key in ("AAPL", "MSFT")])
    assert _read()["owed"] == 2
    _write("market", [(f'DELETE FROM {audit.DIRTY} WHERE key = ?', ("AAPL",))])
    assert _read()["owed"] == 1


# ── what the card draws ───────────────────────────────────────────────────────────────────────────────────────

def _row(**extra) -> dict:
    return {"kind": "prices", "mode": "live", "built_at": "2026-11-20T02:04:00+00:00", "files": 18402,
            "changed": 31, "audited_at": "2026-11-20T02:04:00+00:00", "audited": 500, "differs": 0,
            "owed": 0, **extra}


def _page(rows: list[dict]) -> str:
    nd = control_nd()
    nd["builds"] = {r["kind"]: r for r in rows}
    return report.render_settings_dashboard({"newdata": nd})


def test_the_card_is_on_the_data_tab_with_one_row_a_file():
    html = _page([_row(), _row(kind="spine", mode="fresh", files=None, changed=None, audited_at=None, owed=None)])
    assert 'id="ctl-builds"' in html, "the card is drawn"
    assert "prices.duckdb" in html and "spine.duckdb" in html
    assert "on the live file" in html and "built whole" in html
    assert "18,402 files · 31 changed" in html
    assert "no manifest yet" in html and "no round yet" in html


def test_a_difference_and_an_owed_key_are_named_and_a_clean_file_is_not():
    html = _page([_row(differs=3, owed=2)])
    assert "3 differ" in html and "key(s) owed a rebuild" in html
    clean = _page([_row()])
    assert "all ok" in clean and "nothing owed" in clean
    assert "differ</span>" not in clean


def test_a_kind_whose_file_is_missing_leaves_the_card_off_the_page():
    """``newdata`` skips a kind with no file at all, so with no file built there is nothing to draw."""
    assert control_render._builds({"builds": []}) == ""
    assert control_render._builds({}) == ""


@pytest.mark.parametrize("field", ["kind", "mode"])
def test_the_card_escapes_what_it_prints(field):
    html = control_render._builds({"builds": [_row(**{field: '<script>x</script>'})]})
    assert "<script>x</script>" not in html


def test_the_table_stacks_on_a_phone():
    """``table.stk`` plus a ``data-label`` per cell is the board's own stacking table, so no column scrolls away."""
    html = control_render._builds({"builds": [_row()]})
    assert 'class="stk"' in html
    for label in ("File", "Mode", "Last build", "Parquet", "Last audit round", "Keys owed"):
        assert f'data-label="{label}"' in html, label
