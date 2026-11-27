"""``rcdata/serving.py``: build a new file, check it, swap it in; read-only opens. T3 is the acceptance test of #206."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from revenuechaser.core import config
from revenuechaser.rcdata import serving


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build(rows: int, *, fail_after_write: bool = False) -> None:
    with serving.build("market") as b:
        b.con.execute("CREATE TABLE t (i INTEGER)")
        b.con.execute(f"INSERT INTO t SELECT range FROM range({rows})")
        if fail_after_write:
            b.con.execute("CHECKPOINT")
            assert b.path.exists()
            raise RuntimeError("the build broke after writing its file")
        b.swap({"t": rows})


def _leftovers() -> list[str]:
    return sorted(p.name for p in Path(config.MARKET_DIR).iterdir()
                  if p.name not in ("market.duckdb", "market.prev.duckdb"))


def test_t3_a_build_that_raises_after_writing_leaves_the_live_file_byte_identical():
    _build(3)
    live = serving.live_path("market")
    before = _sha(live)
    with pytest.raises(RuntimeError, match="broke"):
        _build(5, fail_after_write=True)
    assert _sha(live) == before
    assert _leftovers() == [], "the abandoned build file (or its .wal/.tmp) must not remain"
    with serving.open_read("market") as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 3


@pytest.mark.parametrize("bad", ["count", "version", "kind", "failed_check", "missing_table"])
def test_a_build_that_fails_its_check_is_deleted_and_the_live_file_is_untouched(bad):
    _build(3)
    live = serving.live_path("market")
    before = _sha(live)
    with pytest.raises(serving.SwapRefused):
        with serving.build("market") as b:
            b.con.execute("CREATE TABLE t (i INTEGER)")
            b.con.execute("INSERT INTO t VALUES (1), (2)")
            expected, checks = {"t": 2}, []
            if bad == "count":
                expected = {"t": 3}
            elif bad == "version":
                b.con.execute("UPDATE serving_schema_version SET version = version + 1")
            elif bad == "kind":
                b.con.execute("UPDATE serving_schema_version SET kind = 'other'")
            elif bad == "failed_check":
                checks = [{"dataset": "market_series", "result": "failed"}]
            else:
                expected = {"t": 2, "absent": 0}
            b.swap(expected, checks=checks)
    assert _sha(live) == before
    assert _leftovers() == []


def test_a_swap_keeps_the_previous_file_as_prev():
    _build(3)
    first = _sha(serving.live_path("market"))
    _build(4)
    assert _sha(serving.prev_path("market")) == first
    with serving.open_read("market") as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 4
        assert con.execute("SELECT kind, version FROM serving_schema_version").fetchall() == [
            ("market", serving.SERVING_SCHEMA_VERSION["market"])]
    assert _leftovers() == []


def test_a_build_left_without_a_swap_is_removed():
    _build(3)
    with serving.build("market") as b:
        b.con.execute("CREATE TABLE t (i INTEGER)")
    assert _leftovers() == []


def test_open_read_refuses_to_write():
    _build(2)
    with serving.open_read("market") as con:
        with pytest.raises(duckdb.Error):
            con.execute("INSERT INTO t VALUES (9)")


def test_open_read_caps_the_buffer_pool(monkeypatch):
    """A reader's DuckDB instance holds what it read up to memory_limit; the default of 80 % of RAM OOM-killed the
    relatedness run on 15 Nov 2026, so a read connection is capped (RC_DUCKDB_READ_MEMORY_LIMIT, else 1 GiB)."""
    _build(2)
    monkeypatch.delenv("RC_DUCKDB_READ_MEMORY_LIMIT", raising=False)
    with serving.open_read("market") as con:
        assert con.execute("SELECT current_setting('memory_limit')").fetchone()[0] == "1.0 GiB"
    monkeypatch.setenv("RC_DUCKDB_READ_MEMORY_LIMIT", "512MiB")
    with serving.open_read("market") as con:
        assert con.execute("SELECT current_setting('memory_limit')").fetchone()[0] == "512.0 MiB"
    monkeypatch.setenv("RC_DUCKDB_READ_MEMORY_LIMIT", "lots")          # not a size: the default holds
    assert serving.read_memory_limit() == serving.READ_MEMORY_LIMIT_DEFAULT


def test_open_read_spills_into_its_own_process_directory():
    """DuckDB's default spill directory, ``<file>.tmp``, is shared by every process reading the file and its spill
    file names restart at 0 in each: on 17 Nov 2026 two readers of prices.duckdb crashed inside DuckDB 4 s apart."""
    _build(2)
    live = serving.live_path("market")
    with serving.open_read("market") as con:
        got = con.execute("SELECT current_setting('temp_directory')").fetchone()[0]
        assert got == str(live.with_name(f"market.duckdb.tmp-{os.getpid()}"))
        assert got != str(live) + ".tmp"
        # A second open of the same path while the first is open shares its instance: same configuration, no error.
        assert serving.live_stamp("market") is not None
        with serving.open_read("market") as again:
            assert again.execute("SELECT count(*) FROM t").fetchone()[0] == 2


def test_with_the_ssd_temp_root_set_a_reader_spills_under_it(tmp_path, monkeypatch):
    """avo 17 Nov 2026: one temp root per disk. ``RC_TMP_DIR`` (homesrv: /srv/tmp/rc) takes the per-process spill
    out of the market folder; a hash of the file's folder keeps two same-named files of one process apart (two
    DuckDB instances on one spill folder is the 17 Nov crash)."""
    monkeypatch.setenv("RC_TMP_DIR", str(tmp_path / "ssdtmp"))
    a = serving.read_spill_dir(tmp_path / "one" / "market.duckdb")
    b = serving.read_spill_dir(tmp_path / "two" / "market.duckdb")
    assert a.parent == b.parent == tmp_path / "ssdtmp" / "duckdb-read" and a.parent.is_dir()
    assert a != b and a.name.startswith("market.duckdb.") and a.name.endswith(f".tmp-{os.getpid()}")
    assert serving.stale_spill(a.parent / a.name.replace(f".tmp-{os.getpid()}", ".tmp-999999999")) is False  # no dir


def test_scratch_dir_is_the_hdd_temp_root_when_set_else_the_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("RC_TMP_HDD_DIR", raising=False)
    assert serving.scratch_dir("13f_sets", tmp_path / "raw") == tmp_path / "raw"
    assert serving.scratch_dir("restore-check", None) is None
    monkeypatch.setenv("RC_TMP_HDD_DIR", str(tmp_path / "hddtmp"))
    got = serving.scratch_dir("13f_sets", tmp_path / "raw")
    assert got == tmp_path / "hddtmp" / "13f_sets" and got.is_dir()


def test_open_read_resolves_the_path_on_every_call(tmp_path, monkeypatch):
    _build(2)
    with serving.open_read("market") as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 2
    monkeypatch.setattr(config, "MARKET_DIR", tmp_path / "elsewhere")
    with pytest.raises(serving.ServingFileMissing):
        serving.open_read("market")


def test_build_paths_and_unknown_kinds():
    assert serving.build_path("market", "b1") == Path(config.MARKET_DIR) / "market.b1.duckdb"
    with pytest.raises(ValueError):
        serving.live_path("nope")


def _settings(con) -> tuple[str, int]:
    return (con.execute("SELECT current_setting('memory_limit')").fetchone()[0],
            con.execute("SELECT current_setting('threads')").fetchone()[0])


def _limit_bytes(con) -> int:
    return serving._bytes(con.execute("SELECT current_setting('memory_limit')").fetchone()[0])


def test_a_build_connection_is_capped_by_default(monkeypatch):
    """#319's OOM: the build connection must not take DuckDB's default 80 % of RAM, nor every core. With no
    variable set the cap follows the machine (``auto_memory_limit``), here a stand-in 10 GiB available."""
    monkeypatch.delenv("RC_DUCKDB_MEMORY_LIMIT", raising=False)
    monkeypatch.delenv("RC_DUCKDB_THREADS", raising=False)
    monkeypatch.setattr(serving, "available_memory", lambda: 10 * 2**30)
    with serving.build("market") as b:
        got, threads = _limit_bytes(b.con), b.con.execute("SELECT current_setting('threads')").fetchone()[0]
    want = int(10 * 2**30 * serving.MEMORY_SHARE_DEFAULT)
    assert abs(got - want) / want < 0.02, got
    assert threads == serving.THREADS_DEFAULT


def _meminfo(tmp_path, available_kb: int | None) -> None:
    text = "MemTotal:       16305236 kB\nMemFree:          812344 kB\n"
    if available_kb is not None:
        text += f"MemAvailable:   {available_kb} kB\n"
    (tmp_path / "meminfo").write_text(text + "Buffers:          123456 kB\n")


def test_meminfo_available_is_read_in_bytes(tmp_path, monkeypatch):
    """The machine's own answer to "is there room": MemAvailable, in kB, which the builder needs in bytes."""
    _meminfo(tmp_path, 10_485_760)
    monkeypatch.setattr(serving, "MEMINFO_PATH", tmp_path / "meminfo")
    assert serving._meminfo_available() == 10 * 2**30


