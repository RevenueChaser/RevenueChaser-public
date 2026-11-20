"""#446 step 8: ``prices`` is in the scheduled flow, and only its **whole** build waits for a person.

A build on a copy of the live file fits the builder's window; a whole ``prices`` build does not (86 min for the
2010+ volume, 6 h 12 min and 92 GB of spill for the first one with the WRDS history). So ``prices/serving`` no
longer ``starts_by_hand`` -- it is due on its daily cadence -- and declares ``whole_build_by_hand`` instead: when
the plan says the build would be whole and nobody pressed anything, the pass leaves the file alone and says why.

The mechanism is kind-independent, so it is proven here on ``market`` (whose datasets are small and offline, as
``test_market_incremental.py`` has them) with the declaration set for the test, and the one assertion about
``prices`` is on the dataset itself.
"""
from __future__ import annotations

from datetime import date

import pytest

from RevenueChaser.rcdata import ops, serving
from RevenueChaser.rcdata.build import DATASETS, base, dirty, market_series as ms
from RevenueChaser.rcdata.build import uw_greek_expiry_strike as greek, uw_spot_expiry_strike as spot
from RevenueChaser.rcdata.build.prices import serving as prices_serving
from RevenueChaser.rcdata.build.sources import fred, treasury

D1, D3 = date(2026, 10, 26), date(2026, 10, 28)
MEMBERS = (ms.DATASET, spot.DATASET, greek.DATASET)


def _series(src, year: int, value: float) -> None:
    rows = [{"series_id": "DGS10", "obs_date": date(year, 3, d), "source": src.SOURCE, "value": value + d,
             "frequency": "daily", "source_as_of": date(year, 3, 31), "fetched_at": 1.0, "run_id": "r"}
            for d in (2, 3, 4)]
    base.upsert_partition(rows, ms.SCHEMA, ms.KEY, ms.partition_path(src, year))


def _uw(mod, day: date) -> None:
    rows = [{"session_date": day, "expiry": date(2026, 11, 20), "strike": 7000.0, "dte": 18, "source": "uw",
             "source_as_of": day, "fetched_at": 1.0, "run_id": "r",
             **{f: 1.0 for f in mod.NUMERIC_FIELDS if f != "price"}}]
    base.upsert_partition(rows, mod.SCHEMA, list(mod.KEY), mod.partition_path(day))


@pytest.fixture()
def seeded(monkeypatch):
    """A market Parquet tree, and ``market_series`` holding its whole build back for a person."""
    base.parquet_root().mkdir(parents=True, exist_ok=True)
    _uw(spot, D1)
    _uw(greek, D1)
    _series(treasury, 2025, 4.0)
    for year in range(2020, 2027):              # enough untouched files to stay under dirty.MAX_DIRTY_SHARE
        _series(fred, year, 3.0)
    monkeypatch.setattr(ms.DATASET, "whole_build_by_hand", True, raising=False)
    return None


def _build(scheduled: bool) -> tuple[dict, str]:
    """One build of ``market`` with every dataset a member; ``scheduled``: the hourly pass's own requests."""
    ctxs = [(d, base.RunContext(run_id=f"t-{d.name}", dataset=d.name, as_of=D3, scheduled=scheduled,
                                allow_shrink=True))
            for d in MEMBERS]
    checks = base.build_kind_many("market", ctxs, lead=ctxs[0][1])
    return checks[ms.NAME], " ".join(ctxs[0][1].notes)


# ── the declaration ───────────────────────────────────────────────────────────────────────────────────────────

def test_prices_serving_is_in_the_scheduled_flow_and_holds_only_its_whole_build():
    ds = prices_serving.PricesServing
    assert not getattr(ds, "starts_by_hand", False), "a hand start is what #446 step 8 removes"
    assert ds.whole_build_by_hand is True and ds.cadence == "daily"


def test_only_a_declaring_kind_holds_its_whole_build(seeded):
    assert base.whole_build_by_hand("market") == (ms.NAME,)
    assert base.whole_build_by_hand("spine") == (), "every other kind is built whole by the pass, as before"


# ── the gate ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_whole_build_in_the_pass_is_refused_and_leaves_no_file(seeded):
    with pytest.raises(base.WholeBuildByHand, match="a whole market build is not started by the hourly pass"):
        _build(scheduled=True)
    with pytest.raises(serving.ServingFileMissing):
        with serving.open_read("market"):
            pass


def test_the_refusal_names_the_dataset_that_holds_it_and_why_the_build_is_whole(seeded):
    with pytest.raises(base.WholeBuildByHand) as e:
        _build(scheduled=True)
    assert ms.NAME in str(e.value) and "live market file" in str(e.value), str(e.value)


