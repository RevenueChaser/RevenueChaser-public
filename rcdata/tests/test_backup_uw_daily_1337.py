"""``uw-raw-daily`` and the backup's own freshness number (#1337).

The UW raw backup is weekly, so on 21 Nov 2026 it held nothing newer than 15 Nov while `raw/uw/option_list` was
filled to 20 Nov: five sessions in no backup at all, of a source that ends on 9 Dec 2026 and serves no history
(#1283). A weekly step that runs is a step that passed, so nothing said so."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from RevenueChaser.core import config
from RevenueChaser.rcdata import backup


def _file(path: Path, data: bytes, age_s: float = 3600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    t = time.time() - age_s
    os.utime(path, (t, t))


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    d = tmp_path / "backups"
    monkeypatch.setattr(config, "RAW_STORE_BACKUP_DIR", str(d))
    return d / backup.ROOT


@pytest.fixture
def trees(tmp_path, monkeypatch):
    """The three trees the step copies: the UW raw folder, the UW Parquet folder and the SPX Gamma tree."""
    from RevenueChaser.module_spx_gamma import config as spx_config
    uw = config.MARKET_RAW_DIR / "raw" / "uw"
    parquet = config.MARKET_RAW_DIR / "parquet" / "uw"
    spx = tmp_path / "spx_gamma"
    monkeypatch.setattr(spx_config, "TREE_ROOT", spx)
    _file(uw / "option_list" / "2026-11-20" / "list.json.gz", b"a" * 20)
    _file(parquet / "option_list" / "session=2026-11-20" / "part-0.parquet", b"p" * 40)
    _file(spx / "spx_gamma_gex_history.json", b'{"days": [1]}')
    return uw, parquet, spx


def _mf(step_dir: Path) -> dict:
    return json.loads((step_dir / backup.MANIFEST_NAME).read_text(encoding="utf-8"))


def _day(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def test_the_daily_step_is_a_daily_step_and_never_runs_in_the_weekly_pass():
    """It is picked by ``--only uw-raw-daily`` alone, like ``watchlists-daily``: the weekly job must not start a
    second copy of the same trees every Sunday."""
    assert backup.STEP_UW_RAW_DAILY == "uw-raw-daily"
    assert backup.STEP_UW_RAW_DAILY in backup.DAILY_STEPS and backup.STEP_UW_RAW_DAILY not in backup.STEPS
    assert backup._check_only("uw-raw-daily") == (("uw-raw-daily",), ())
    assert backup._check_only(None)[0] == backup.STEPS           # the default pass is unchanged
    assert backup.KEEP_UW_DAILY == 14 and backup.BEHIND_WARN_DAYS == 1


def test_a_daily_run_writes_one_folder_a_day_into_the_weekly_steps_folder(backup_dir, trees):
    """One folder per ISO date, beside the weekly ones, so the restore path and the manifest stay the one record."""
    uw, _, _ = trees
    summary = backup.run_backup(only="uw-raw-daily")["uw-raw-daily"]
    today = backup._iso_day()
    out = backup_dir / backup.STEP_UW_RAW
    assert summary["week"] == today and summary["cadence"] == "daily"
    assert (out / today / "uw" / "option_list" / "2026-11-20" / "list.json.gz").read_bytes() == b"a" * 20
    assert not (backup_dir / "uw-raw-daily").exists()           # no folder of its own
    assert _mf(out)["files"][f"{today}/uw/option_list/2026-11-20/list.json.gz"]["bytes"] == 20


def test_the_uw_parquet_tree_is_copied_too(backup_dir, trees):
    """Parquet is otherwise never backed up, because a build writes it again from the raw files. UW's typed copy is
    the exception: after 9 Dec 2026 neither it nor the raw day files can be fetched again, and the served option
    history is 30 sessions while the Parquet keeps every one of them."""
    assert [name for name, _ in backup.uw_raw_sources()] == ["uw", "uw_parquet", "spx_gamma"]
    summary = backup.run_backup(only="uw-raw-daily")["uw-raw-daily"]
    assert summary["uw_parquet"] == {"copied": 1, "linked": 0, "skipped": 0, "rejected": 0}
    today = backup._iso_day()
    copy = (backup_dir / backup.STEP_UW_RAW / today / "uw_parquet" / "option_list" / "session=2026-11-20"
            / "part-0.parquet")
    assert copy.read_bytes() == b"p" * 40


def test_a_day_links_its_unchanged_files_to_the_day_before(backup_dir, trees):
    """A daily cadence costs one day's new files: everything the day before already holds is a hard link to that
    folder's copy, whichever cadence wrote it."""
    uw, _, _ = trees
    out = backup_dir / backup.STEP_UW_RAW
    out.mkdir(parents=True)
    manifest = backup._Manifest(out)
    backup._backup_uw_raw(out, manifest, now=_day("2026-11-20"), daily=True)
    _file(uw / "option_list" / "2026-11-21" / "list.json.gz", b"b" * 10)        # the new session
    summary = backup._backup_uw_raw(out, manifest, now=_day("2026-11-21"), daily=True)
    assert summary["uw"] == {"copied": 1, "linked": 1, "skipped": 0, "rejected": 0}
    rel = Path("uw/option_list/2026-11-20/list.json.gz")
    first, second = out / "2026-11-20", out / "2026-11-21"
    assert (first / rel).stat().st_ino == (second / rel).stat().st_ino           # one copy on disk
    assert _mf(out)["files"][f"2026-11-21/{rel.as_posix()}"]["linked_from"] == f"2026-11-20/{rel.as_posix()}"


