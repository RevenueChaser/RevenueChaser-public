"""Why an hourly builder pass exited 1, in the places a person reads (#1119).

Measured 19 Nov 2026: eight red ``RC-Build`` rows, and the reason in none of the three records that were looked
at (the ``rc-builder`` jobrun log, the unit's journal, ops.db's ``job_runs.message``). The CLI printed a line per
dataset run and a stderr line per due-step failure, but ``core.automations.run_task`` sends this process's whole
stream to ``RC-Build.log``, so the only line that reaches a job record is the **last** one printed here.

Two things follow, and are tested here:

- a failed check row names the **step** that raised (``fetch``, ``parquet``, ``build``, ``check``, ``swap``), not
  only the exception's class, so an HTTP 504 a fetch got is told from the same class out of a check read;
- a pass that exits non-zero ends with one summary line naming every reason it has, exit 3 included.

The datasets are fakes registered over ``DATASETS``, as in ``test_build_batch.py``: no call, no Parquet tree.
"""
from __future__ import annotations

from datetime import date

import pytest

from revenuechaser.rcdata import ops, serving
from revenuechaser.rcdata import build as build_pkg
from revenuechaser.rcdata.build import __main__ as cli
from revenuechaser.rcdata.build import base, due

AS_OF = date(2026, 11, 6)


class Fake:
    providers: tuple[str, ...] = ()

    def __init__(self, name: str, kind: str = "market", *, fails: str | None = None):
        self.name, self.kind, self.fails = name, kind, fails
        self.tables = (f"t_{name.replace('/', '_')}",)

    def default_as_of(self) -> date:
        return AS_OF

    def _stop(self, step: str) -> None:
        if self.fails == step:
            raise base.SourceError(f"{self.name}: sec.gov said 504")

    def fetch(self, ctx, as_of):
        self._stop("fetch")
        return []

    def to_parquet_all(self, ctx, raws):
        self._stop("parquet")
        return []

    def build(self, ctx, con):
        self._stop("build")
        con.execute(f"CREATE OR REPLACE TABLE {self.tables[0]} AS SELECT 1 AS x")
        return {self.tables[0]: 1}

    def check(self, ctx, con):
        self._stop("check")
        return {"dataset": self.name, "result": "changed", "rows": 1, "added": 1, "removed": 0}


@pytest.fixture
def fakes(monkeypatch):
    base.parquet_root().mkdir(parents=True, exist_ok=True)
    reg = {n: Fake(n) for n in ("m/one", "m/two")}
    monkeypatch.setattr(build_pkg, "DATASETS", reg)
    # Nothing of the fakes' own is due: the queue here is what a test enqueues. A pause would do it, but it also
    # cancels the queued requests (``ops.schedule_pause``), and the due step is not what these tests are about.
    monkeypatch.setattr(due, "enqueue_due", lambda *a, **k: [])
    return reg


def _last_line(capsys) -> str:
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()][-1]


# --- the step that raised -----------------------------------------------------------------------

@pytest.mark.parametrize("step", ["fetch", "parquet", "build", "check"])
def test_a_failed_run_names_the_step_ahead_of_the_exception(fakes, step):
    ops.enqueue("m/two", None, by="test")                  # the same pass, with nothing wrong with it
    assert cli._run_queue("m/two", once=True) == 0
    assert "failed" not in (ops.latest_check("m/two")["note"] or "")
    fakes["m/one"].fails = step
    rid = ops.enqueue("m/one", None, by="test")
    assert cli._run_queue("m/one", once=True) == 1
    row = ops.latest_check("m/one")
    assert row["result"] == "failed"
    assert row["note"].startswith(f"{step} failed: SourceError: m/one: sec.gov said 504")
    # The same words in the run row and in the request's note, which is what the Settings board reads.
    [run] = [r for r in ops.rows("job_runs2") if r["dataset"] == "m/one"]
    assert run["status"] == "failed" and run["error"].startswith(f"{step} failed: ")
    assert next(r for r in ops.rows("build_requests") if r["id"] == rid)["note"].startswith(f"{step} failed: ")


# --- the pass's last line -----------------------------------------------------------------------

def test_the_last_line_of_a_failed_pass_names_the_dataset_its_step_and_the_exception(fakes, capsys):
    fakes["m/one"].fails = "fetch"
    ops.enqueue("m/one", None, by="test")
    reasons: list[str] = []
    assert cli._run_queue(None, once=True, reasons=reasons) == 1
    cli._say_failed(reasons)
    said = _last_line(capsys)
    assert said.startswith("pass failed: ")
    assert "m/one: fetch failed: SourceError: m/one: sec.gov said 504" in said


def test_only_a_failed_pass_prints_the_line_and_every_failed_dataset_is_on_it(fakes, capsys):
    ops.enqueue("m/one", None, by="test")
    assert cli.main(["run", "--once"]) == 0
    assert "pass failed" not in capsys.readouterr().out    # a pass that worked prints nothing extra
    assert serving.live_path("market").exists()
    fakes["m/one"].fails = "fetch"
    fakes["m/two"].fails = "fetch"
    for n in ("m/one", "m/two"):
        ops.enqueue(n, None, by="test")
    assert cli.main(["run", "--once"]) == 1
    said = _last_line(capsys)
    assert said.startswith("pass failed: ") and "m/one: fetch failed" in said and "m/two: fetch failed" in said


def test_a_due_step_failure_alone_is_the_reason_of_the_pass(fakes, monkeypatch, capsys):
    """The one reason that failed the pass with every dataset run ok, and the one that had no record at all."""
    monkeypatch.setattr(due, "enqueue_due",
                        lambda *a, **k: [("m/one", "due check failed: ValueError: no calendar after 2026", None,
                                          True)])
    assert cli.main(["run", "--once"]) == 1
    said = _last_line(capsys)
    assert said == "pass failed: due m/one: due check failed: ValueError: no calendar after 2026"


def test_a_pass_that_could_not_start_says_which_holder_it_waited_for(fakes, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_take_the_turn", lambda stack, wait: (False, "another builder (pid 4242)"))
    assert cli.main(["run", "--once"]) == 3
    assert _last_line(capsys) == "pass failed: not started: another builder (pid 4242)"


def test_the_summary_line_is_cut_where_the_job_record_cuts_it(capsys):
    cli._say_failed(["x" * 50 for _ in range(40)])
    assert len(_last_line(capsys)) == cli.REASON_LINE_MAX


def test_a_failed_pass_with_nothing_collected_still_says_the_pass_failed(capsys):
    cli._say_failed([])
    assert _last_line(capsys) == "pass failed: no reason recorded"