@pytest.mark.parametrize("broken", ["MemAvailable: lots kB\n", "MemTotal: 1 kB\n", ""])
def test_meminfo_that_cannot_be_read_is_not_a_number(tmp_path, monkeypatch, broken):
    (tmp_path / "meminfo").write_text(broken)
    monkeypatch.setattr(serving, "MEMINFO_PATH", tmp_path / "meminfo")
    assert serving._meminfo_available() is None
    monkeypatch.setattr(serving, "MEMINFO_PATH", tmp_path / "gone")        # not even a file
    assert serving._meminfo_available() is None


def _cgroup(tmp_path, levels: dict[str, dict[str, str]]) -> Path:
    """A cgroup v2 tree under ``tmp_path``: ``levels`` maps a relative folder ("" is the root) to its files."""
    root = tmp_path / "cgroup"
    for rel, files in levels.items():
        folder = root / rel if rel else root
        folder.mkdir(parents=True, exist_ok=True)
        for name, value in files.items():
            (folder / name).write_text(value)
    return root


def test_the_cgroup_headroom_is_the_tightest_limit_above_the_process(tmp_path, monkeypatch):
    """homesrv runs the builder under a systemd MemoryMax, so free host RAM alone is a limit the cgroup kills the
    build for taking. A limit on a parent slice binds the child, so every level up to the root is read."""
    root = _cgroup(tmp_path, {"": {"memory.max": "max", "memory.current": "1000000000"},
                              "life.slice": {"memory.max": "8000000000", "memory.current": "3000000000"},
                              "life.slice/rc-builder.service": {"memory.max": "max",
                                                                "memory.current": "1000000000"}})
    (tmp_path / "self-cgroup").write_text("0::/life.slice/rc-builder.service\n")
    monkeypatch.setattr(serving, "CGROUP_ROOT", root)
    monkeypatch.setattr(serving, "PROC_CGROUP_PATH", tmp_path / "self-cgroup")
    assert serving._cgroup_dir() == root / "life.slice/rc-builder.service"
    assert serving._cgroup_headroom() == 5_000_000_000                     # 8 GB - 3 GB on the slice


