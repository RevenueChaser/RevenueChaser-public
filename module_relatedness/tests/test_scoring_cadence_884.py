"""#884, the cadence half: the scoring step runs **weekly** and only when the SEC reads brought something new.

avo, 20 Nov 2026: a change in the SEC report is what gets scored ("Sec raporunda degisiklik var ise yapilacak
sekilde ayarla"), and the cadence is his word of the same day: "Tamam haftalik, uygun zamana koy" -- weekly, in a
free slot. Saturday 07:30: the week's filings are read by then, and the Sunday backups and the weekday server jobs
are elsewhere. Cheap either way, because scoring every pair of the 5,111-name universe is ~27 s of CPU on the
server (measured 20 Nov 2026, #884), not the ~2 h the cadence options were sized against.

What that needs of ``engine.score`` (``--score``), on top of what ``test_weekly_scoring_884.py`` already pins:

- on the service path its gate reads the service's ``company.profile`` answers where they are, the whole board,
  inside the job lock (#894 step 3b: it copied them into the board's tables until then). Each answer carries the
  time the service asked, so a new answer is seen the day it lands;
- reading them is free: no model call and no SEC request, so a week the service read nothing really is a week with
  nothing to do, and an unchanged week writes nothing;
- on the own-writer path (``PROFILES_FROM == "own"``) the gate reads the board's own table.

And the row itself (``RC-Relatedness-Score``): weekly Saturday 07:30, chained on the SEC reads, no cap and
no writer. Its sibling ``RC-Relatedness-OffPeak`` (the writer run) is weekly too, Sunday 22:15 -- what the
installed homesrv timer has had since 16 Nov, where these words said every other Sunday 07:30 until avo's
"Tamam haftalik".
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from revenuechaser.core import automations as A
from revenuechaser.core import job_lock, rawstore
from revenuechaser.module_relatedness import engine

NOW = datetime(2026, 11, 20, 4, 20, 9, tzinfo=timezone.utc)
PEERS = {"AAA": [{"peer": "BBB", "score": 0.42}], "BBB": [{"peer": "AAA", "score": 0.42}]}
PAYLOAD = {"as_of": NOW.isoformat(), "n": 2, "companies": [{"ticker": "AAA"}, {"ticker": "BBB"}],
           "peers": PEERS, "n_pairs": 1, "n_scored": 1, "similarity": "embedding"}
BOARD = ["AAA", "BBB"]


@pytest.fixture
def saved_payload(tmp_path, monkeypatch):
    path = tmp_path / "relatedness_latest.json"
    path.write_text(json.dumps(PAYLOAD), encoding="utf-8")
    monkeypatch.setattr(engine.config, "RELATEDNESS_JSON", path)
    monkeypatch.setattr(engine, "select_pilot", lambda: list(BOARD))
    monkeypatch.setattr("revenuechaser.module_relatedness.store.save_scores", lambda p: None)
    return PAYLOAD


def _answers(monkeypatch, seen: list, fetched_at):
    """The service's answers, as ``engine.service_rows`` reads them: one company, asked at ``fetched_at``."""
    monkeypatch.setattr(engine, "service_rows",
                        lambda tickers=None: seen.append(tickers) or [{"ticker": "AAA", "fetched_at": fetched_at}])
    monkeypatch.setattr(rawstore, "get_all", lambda *a, **k: pytest.fail("the board's own table was read"))


def _fake_run(monkeypatch, calls: list):
    def run(no_fetch, tickers, limit, usd_cap, run_id=None, provider="deepseek", max_calls=None, model=None,
            write=None):
        calls.append({"no_fetch": no_fetch, "write": write})
        return dict(PAYLOAD)
    monkeypatch.setattr(engine, "_run", run)


# ── the service's answers, read where they are ──────────────────────────────

def test_a_new_answer_from_the_service_is_scored(saved_payload, monkeypatch):
    """The gate reads the whole board's answers from the service; one newer than the payload is work."""
    seen, calls = [], []
    monkeypatch.setattr(engine.config, "PROFILES_FROM", "service")
    _answers(monkeypatch, seen, (NOW + timedelta(minutes=5)).timestamp())
    _fake_run(monkeypatch, calls)
    payload = engine.score()
    assert seen == [None]                       # every name, never a slice
    assert "skipped" not in payload and len(calls) == 1
    assert calls[0]["no_fetch"] is True and calls[0]["write"] is True   # no call, and the vectors are cached


