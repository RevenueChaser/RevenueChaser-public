"""#297 (D12): the three jobs that store vendor statements/valuation stamp them with the job's run id.

- ``universe`` / AG Fetch: ``run_asymmetric_growth`` passes the job's id to the scan; a Refresh runs no scan and asks for no id (K4).
- ``quick``: ``run_quick`` passes the job's id to Financials' ``run``.
- ``earnings``: ``run_earnings_range`` flushes the pipeline's capture with the job's id.
Offline: the scans are spies, temp stores."""
from __future__ import annotations

from datetime import date

import pytest

from RevenueChaser.app import runners
from RevenueChaser.core import ledger, rawstore

AG_RESULT = {"cards": [], "summary": {}, "asof": "2026-10-08T20:35:00+00:00", "funnel_steps": []}










def test_quick_hands_the_job_id_to_financials(monkeypatch, rawstore_tmp_db):
    import RevenueChaser.module_financials.run as fm
    seen = {}
    monkeypatch.setattr(fm, "run", lambda ticker, **k: seen.update(k) or {"paths": {}})
    monkeypatch.setattr(runners, "run_id", lambda: "job-q")
    monkeypatch.setattr(runners, "_copy_quick_artifact", lambda html: False)
    runners.run_quick(None, "MSFT")
    assert seen["run_id"] == "job-q"




class _UW:
    auth_error = None

    def health(self):
        return {"calls": 1, "failed": 0, "failures": [], "auth_error": None, "breaker_open": False,
                "skipped_calls": 0}

    def screener_batch(self, tickers):
        return {}


