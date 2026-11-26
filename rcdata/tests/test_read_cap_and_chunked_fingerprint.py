"""Every serving read is capped at the door, and a fingerprint that does not fit the cap is taken in parts.

Measured on homesrv, 26 November 2026, which is what these tests pin:

* a ``sec_forms`` pack was OOM-killed at **5.55 GB** anon RSS inside ``backup._table_fingerprints``, because
  ``serving.connect_read`` applied no ``memory_limit`` -- only ``open_read`` did, so every read that came through
  the door itself ran at DuckDB's own default of 80 % of RAM;
* with a **1 GiB** cap, ``filing_note`` hashed in 5.51 s and ``filing_section`` raised ``OutOfMemoryException``
  (16 MiB wanted at 1022.3 MiB of 1 GiB used) having spilled **0 bytes**: a string vector of a 217 kB row cannot
  spill, so the cap alone turns a kill into a raise;
* in **64 parts** under that cap, ``filing_section`` finished in 28.23 s at a 1.32 GiB peak -- faster than the
  53.22 s of the uncapped single pass it replaces -- and every table's count and checksum came out **identical**
  across one pass, 64 parts and 256 parts, capped and uncapped.

``memory_limit`` is a setting of the DuckDB instance, and a process keeps one per path, so the cap cannot belong to
one caller: a ``SET`` on any connection is read by all of them.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest

from revenuechaser.rcdata import backup, serving


def _file(tmp_path: Path, *, wide: int = 0) -> Path:
    """A DuckDB file with a narrow table and, asked for, one whose single row is ``wide`` characters."""
    path = tmp_path / "live.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE narrow AS SELECT i AS a, 's' || i AS b FROM range(500) t(i)")
        if wide:
            con.execute(f"CREATE TABLE wide AS SELECT 1 AS a, repeat('x', {int(wide)}) AS text")
    finally:
        con.close()
    return path


def test_the_door_caps_every_read_and_its_spill(tmp_path, monkeypatch):
    """The cap is applied by ``connect_read``, so a caller that does not go through ``open_read`` has it too."""
    monkeypatch.setenv("RC_DUCKDB_READ_MEMORY_LIMIT", "512MiB")
    monkeypatch.setenv("RC_DUCKDB_READ_MAX_TEMP", "20GB")
    with serving.connect_read(_file(tmp_path)) as con:
        limit, spill = con.execute("SELECT current_setting('memory_limit'), "
                                   "current_setting('max_temp_directory_size')").fetchone()
    assert limit == "512.0 MiB", "a read that comes through the door, not through open_read, is capped too"
    # The spill cap is the smaller of the asked-for size and 90 % of the spill disk's free space, so it is never
    # a cap that lets a read fill the disk it spills on; it is never DuckDB's own "90 % of free space" either.
    free = shutil.disk_usage(tmp_path).free
    assert serving._bytes(spill.replace(" ", "")) <= min(serving._bytes("20GB"), int(free * 0.9)) + 1


def test_a_checksum_taken_in_parts_is_the_same_number(tmp_path):
    """The whole reason to hash in parts rather than per column: the stored fingerprint does not change.

    The sum over ``rowid % n = k`` for every ``k`` is the sum over the table, so no stored fingerprint has to be
    recomputed and ``restore_live`` keeps comparing like with like.
    """
    path = _file(tmp_path, wide=200_000)
    with serving.connect_read(path) as con:
        one_pass = {n: backup._table_checksum(con, n) for n in ("narrow", "wide")}

        class InParts:
            """The capped connection: it refuses the whole table and answers every part."""

            def __init__(self, real):
                self.real, self.refused = real, 0

            def execute(self, sql):
                if "WHERE t.rowid %" not in sql:
                    self.refused += 1
                    raise duckdb.OutOfMemoryException("failed to allocate data of size 16.0 MiB")
                return self.real.execute(sql)

        for name, expected in one_pass.items():
            fake = InParts(con)
            assert backup._table_checksum(fake, name) == expected, f"{name} hashed in parts differs"
            assert fake.refused == 1, "the single pass is tried first, because it is the cheaper read"
        assert one_pass["narrow"][0] == 500 and one_pass["wide"][0] == 1


def test_a_table_that_fits_no_number_of_parts_fails_the_backup(tmp_path):
    """Fail closed: a fingerprint that cannot be taken is never reported as a number, and never as 0."""

    class Never:
        def execute(self, _sql):
            raise duckdb.OutOfMemoryException("failed to allocate data of size 16.0 MiB")

    with pytest.raises(backup.BackupFailed, match=f"{backup.CHECKSUM_PARTS[-1]} parts"):
        backup._table_checksum(Never(), "filing_section")


def test_a_damaged_file_still_raises_rather_than_being_hashed_in_parts(tmp_path):
    """Only ``OutOfMemoryException`` means "does not fit". Another DuckDB error is a damaged file, and the caller
    turns it into a failed copy; retrying it in parts would read a broken block 64 more times and still fail."""

    class Damaged:
        def execute(self, _sql):
            raise duckdb.IOException("Could not read block")

    with pytest.raises(duckdb.IOException):
        backup._table_checksum(Damaged(), "filing_section")