def test_a_week_the_service_answered_nothing_is_skipped(saved_payload, monkeypatch):
    seen = []
    monkeypatch.setattr(engine.config, "PROFILES_FROM", "service")
    _answers(monkeypatch, seen, (NOW - timedelta(days=1)).timestamp())
    monkeypatch.setattr(engine, "_run", lambda *a, **k: pytest.fail("nothing to rescore"))
    monkeypatch.setattr("revenuechaser.module_relatedness.store.save_scores",
                        lambda p: pytest.fail("nothing to persist"))
    out = engine.score()
    assert seen == [None]
    assert out["skipped"] and out["as_of"] == PAYLOAD["as_of"]


def test_force_scores_even_when_the_service_answered_nothing(saved_payload, monkeypatch):
    seen, calls = [], []
    monkeypatch.setattr(engine.config, "PROFILES_FROM", "service")
    _answers(monkeypatch, seen, (NOW - timedelta(days=1)).timestamp())
    _fake_run(monkeypatch, calls)
    assert "skipped" not in engine.score(only_if_new=False)
    assert seen == [] and len(calls) == 1      # --force does not even look


def test_the_gate_waits_for_the_lock(saved_payload, monkeypatch):
    """A Fetch holds the board: the scoring step reads nothing and writes nothing."""
    seen = []
    monkeypatch.setattr(engine.config, "PROFILES_FROM", "service")
    _answers(monkeypatch, seen, (NOW + timedelta(minutes=5)).timestamp())
    monkeypatch.setattr(engine, "_run", lambda *a, **k: pytest.fail("the lock was not honoured"))
    with job_lock.acquire("relatedness", wait=0) as got:
        assert got
        with pytest.raises(engine.AlreadyRunning):
            engine.score()
    assert seen == []


def test_the_own_writer_path_reads_its_own_table(saved_payload, monkeypatch):
    calls = []
    monkeypatch.setattr(engine.config, "PROFILES_FROM", "own")
    monkeypatch.setattr(engine, "service_rows", lambda tickers=None: pytest.fail("the service was read"))
    monkeypatch.setattr(rawstore, "get_all",
                        lambda *a, **k: [{"ticker": "AAA", "fetched_at": (NOW + timedelta(minutes=5)).timestamp()}])
    _fake_run(monkeypatch, calls)
    assert "skipped" not in engine.score()
    assert len(calls) == 1


# ── the row the server installs ─────────────────────────────────────────────

def test_the_scoring_row_is_weekly_in_a_free_slot_and_chained_on_the_sec_reads():
    e = A.entry("RC-Relatedness-Score")
    assert e.args == ("-m", "revenuechaser.module_relatedness", "--score")
    assert e.days == ("Saturday",) and not e.fortnightly and not e.hourly    # weekly (avo, 20 Nov 2026)
    assert e.schedule == "weekly Saturday 07:30 (local), after RC-SEC-Read"
    assert e.after == "RC-SEC-Read"                                 # that night's answers, or nothing new to score
    assert A.system_unit(e) == "life-rc-relatedness-score"          # the home-server unit pair's name


def test_the_scoring_row_costs_nothing_and_is_not_off_peak_gated():
    e = A.entry("RC-Relatedness-Score")
    assert "--cap" not in e.args and "--provider" not in e.args     # --score refuses both: it calls no writer
    assert e.offpeak_gated is False                                 # no paid call to defer
    # It reads the service's answers and copies none into the board's profile tables (#894 step 3b).
    assert set(e.tables_written) == {"relatedness_embeddings", "relatedness_scores"}
    assert "llm_cache" not in e.tables_written


def test_the_profiling_row_is_still_its_own_job_and_weekly_too():
    """This row scores; the writer run stays its own job, and weekly since avo's word of 20 Nov 2026 -- the
    schedule the installed homesrv timer has had since 16 Nov."""
    e = A.entry("RC-Relatedness-OffPeak")
    # Since #1255 that run asks the dashboard for the board's whole-board Fetch instead of writing itself.
    assert e.args == ("-m", "revenuechaser.scripts.board_fetch", "relatedness")
    assert e.schedule == "weekly Sunday 22:15 (local)"
    assert not e.fortnightly
