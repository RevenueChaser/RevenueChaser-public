"""#136: a run records how much it did, for the Runs tab's ``counts`` column.

Two writers, two gaps, and this suite covers both.

**The scheduled writer** (``core/automations.run_task``) wrote a literal ``"counts": None`` — the only
occurrence of ``counts`` in that file — so no scheduled step could record counts whatever it printed. A
step's CLI prints its result as JSON on stdout, which ``run_task`` streams into the task's log, so the
numbers are there to be read. What it prints is a whole *result*, though — a run id, a session date, nested
sweep statistics, sometimes a provider name and no counts at all — so the row takes the last JSON object the
command printed **through the same filter the dashboard side uses** (``core/run_counts.numeric``). One rule
for one column: the alternative was the same work recording a different shape depending on who started it.

**The dashboard writer** (``app/jobs.py:_counts_of``) stores a runner's returned ``counts``, and
``run_spxgamma_history`` proves it. But the long writers the issue names (identity, daily bars) never
return: they end by raising ``JobMessage`` so the UI shows what happened, and the ``except JobMessage``
branch never asked for counts. ``JobMessage`` now carries them, which is what makes adoption a one-line
change per runner instead of a return-type change that would break every caller using the returned path.

Offline; a log file in ``tmp_path`` and the temp store.
"""
from __future__ import annotations

import dataclasses
import json

from RevenueChaser.app import jobs
from RevenueChaser.core import automations, rawstore

OK_JSON = '{"rows": 93714, "written": 93714, "status": {"open": 93382, "closed": 332}}'










def test_a_job_message_carries_counts_so_a_runner_that_never_returns_can_record_them():
    """Identity and daily bars end with ``JobMessage``; without this they could record nothing."""
    counts = {"tickers": 7, "written": 7}

    assert jobs.JobMessage("done", counts=counts).counts == counts
    assert jobs.JobMessage("done").counts is None