def test_anything_but_the_pass_gets_the_whole_build(seeded):
    check, note = _build(scheduled=False)
    assert check["result"] != "failed" and "built whole" in note, note
    with serving.open_read("market") as con:
        assert con.execute(f"SELECT count(*) FROM {ms.TABLE}").fetchone()[0] > 0


def test_one_press_among_the_passs_requests_builds_it(seeded):
    """A pass that also holds a person's Fetch of the kind is a person asking for the build: ``all``, not ``any``."""
    ctxs = [(d, base.RunContext(run_id=f"t-{d.name}", dataset=d.name, as_of=D3, allow_shrink=True,
                                scheduled=d is not ms.DATASET))
            for d in MEMBERS]
    checks = base.build_kind_many("market", ctxs, lead=ctxs[0][1])
    assert "built whole" in " ".join(ctxs[0][1].notes) and checks[ms.NAME]["result"] != "failed"


def test_the_build_on_the_live_copy_runs_in_the_pass(seeded):
    _build(scheduled=False)
    _series(fred, 2026, 9.9)                        # one source's year restated: a dirty set, not a whole build
    check, note = _build(scheduled=True)
    assert "built on the live file" in note, note
    assert check["result"] != "failed", check


def test_a_kind_that_declares_nothing_is_built_whole_in_the_pass(seeded, monkeypatch):
    monkeypatch.delattr(ms.DATASET, "whole_build_by_hand")
    check, note = _build(scheduled=True)
    assert "built whole" in note and check["result"] != "failed", note


def test_the_lever_by_hand_does_not_let_the_pass_in(seeded, monkeypatch):
    """``RC_BUILD_WHOLE=1`` asks for a whole build; it is still not one the hourly pass starts."""
    _build(scheduled=False)
    monkeypatch.setenv(dirty.WHOLE_ENV, "1")
    with pytest.raises(base.WholeBuildByHand):
        _build(scheduled=True)


# ── what a refused pass writes ────────────────────────────────────────────────────────────────────────────────

class _Fetcher:
    """A dataset whose fetch does nothing, so a test reaches the build with no provider call."""

    kind = "market"
    providers = ()
    tables = ()
    cadence = "daily"

    def __init__(self, name: str):
        self.name = name

    def default_as_of(self):
        return D3

    def fetch(self, ctx, as_of):
        return []

    def to_parquet_all(self, ctx, raws):
        return []

    def backfill(self, ctx, start, end):
        return None


@pytest.fixture()
def refusing(monkeypatch):
    """Two fake datasets of one kind, whose build raises the refusal."""
    held = [_Fetcher("test/held_a"), _Fetcher("test/held_b")]
    for ds in held:
        monkeypatch.setitem(DATASETS, ds.name, ds)
    refusal = base.WholeBuildByHand("a whole market build is not started by the hourly pass (test/held_a): "
                                    "no live market file; press Fetch on the Settings board, or run it from the "
                                    "CLI on the server")

    def raise_it(*args, **kwargs):
        raise refusal
    monkeypatch.setattr(base, "build_kind", raise_it)
    monkeypatch.setattr(base, "build_kind_many", raise_it)
    return held


def _schedule(name: str) -> dict:
    """The request ``due.py`` would queue: no person behind it."""
    ops.enqueue(name, None, by="schedule")
    return ops.next_request(name)


def test_a_fetch_press_of_the_same_dataset_is_not_refused(refusing, monkeypatch):
    """The gate is in ``build_kind_many``; what reaches it from a press is a context that is not the schedule's."""
    seen: list[bool] = []
    monkeypatch.setattr(base, "build_kind", lambda ctx, ds: seen.append(ctx.scheduled) or
                        {"dataset": ds.name, "result": "changed"})
    ops.enqueue(refusing[0].name, None, by="settings")
    row = base.run_request(ops.next_request(refusing[0].name))
    assert seen == [False] and row["result"] == "changed", (seen, row)


def test_a_refused_pass_is_a_skipped_check_row_not_a_failure(refusing):
    row = base.run_request(_schedule(refusing[0].name))
    assert row["result"] == "skipped", row
    assert "not started by the hourly pass" in row["note"] and "press Fetch" in row["note"], row["note"]


def test_a_refused_pass_of_several_requests_skips_every_one(refusing):
    rows = base.run_batch([_schedule(ds.name) for ds in refusing])
    assert [r["result"] for r in rows] == ["skipped", "skipped"], rows
    assert all("not started by the hourly pass" in r["note"] for r in rows), rows


def test_only_the_schedules_own_request_is_the_pass():
    """Not the negation of ``_pressed``: a request with neither an id nor a ``requested_by`` is held by nothing."""
    assert base._scheduled({"id": 1, "requested_by": "schedule"}) is True
    assert base._scheduled({"id": 1, "requested_by": "settings"}) is False
    assert base._scheduled({}) is False and base._pressed({}) is False