def test_a_daily_folder_links_to_the_weekly_one_and_neither_cadence_prunes_the_other(backup_dir, trees):
    """The two cadences share the folder and each keeps its own count, so a fortnight of daily runs never removes a
    weekly copy and the weekly run never removes a day."""
    out = backup_dir / backup.STEP_UW_RAW
    out.mkdir(parents=True)
    manifest = backup._Manifest(out)
    backup._backup_uw_raw(out, manifest, now=_day("2026-11-16"))                # the week's copy (2026-W47)
    backup._backup_uw_raw(out, manifest, now=_day("2026-11-17"), daily=True)
    rel = Path("uw/option_list/2026-11-20/list.json.gz")
    week, day = out / "2026-W47", out / "2026-11-17"
    assert week.is_dir() and day.is_dir()
    assert (week / rel).stat().st_ino == (day / rel).stat().st_ino               # the day linked to the week
    # 20 daily runs: the newest KEEP_UW_DAILY days stay and the week is untouched
    for n in range(20):
        backup._backup_uw_raw(out, manifest, now=_day("2026-11-17") + timedelta(days=n + 1), daily=True)
    names = [p.name for p in backup._week_dirs(out)]
    assert names[0] == "2026-W47"
    assert len([n for n in names if backup._is_day(n)]) == backup.KEEP_UW_DAILY
    assert names[-1] == "2026-12-07"


def test_the_step_states_how_far_behind_the_newest_backed_up_file_is(backup_dir, trees, caplog):
    """The number nothing stated when the gap opened. Read over the folders of both cadences, so a run that copied
    nothing because every file was held back is still behind."""
    uw, _, _ = trees
    out = backup_dir / backup.STEP_UW_RAW
    out.mkdir(parents=True)
    manifest = backup._Manifest(out)
    # the backup is taken when the newest session is five days old
    _file(uw / "option_list" / "2026-11-20" / "list.json.gz", b"a" * 20, age_s=5 * 86400)
    fresh = backup._backup_uw_raw(out, manifest, now=_day("2026-11-21"), daily=True)
    assert fresh["freshness"]["behind_days"] == 0.0
    assert fresh["freshness"]["uw"]["backed_up_newest"] == fresh["freshness"]["uw"]["source_newest"]
    # a new session arrives and is still being written, so the next run copies nothing of it: the backup's newest
    # file stays five days old while the source's is now
    _file(uw / "option_list" / "2026-11-25" / "list.json.gz", b"c" * 10, age_s=5)
    with caplog.at_level("WARNING"):
        behind = backup._backup_uw_raw(out, manifest, now=_day("2026-11-25"), daily=True)
    assert behind["uw"]["skipped"] == 1 and behind["uw"]["copied"] == 0
    assert behind["freshness"]["behind_days"] > backup.BEHIND_WARN_DAYS
    assert "behind the newest source file" in caplog.text
    # and the manifest keeps it, so Data health can read it after the log has scrolled away
    assert _mf(out)["freshness"]["behind_days"] == behind["freshness"]["behind_days"]
