"""#884 part 1: the weekly scoring step — ``--score`` / ``engine.score``.

avo, 16 Nov 2026 20:01: "A) Haftada bir, Pazar gecesi". The step is the Fetch's second half alone: the profiles
are whatever the SEC reading service mirrored, so it calls no writer and downloads nothing, and unlike a Refresh
it **writes** — the new company vectors and the peer scores.

- it rescores from the stored profiles, persists them with ``store.save_scores`` and keeps the payload;
- it asks ``_run`` for a writing run (``write=True``), so a vector embedded this week is cached for the next;
- a week whose profiles are all older than the saved payload is skipped (the timer plan's "nothing marked"),
  and ``--force`` rescores anyway;
- it holds the board's job lock, so it never runs beside a Fetch (exit 3 for the CLI);
- no ``--cap`` / ``--limit`` / ``--provider`` and no selection: it makes no call.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from RevenueChaser.core import job_lock, rawstore
from RevenueChaser.module_relatedness import __main__ as cli
from RevenueChaser.module_relatedness import engine

NOW = datetime(2026, 11, 22, 21, 15, 3, tzinfo=timezone.utc)
PEERS = {"AAA": [{"peer": "BBB", "score": 0.42}], "BBB": [{"peer": "AAA", "score": 0.42}]}
PAYLOAD = {"as_of": NOW.isoformat(), "n": 2, "companies": [{"ticker": "AAA"}, {"ticker": "BBB"}],
           "peers": PEERS, "n_pairs": 1, "n_scored": 1, "similarity": "embedding"}


@pytest.fixture
def saved_payload(tmp_path, monkeypatch):
    """The payload of the last run, at ``NOW``."""
    path = tmp_path / "relatedness_latest.json"
    path.write_text(json.dumps(PAYLOAD), encoding="utf-8")
    monkeypatch.setattr(engine.config, "RELATEDNESS_JSON", path)
    return PAYLOAD


def _profiles(monkeypatch, fetched_at):
    monkeypatch.setattr(rawstore, "get_all", lambda table, *a, **k: [{"ticker": "AAA", "fetched_at": fetched_at}])


def _fake_run(monkeypatch, calls: list):
    def run(no_fetch, tickers, limit, usd_cap, run_id=None, provider="deepseek", max_calls=None, model=None,
            write=None):
        calls.append({"no_fetch": no_fetch, "tickers": tickers, "limit": limit, "write": write,
                      "provider": provider, "model": model})
        return dict(PAYLOAD)
    monkeypatch.setattr(engine, "_run", run)


# ── engine.score ────────────────────────────────────────────────────────────

def test_the_weekly_step_scores_the_stored_profiles_and_persists_them(saved_payload, monkeypatch):
    calls, got = [], []
    _profiles(monkeypatch, (NOW + timedelta(hours=1)).timestamp())      # a newer profile: there is work
    _fake_run(monkeypatch, calls)
    monkeypatch.setattr("RevenueChaser.module_relatedness.store.save_scores", lambda p: got.append(p))
    payload = engine.score()
    assert payload["peers"] == PEERS and "skipped" not in payload
    assert got == [PEERS]                       # the pairs went to relatedness_scores
    assert len(calls) == 1
    assert calls[0]["no_fetch"] is True         # no download, no model call
    assert calls[0]["tickers"] is None and calls[0]["limit"] is None    # the whole board, always
    assert calls[0]["write"] is True            # ... and the embedded vectors are cached


def test_a_week_with_no_newer_profile_is_skipped(saved_payload, monkeypatch):
    _profiles(monkeypatch, (NOW - timedelta(days=2)).timestamp())
    monkeypatch.setattr(engine, "_run", lambda *a, **k: pytest.fail("nothing to rescore"))
    monkeypatch.setattr("RevenueChaser.module_relatedness.store.save_scores",
                        lambda p: pytest.fail("nothing to persist"))
    out = engine.score()
    assert out["skipped"] and out["as_of"] == PAYLOAD["as_of"]


def test_force_rescores_a_week_with_no_newer_profile(saved_payload, monkeypatch):
    calls, got = [], []
    _profiles(monkeypatch, (NOW - timedelta(days=2)).timestamp())
    _fake_run(monkeypatch, calls)
    monkeypatch.setattr("RevenueChaser.module_relatedness.store.save_scores", lambda p: got.append(p))
    assert "skipped" not in engine.score(only_if_new=False)
    assert len(calls) == 1 and got == [PEERS]


def test_the_weekly_step_never_runs_beside_a_fetch(saved_payload, monkeypatch):
    _profiles(monkeypatch, (NOW + timedelta(hours=1)).timestamp())
    monkeypatch.setattr(engine, "_run", lambda *a, **k: pytest.fail("the lock was not honoured"))
    with job_lock.acquire("relatedness", wait=0) as got:
        assert got
        with pytest.raises(engine.AlreadyRunning):
            engine.score()


# ── the CLI ─────────────────────────────────────────────────────────────────

def test_the_cli_prints_the_pair_counts_and_exits_0(monkeypatch, capsys):
    monkeypatch.setattr(cli.engine, "score", lambda **k: dict(PAYLOAD))
    assert cli.main(["--score"]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["n"] == 2 and out["pairs"] == 1 and out["scored"] == 1
    assert out["similarity"] == "embedding" and out["as_of"] == PAYLOAD["as_of"]
    assert isinstance(out["seconds"], float)


def test_the_cli_names_the_skip(monkeypatch, capsys):
    monkeypatch.setattr(cli.engine, "score", lambda **k: {**PAYLOAD, "skipped": "no profile is newer"})
    assert cli.main(["--score"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["skipped"] == "no profile is newer"


def test_force_reaches_the_engine(monkeypatch, capsys):
    got = {}
    monkeypatch.setattr(cli.engine, "score", lambda **k: got.update(k) or dict(PAYLOAD))
    assert cli.main(["--score", "--force"]) == 0
    assert got["only_if_new"] is False
    got.clear()
    assert cli.main(["--score"]) == 0
    assert got["only_if_new"] is True


def test_a_busy_lock_exits_3_and_wrote_nothing(monkeypatch, capsys):
    def busy(**k):
        raise cli.engine.AlreadyRunning("Another Relatedness run is already in progress.")
    monkeypatch.setattr(cli.engine, "score", busy)
    assert cli.main(["--score"]) == 3
    assert "already in progress" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["skipped"]


@pytest.mark.parametrize("argv", [["--score", "--cap", "10"], ["--score", "--limit", "5"],
                                  ["--score", "--provider", "evren"], ["--score", "--run"],
                                  ["--score", "--status"], ["--score", "--tickers", "AAA,BBB"],
                                  ["--score", "--floor", "300"], ["--force"]])
def test_the_flags_that_make_no_sense_for_a_scoring_run_are_refused(argv):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2


def test_the_scoring_run_calls_no_writer(monkeypatch, capsys):
    """It is the one board job with no provider: ``engine.run`` is never reached."""
    monkeypatch.setattr(cli.engine, "run", lambda *a, **k: pytest.fail("a scoring run calls no writer"))
    monkeypatch.setattr(cli.engine, "score", lambda **k: dict(PAYLOAD))
    assert cli.main(["--score"]) == 0