def test_memory_high_counts_as_a_limit_and_no_limit_reads_as_none(tmp_path, monkeypatch):
    """Past ``memory.high`` the kernel throttles and reclaims: that is where a build goes from slow to killed."""
    root = _cgroup(tmp_path, {"": {"memory.max": "max", "memory.high": "4000000000",
                                   "memory.current": "1500000000"}})
    monkeypatch.setattr(serving, "CGROUP_ROOT", root)
    monkeypatch.setattr(serving, "PROC_CGROUP_PATH", tmp_path / "no-such-file")
    assert serving._cgroup_headroom() == 2_500_000_000
    _cgroup(tmp_path, {"": {"memory.max": "max", "memory.high": "max", "memory.current": "1500000000"}})
    assert serving._cgroup_headroom() is None


def test_available_memory_takes_the_smaller_of_the_two(tmp_path, monkeypatch):
    monkeypatch.setattr(serving, "_meminfo_available", lambda: 10 * 2**30)
    monkeypatch.setattr(serving, "_cgroup_headroom", lambda: 3 * 2**30)
    assert serving.available_memory() == 3 * 2**30
    monkeypatch.setattr(serving, "_cgroup_headroom", lambda: None)
    assert serving.available_memory() == 10 * 2**30
    monkeypatch.setattr(serving, "_meminfo_available", lambda: None)
    assert serving.available_memory() is None


