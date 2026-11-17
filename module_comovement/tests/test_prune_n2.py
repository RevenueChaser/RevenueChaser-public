"""Review v2 N2 (avo's card, 17 Nov 2026: "14 günden eskiyi sil"): a stored run deletes, in the same transaction,
every run older than ``config.KEEP_DAYS`` days together with its nodes, members and lagged rows, except the newest
run of each config hash (the one a Refresh or the Relatedness board still serves).

Offline, temp store.
"""
from __future__ import annotations

from RevenueChaser.core import rawstore
from RevenueChaser.module_comovement import config, engine


def _store(as_of: str, chash: str) -> None:
    engine._persist(as_of, chash, 2,
                    [{"as_of": as_of, "cut": 60, "cluster_id": "0", "n": 2}],
                    [{"as_of": as_of, "cut": 60, "cluster_id": "0", "ticker": "AAA"}],
                    1, "SPY", 252,
                    lag={60: [{"lag_id": "0", "members": ["AAA"], "oos_r": 0.1, "oos_base": 0.0, "held": 1}]})


def _as_ofs(table: str) -> list[str]:
    return sorted({r["as_of"] for r in rawstore.query(f"SELECT as_of FROM {table}", db="comovement")})


def test_old_runs_are_pruned_but_the_newest_per_hash_stays(rawstore_tmp_db):
    assert config.KEEP_DAYS == 14
    _store("2026-10-01T00:00:00.000000+00:00", "a")    # old, superseded by a newer "a" -> deleted
    _store("2026-10-02T00:00:00.000000+00:00", "b")    # old, but the newest "b" -> kept
    _store("2026-11-10T00:00:00.000000+00:00", "a")    # inside 14 days -> kept
    _store("2026-11-17T00:00:00.000000+00:00", "a")    # the new run
    want = ["2026-10-02T00:00:00.000000+00:00", "2026-11-10T00:00:00.000000+00:00",
            "2026-11-17T00:00:00.000000+00:00"]
    for table in ("comov_runs", "comov_nodes", "comov_members", "comov_lag"):
        assert _as_ofs(table) == want, table