def test_the_limit_follows_the_free_memory_between_a_floor_and_a_cap(monkeypatch):
    """avo 19 Nov 2026: "Yer varsa artırsa yoksa azaltsa". More when the box is quiet, less when it is not; the
    floor is safe because DuckDB spills past its limit instead of failing."""
    for var in ("RC_DUCKDB_MEMORY_SHARE", "RC_DUCKDB_MEMORY_FLOOR", "RC_DUCKDB_MEMORY_CAP"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(serving, "_cgroup_headroom", lambda: None)         # a box with no cgroup limit on it
    monkeypatch.setattr(serving, "available_memory", lambda: 10 * 2**30)
    assert serving.auto_memory_limit() == "6442MB"                         # 60 % of 10 GiB
    monkeypatch.setattr(serving, "available_memory", lambda: 1 * 2**30)    # a busy box: the floor
    assert serving.auto_memory_limit() == "2000MB"
    monkeypatch.setattr(serving, "available_memory", lambda: 60 * 2**30)   # a quiet one: the cap
    assert serving.auto_memory_limit() == "12000MB"
    monkeypatch.setattr(serving, "available_memory", lambda: None)         # not Linux, or no /proc
    assert serving.auto_memory_limit() == serving.MEMORY_LIMIT_DEFAULT


@pytest.mark.parametrize("share, floor, cap, expected", [("0.25", "", "", "2684MB"),
                                                         ("", "6GB", "", "6442MB"),
                                                         ("0.9", "", "4GB", "4000MB"),
                                                         ("3", "", "", "6442MB"),      # not a share: the default
                                                         ("much", "nope", "nope", "6442MB"),
                                                         ("0.1", "5GB", "3GB", "5000MB")])  # floor wins over a cap
def test_the_share_the_floor_and_the_cap_come_from_the_environment(monkeypatch, share, floor, cap, expected):
    monkeypatch.setenv("RC_DUCKDB_MEMORY_SHARE", share)
    monkeypatch.setenv("RC_DUCKDB_MEMORY_FLOOR", floor)
    monkeypatch.setenv("RC_DUCKDB_MEMORY_CAP", cap)
    monkeypatch.setattr(serving, "_cgroup_headroom", lambda: None)         # the cgroup clamp is its own test
    monkeypatch.setattr(serving, "available_memory", lambda: 10 * 2**30)
    assert serving.auto_memory_limit() == expected


def test_the_floor_never_raises_the_limit_above_what_the_cgroup_allows(monkeypatch):
    """A ``memory_limit`` the size of the cgroup the process runs in is one the kernel cannot honour:
    ``memory_limit`` counts no Python, Arrow or gzip memory, so a step that did need to spill would be ended
    first. Read on homesrv 27 Nov 2026: under ``life-scripts.slice``'s ``MemoryMax=3G`` the floor handed a step
    ``2000MB`` where 60 % of the headroom was about 1680MB. This is hygiene, not the fix for an observed kill:
    the ``wrds/prices`` kill of 01:27 that same night proved to be elsewhere."""
    for var in ("RC_DUCKDB_MEMORY_SHARE", "RC_DUCKDB_MEMORY_FLOOR", "RC_DUCKDB_MEMORY_CAP", "RC_DUCKDB_MEMORY_MIN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(serving, "_meminfo_available", lambda: 10 * 2**30)  # the box is quiet
    monkeypatch.setattr(serving, "_cgroup_headroom", lambda: 2_800_000_000)  # the slice is not
    assert serving.auto_memory_limit() == "1680MB"                          # 60 % of the headroom, not the 2GB floor


def test_a_cgroup_tighter_than_the_minimum_still_gets_a_workable_limit(monkeypatch):
    """The clamp stops at ``MEMORY_MIN_DEFAULT``: a nearly full cgroup would otherwise be given a limit DuckDB
    cannot plan a single join under, and the step must fail on its own terms rather than on a 0 MB buffer pool."""
    for var in ("RC_DUCKDB_MEMORY_SHARE", "RC_DUCKDB_MEMORY_FLOOR", "RC_DUCKDB_MEMORY_CAP", "RC_DUCKDB_MEMORY_MIN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(serving, "_meminfo_available", lambda: 10 * 2**30)
    monkeypatch.setattr(serving, "_cgroup_headroom", lambda: 10_000_000)    # 10 MB left in the cgroup
    assert serving.auto_memory_limit() == "256MB"


def test_a_set_memory_limit_still_wins_over_the_machine(monkeypatch):
    """``RC_DUCKDB_MEMORY_LIMIT`` is the manual override: a build under it reads no meminfo and no cgroup."""
    monkeypatch.setenv("RC_DUCKDB_MEMORY_LIMIT", "7GB")
    monkeypatch.setattr(serving, "available_memory", lambda: pytest.fail("the machine was read anyway"))
    assert serving.build_config()["memory_limit"] == "7GB"


def test_the_cap_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("RC_DUCKDB_MEMORY_LIMIT", "2GB")
    monkeypatch.setenv("RC_DUCKDB_THREADS", "2")
    monkeypatch.setenv("RC_DUCKDB_MAX_TEMP", "50GB")
    _free_space(monkeypatch, 10**15)          # a CI runner has less than 50 GB free; the cap is the variable's here
    with serving.build("market") as b:
        memory, threads = _settings(b.con)
        max_temp = b.con.execute("SELECT current_setting('max_temp_directory_size')").fetchone()[0]
    assert memory.replace(" ", "") in ("1.8GiB", "2.0GB"), memory
    assert threads == 2
    assert max_temp.replace(" ", "") in ("46.5GiB", "50.0GB"), max_temp


@pytest.mark.parametrize("memory, threads, max_temp",
                         [("", "", ""), ("lots", "x", "much"), ("5", "0", "200"), ("GB", "-3", "TB")])
def test_an_empty_or_invalid_cap_keeps_the_default(monkeypatch, memory, threads, max_temp):
    monkeypatch.setenv("RC_DUCKDB_MEMORY_LIMIT", memory)
    monkeypatch.setenv("RC_DUCKDB_THREADS", threads)
    monkeypatch.setenv("RC_DUCKDB_MAX_TEMP", max_temp)
    monkeypatch.setattr(serving, "available_memory", lambda: None)      # no machine to follow: the fallback
    assert serving.build_config() == {"memory_limit": serving.MEMORY_LIMIT_DEFAULT,
                                      "threads": serving.THREADS_DEFAULT,
                                      "max_temp_directory_size": serving.MAX_TEMP_DEFAULT}


def _free_space(monkeypatch, free: int) -> None:
    monkeypatch.setattr(serving.shutil, "disk_usage", lambda p: SimpleNamespace(free=free))


@pytest.mark.parametrize("max_temp, free, expected", [("200GB", 10**15, "200GB"),
                                                      ("200GB", 50 * 10**9, "45000000KB"),
                                                      ("200GiB", 100 * 10**9, "90000000KB"),
                                                      ("1KB", 0, "0KB")])
def test_379_the_spill_cap_never_exceeds_90_percent_of_the_spill_disks_free_space(monkeypatch, tmp_path, max_temp,
                                                                                  free, expected):
    """#379: a 200 GB cap on an SSD with 50 GB free would let a spill fill the disk the live stores share."""
    monkeypatch.setenv("RC_DUCKDB_MAX_TEMP", max_temp)
    _free_space(monkeypatch, free)
    assert serving.build_config(tmp_path)["max_temp_directory_size"] == expected
    assert serving.build_config()["max_temp_directory_size"] == max_temp


def test_379_a_build_opens_with_the_cap_held_to_the_free_space(monkeypatch):
    _free_space(monkeypatch, 50 * 10**9)
    monkeypatch.delenv("RC_DUCKDB_MAX_TEMP", raising=False)
    with serving.build("market") as b:
        max_temp = b.con.execute("SELECT current_setting('max_temp_directory_size')").fetchone()[0]
    assert max_temp.replace(" ", "") in ("41.9GiB", "45.0GB"), max_temp


def test_a_build_over_its_memory_limit_spills_on_the_raw_disk_and_leaves_no_scratch(monkeypatch):
    """Under a small limit a sort larger than it still finishes, and the spill directory goes with the build. #372:
    the spill lives under the raw root (the server's HDD), not beside the live files: request 71 spilled 47 GB
    there, on the SSD the live stores share."""
    monkeypatch.setenv("RC_DUCKDB_MEMORY_LIMIT", "64MB")
    monkeypatch.setenv("RC_DUCKDB_THREADS", "1")
    rows = 3_000_000
    with serving.build("market") as b:
        spill = Path(b.con.execute("SELECT current_setting('temp_directory')").fetchone()[0])
        b.con.execute(f"CREATE TABLE t AS SELECT range AS i, md5(range::VARCHAR) AS h FROM range({rows}) ORDER BY h")
        b.swap({"t": rows})
    assert Path(config.MARKET_RAW_DIR) in spill.parents, spill
    assert not spill.exists() and _leftovers() == []


def test_rc_duckdb_temp_dir_moves_the_spill_and_unset_keeps_the_raw_root(monkeypatch, tmp_path):
    """#654 review: the spill folder can move (to the SSD, once a logged peak says it fits); the default is unchanged."""
    monkeypatch.setenv("RC_DUCKDB_TEMP_DIR", str(tmp_path / "ssd_tmp"))
    with serving.build("market") as b:
        spill = Path(b.con.execute("SELECT current_setting('temp_directory')").fetchone()[0])
    assert spill.parent == tmp_path / "ssd_tmp" and spill.name == f"{b.path.name}.tmp"
    monkeypatch.setenv("RC_DUCKDB_TEMP_DIR", " ")
    assert serving.spill_dir(Path("m.duckdb")) == Path(config.MARKET_RAW_DIR) / "build_tmp" / "m.duckdb.tmp"


def _build_t(rows: int, **swap_kw) -> None:
    with serving.build("market") as b:
        b.con.execute(f"CREATE TABLE t AS SELECT range AS i FROM range({rows})")
        b.swap({"t": rows}, **swap_kw)


@pytest.mark.parametrize("rows", [0, 9])
def test_b2_a_table_that_empties_or_shrinks_against_the_live_file_is_refused(rows):
    """B2: the expected counts come from the build itself, so they cannot catch a build from a missing Parquet
    tree; the live file is the reference."""
    _build_t(10)
    before = _sha(serving.live_path("market"))
    with pytest.raises(serving.SwapRefused, match="shrinks|empties"):
        _build_t(rows)
    assert _sha(serving.live_path("market")) == before and _leftovers() == []


def test_b2_a_table_the_live_file_has_must_be_in_the_build():
    _build_t(10)
    with pytest.raises(serving.SwapRefused, match="missing"):
        with serving.build("market") as b:
            b.con.execute("CREATE TABLE other (i INTEGER)")
            b.swap({"other": 0})


def test_b2_a_shrink_is_allowed_only_when_asked_for():
    _build_t(10)
    _build_t(0, allow_shrink=("t",))
    with serving.open_read("market") as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 0
    _build_t(11)                                   # growing is always fine


def test_a_shrink_under_the_limit_swaps_in_and_leaves_a_build_issue():
    """#292 N-3: 2,220 of 222,009 SPX rows went in without a trace. A shrink under MAX_SHRINK still swaps in, and
    now leaves one open ``build_issues`` row naming the table and both counts; growing leaves none."""
    from revenuechaser.rcdata import ops
    _build_t(1000)
    _build_t(1001)
    assert ops.open_issues("market")[0] == 0
    _build_t(995)
    with serving.open_read("market") as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 995
    n, rows = ops.open_issues("market")
    assert n == 1 and rows[0]["kind"] == "shrink" and rows[0]["key"] == "t" and "1001 -> 995" in rows[0]["detail"]
    _build_t(990)                                  # shrinks again: still one open row, no flood
    assert ops.open_issues("market")[0] == 1


def _build_window(days: list[str], rows_per: int = 10, **swap_kw) -> None:
    """A windowed table (``option_eod``'s shape) holding ``rows_per`` rows on each of ``days``, its window
    declared from the days it found, as ``options/tables._windowed`` declares it from the partitions it found."""
    with serving.build("market") as b:
        b.con.execute("CREATE TABLE w (session_date DATE, i INTEGER)")
        for day in days:
            b.con.execute(f"INSERT INTO w SELECT CAST(? AS DATE), range FROM range({int(rows_per)})", [day])
        serving.declare_window(b.con, "w", "session_date", min(days))
        b.swap({"w": len(days) * rows_per}, **swap_kw)


def _days(first: int, n: int) -> list[str]:
    return [f"2026-11-{d:02d}" for d in range(first, first + n)]


def test_n4_a_window_read_from_the_partitions_found_cannot_replace_20_sessions_with_1():
    """#292 N-4: the window comes from the Parquet present, and both files are counted inside the build's window,
    so a build that found one session matched the live file row for row and swapped 20 sessions away. The window
    itself is compared now."""
    _build_window(_days(1, 20))
    before = _sha(serving.live_path("market"))
    with pytest.raises(serving.SwapRefused, match="session_date value"):
        _build_window(_days(20, 1))
    assert _sha(serving.live_path("market")) == before and _leftovers() == []
    with serving.open_read("market") as con:
        assert con.execute("SELECT count(DISTINCT session_date) FROM w").fetchone()[0] == 20


def test_n4_a_window_that_rolls_forward_by_a_session_still_swaps_in():
    """The guard is on the window's length, not its first day: the newest 20 sessions replace the newest 20."""
    _build_window(_days(1, 20))
    _build_window(_days(2, 20))
    with serving.open_read("market") as con:
        first, n = con.execute("SELECT CAST(min(session_date) AS TEXT), count(DISTINCT session_date) "
                               "FROM w").fetchone()
    assert (first, n) == ("2026-11-02", 20)


def test_n4_a_shorter_window_goes_in_when_the_request_asks_for_it():
    """A window the code shortened on purpose is a shrink like any other: ``allow_shrink`` on that table."""
    _build_window(_days(1, 20))
    _build_window(_days(20, 1), allow_shrink=("w",))
    with serving.open_read("market") as con:
        assert con.execute("SELECT count(DISTINCT session_date) FROM w").fetchone()[0] == 1


def test_a_table_that_shrinks_by_choice_may_shrink_without_allow_shrink_but_may_not_empty():
    """``SHRINKS_BY_CHOICE``: the source or avo chooses the row count, so a smaller one is not a partial build.
    A request-wide ``allow_shrink`` is not needed for it (it would relax every other table of the kind with it),
    and the "empties" guard still holds."""
    for table in serving.SHRINKS_BY_CHOICE:
        with serving.build("market") as b:
            b.con.execute(f'CREATE TABLE "{table}" AS SELECT range AS i FROM range(100)')
            b.swap({table: 100})
        with serving.build("market") as b:                      # -90 %, far past MAX_SHRINK, no allow_shrink
            b.con.execute(f'CREATE TABLE "{table}" AS SELECT range AS i FROM range(10)')
            b.swap({table: 10})
        with serving.open_read("market") as con:
            assert con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == 10
        with pytest.raises(serving.SwapRefused, match="empties"):
            with serving.build("market") as b:
                b.con.execute(f'CREATE TABLE "{table}" (i INTEGER)')
                b.swap({table: 0})
        serving.live_path("market").unlink()


def test_the_economic_calendar_shrinks_by_choice_because_its_window_rolls():
    """RC-Build on homesrv failed every hour from 00:05 UTC on 14 Nov 2026: ``uw/economic_calendar`` served 114 rows
    against 126 live (-9.5 %), because a snapshot day's partition is replaced whole by that day's newest fetch and
    events have rolled out of UW's "this week and next" window since. One refused swap fails the whole ``market``
    kind (one file, one swap), so the guard cannot be left to a retry."""
    from revenuechaser.rcdata.build import uw_economic_calendar as econ
    assert econ.TABLE in serving.SHRINKS_BY_CHOICE


def test_a_retired_table_may_leave_the_build_and_any_other_still_may_not(monkeypatch):
    """Review M2 of #382: PR 382 drops ``prices``' ``crsp_unadjusted`` table on purpose, and the live file still holds
    it. The "every live table must be in the build" guard refused that build even with ``allow_shrink``; a table the
    code retired by name (``RETIRED_TABLES``) may now leave, and any other missing table is refused as before."""
    monkeypatch.setitem(serving.RETIRED_TABLES, "market", ("old",))
    with serving.build("market") as b:
        b.con.execute("CREATE TABLE t AS SELECT range AS i FROM range(10)")
        b.con.execute("CREATE TABLE old AS SELECT range AS i FROM range(5)")
        b.con.execute("CREATE TABLE gone AS SELECT range AS i FROM range(5)")
        b.swap({"t": 10, "old": 5, "gone": 5})
    with pytest.raises(serving.SwapRefused, match="table gone of the live file is missing"):
        _build_t(10)                                   # neither old nor gone: gone is no retired table
    with serving.build("market") as b:
        b.con.execute("CREATE TABLE t AS SELECT range AS i FROM range(10)")
        b.con.execute("CREATE TABLE gone AS SELECT range AS i FROM range(5)")
        b.swap({"t": 10, "gone": 5})                   # old, the retired one, is absent: accepted
    with serving.open_read("market") as con:
        names = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    assert "old" not in names and {"t", "gone"} <= names


def test_prices_retires_the_crsp_unadjusted_table_of_pr_353():
    """PR 382 removed ``crsp_unadjusted`` (the CRSP bars no action adjusted): CRSP serves no bar any more."""
    from revenuechaser.rcdata.build.prices import serving as prices_serving
    assert "crsp_unadjusted" in serving.RETIRED_TABLES["prices"]
    assert not set(serving.RETIRED_TABLES["prices"]) & set(prices_serving.SCHEMAS), "a retired table is still built"


# ── base="live": the build file starts as a copy of the live one (PR 1 of the incremental plan) ─────────────────

def _mode(con) -> str:
    return con.execute("SELECT build_mode FROM serving_schema_version").fetchone()[0]


def test_a_live_based_build_starts_as_a_copy_and_appends_to_it():
    """The point of the mode: the rows already served are in the build file, so a build may add only what changed."""
    _build_t(10)
    first = _sha(serving.live_path("market"))
    with serving.build("market", base="live") as b:
        assert b.mode == "live"
        assert b.con.execute("SELECT count(*) FROM t").fetchone()[0] == 10, "the live rows are not in the copy"
        b.con.execute("INSERT INTO t SELECT range + 10 FROM range(5)")
        b.swap({"t": 15})
    with serving.open_read("market") as con:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 15
        assert _mode(con) == "live"
        assert con.execute("SELECT kind, version FROM serving_schema_version").fetchall() == [
            ("market", serving.SERVING_SCHEMA_VERSION["market"])], "the copied version row must be replaced"
    assert _sha(serving.prev_path("market")) == first, "the rollback file is still the file that was live"
    assert _leftovers() == []


def test_a_live_based_build_is_fresh_when_there_is_no_live_file():
    with serving.build("market", base="live") as b:
        assert b.mode == "fresh"
        b.con.execute("CREATE TABLE t AS SELECT range AS i FROM range(3)")
        b.swap({"t": 3})
    with serving.open_read("market") as con:
        assert _mode(con) == "fresh"


def test_a_live_file_of_another_serving_schema_version_is_not_appended_to(monkeypatch):
    """A version bump changes which tables the code builds, so its first build must be a whole one."""
    _build_t(10)
    monkeypatch.setitem(serving.SERVING_SCHEMA_VERSION, "market", serving.SERVING_SCHEMA_VERSION["market"] + 1)
    with serving.build("market", base="live") as b:
        assert b.mode == "fresh"
        tables = {r[0] for r in b.con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        assert "t" not in tables, "nothing of the live file may be copied into a build of another version"


def test_a_live_based_build_keeps_the_shrink_guard_and_the_rollback():
    _build_t(10)
    before = _sha(serving.live_path("market"))
    with pytest.raises(serving.SwapRefused, match="shrinks"):
        with serving.build("market", base="live") as b:
            b.con.execute("DELETE FROM t WHERE i < 5")
            b.swap({"t": 5})
    assert _sha(serving.live_path("market")) == before and _leftovers() == []


def test_an_unknown_base_is_refused():
    with pytest.raises(ValueError, match="unknown build base"):
        with serving.build("market", base="incremental"):
            pass
    assert not Path(config.MARKET_DIR).exists(), "the refusal comes before any file is made"


def test_a_live_file_without_the_build_mode_column_gets_it_in_the_copy():
    """Why this needs no SERVING_SCHEMA_VERSION bump: a file built before the column is upgraded, not refused."""
    live = serving.live_path("market")
    live.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(live))
    con.execute(f"CREATE TABLE {serving.VERSION_TABLE} (kind TEXT, version INTEGER, built_at DOUBLE, "
                "build_id TEXT)")                                  # the four columns of before build_mode
    con.execute(f"INSERT INTO {serving.VERSION_TABLE} VALUES ('market', ?, 0, 'old')",
                [serving.SERVING_SCHEMA_VERSION["market"]])
    con.execute("CREATE TABLE t AS SELECT range AS i FROM range(10)")
    con.execute("CHECKPOINT")
    con.close()
    with serving.build("market", base="live") as b:
        assert b.mode == "live", "an older live file of the same version is still copied"
        b.con.execute("INSERT INTO t SELECT range + 10 FROM range(5)")
        b.swap({"t": 15})
    with serving.open_read("market") as con:
        assert _mode(con) == "live"
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 15


def test_a_copy_that_breaks_leaves_no_partial_build_file(monkeypatch):
    """A half-copied 2.9 GB file on the live files' own SSD is what a failed copy must not leave behind."""
    _build_t(10)
    before = _sha(serving.live_path("market"))

    def no_space(src, dst):
        Path(dst).write_bytes(b"half a file")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(serving.shutil, "copy2", no_space)
    with pytest.raises(OSError, match="No space"):
        with serving.build("market", base="live"):
            pass
    assert _leftovers() == [], "the partial copy must go with the failure"
    assert _sha(serving.live_path("market")) == before


def test_the_rollback_copy_lives_under_prev_dir_not_beside_the_live_file():
    _build(3)
    first = _sha(serving.live_path("market"))
    _build(4)
    assert serving.prev_path("market").parent == Path(config.MARKET_RAW_DIR) / "serving_prev"
    assert _sha(serving.prev_path("market")) == first
    assert not (Path(config.MARKET_DIR) / "market.prev.duckdb").exists()


def test_a_build_does_not_start_without_room_for_twice_the_live_file(monkeypatch):
    _build(3)
    live = serving.live_path("market")
    before = _sha(live)
    size = live.stat().st_size
    monkeypatch.setattr(serving.shutil, "disk_usage", lambda p: SimpleNamespace(total=0, used=0, free=2 * size - 1))
    with pytest.raises(serving.DiskTooFull, match="twice the live file"):
        _build(4)
    assert _sha(live) == before
    assert _leftovers() == []
    monkeypatch.setenv("RC_BUILD_MIN_FREE", "1TB")
    monkeypatch.setattr(serving.shutil, "disk_usage", lambda p: SimpleNamespace(total=0, used=0, free=10**11))
    with pytest.raises(serving.DiskTooFull):
        _build(4)


# ── A build step's own in-memory connection (#1098) ──────────────────────────────────────────────────────────────

def test_a_scratch_connection_is_capped_like_the_build_and_spills(tmp_path, monkeypatch):
    """A bare ``duckdb.connect()`` has no limit and no spill folder, so a step that outgrows the machine is killed
    by the kernel rather than spilling: ``connect_scratch`` gives it the build's adaptive limit and a folder."""
    monkeypatch.setenv("RC_TMP_HDD_DIR", str(tmp_path / "hdd"))
    monkeypatch.delenv("RC_DUCKDB_SCRATCH_MEMORY_LIMIT", raising=False)
    monkeypatch.delenv("RC_DUCKDB_MEMORY_LIMIT", raising=False)
    monkeypatch.setattr(serving, "available_memory", lambda: 10 * 2**30)
    with serving.connect_scratch() as one, serving.connect_scratch() as two:
        first = one.execute("SELECT current_setting('temp_directory')").fetchone()[0]
        second = two.execute("SELECT current_setting('temp_directory')").fetchone()[0]
        want = int(10 * 2**30 * serving.MEMORY_SHARE_DEFAULT)
        assert abs(_limit_bytes(one) - want) / want < 0.02
        # Two instances on one spill folder write over each other's blocks (the 17 Nov 2026 crashes).
        assert first != second
        assert Path(first).parent == tmp_path / "hdd" / "duckdb-scratch"
        assert Path(first).name.endswith(f".tmp-{os.getpid()}")


def test_a_scratch_connections_cap_can_be_set_on_its_own(monkeypatch):
    monkeypatch.setenv("RC_DUCKDB_SCRATCH_MEMORY_LIMIT", "512MB")
    assert serving.scratch_memory_limit() == "512MB"
    monkeypatch.setenv("RC_DUCKDB_SCRATCH_MEMORY_LIMIT", "plenty")        # not a size: the machine again
    monkeypatch.setattr(serving, "available_memory", lambda: 10 * 2**30)
    assert serving.scratch_memory_limit() == serving.auto_memory_limit()


def test_a_scratch_file_connection_is_capped_and_spills_beside_its_file(tmp_path, monkeypatch):
    """#1100: the quarterly SEC set readers type a whole zip into a scratch database on a file. A plain
    ``duckdb.connect(path)`` caps that no better than the in-memory one, so ``connect_scratch_file`` gives it the
    same adaptive limit and a spill folder of its own, beside the file."""
    monkeypatch.delenv("RC_DUCKDB_SCRATCH_MEMORY_LIMIT", raising=False)
    monkeypatch.delenv("RC_DUCKDB_MEMORY_LIMIT", raising=False)
    monkeypatch.setattr(serving, "available_memory", lambda: 10 * 2**30)
    path = tmp_path / "set.duckdb"
    with serving.connect_scratch_file(path) as con:
        want = int(10 * 2**30 * serving.MEMORY_SHARE_DEFAULT)
        assert abs(_limit_bytes(con) - want) / want < 0.02
        spill = Path(con.execute("SELECT current_setting('temp_directory')").fetchone()[0])
        assert spill == tmp_path / "set.duckdb.spill" and spill.is_dir()
        # It is a database on that file, not an in-memory one.
        con.execute("CREATE TABLE t AS SELECT 1 AS n")
    assert path.exists()


def test_a_scratch_file_connection_takes_a_cap_of_its_own(tmp_path, monkeypatch):
    """``nport`` reads 5.6M holding rows under a deliberate 1 GB, so it spills rather than take the machine's
    share on a box that happens to be idle."""
    monkeypatch.setattr(serving, "available_memory", lambda: 10 * 2**30)
    with serving.connect_scratch_file(tmp_path / "set.duckdb", "1GB") as con:
        # DuckDB reports the limit it rounded to its own units (999,922,073 B for 1 GB), not the string as sent.
        assert abs(_limit_bytes(con) - 10**9) / 10**9 < 0.01


def test_a_killed_processes_scratch_folder_is_swept(tmp_path, monkeypatch):
    monkeypatch.setenv("RC_TMP_HDD_DIR", str(tmp_path / "hdd"))
    root = tmp_path / "hdd" / "duckdb-scratch"
    root.mkdir(parents=True)
    dead, mine = root / "scratch-7.tmp-999999999", root / f"scratch-7.tmp-{os.getpid()}"
    for folder in (dead, mine):
        folder.mkdir()
    assert serving.scratch_spill_dir().parent == root
    assert not dead.exists() and mine.exists()                           # only a process that is gone
