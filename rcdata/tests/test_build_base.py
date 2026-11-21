"""``rcdata/build/base.py``: the pacer, the keyless HTTP helper, raw and Parquet writes, the idle gate."""
from __future__ import annotations

import pytest

from RevenueChaser.core import job_lock
from RevenueChaser.rcdata.build import base


def test_the_pacer_never_lets_120_calls_into_one_minute():
    now = [0.0]
    sent = []

    def sleep(s):
        now[0] += s

    pacer = base.Pacer(110, clock=lambda: now[0], sleep=sleep)
    for _ in range(400):
        pacer.wait()
        sent.append(now[0])
        now[0] += 0.01                      # a fast answer
    for i, t in enumerate(sent):
        in_window = sum(1 for u in sent[i:] if u - t < 60.0)
        assert in_window <= 110
    assert sent[-1] > 180.0                 # it really waited


def test_http_get_retries_5xx_counts_every_attempt_and_raises(http_mock):
    http_mock.add("flaky.test", b"oops", status=503)
    ctx = base.RunContext(run_id="r", dataset="d", sleep=lambda s: None)
    with pytest.raises(base.SourceError, match="HTTP 503"):
        base.http_get(ctx, "cboe", "https://flaky.test/x.csv")
    assert ctx.calls["cboe"] == [base.HTTP_ATTEMPTS, 1, 0]
    assert len(http_mock.calls("flaky.test")) == base.HTTP_ATTEMPTS


def test_http_get_does_not_retry_a_404_and_counts_no_failure(http_mock):
    """#1304: the request is counted and it raises, but "the host holds no such object" is an answer and not
    provider trouble, so the day's ``failures`` stays where it was -- as the app's own client already has it."""
    ctx = base.RunContext(run_id="r", dataset="d", sleep=lambda s: None)
    with pytest.raises(base.SourceError):
        base.http_get(ctx, "fed", "https://nothing.test/")
    assert ctx.calls["fed"] == [1, 0, 0]


def test_http_get_counts_a_failure_for_a_403_a_429_and_a_5xx(http_mock):
    """#1304's other side: a refusal and a provider that could not answer are failures. The 403 case is
    ``test_a_403_says_what_to_set``; here the ladder's two ends."""
    ctx = base.RunContext(run_id="r", dataset="d", sleep=lambda s: None)
    http_mock.add("busy.test", b"slow down", status=429)
    with pytest.raises(base.SourceError):
        base.http_get(ctx, "fed", "https://busy.test/x")
    assert ctx.calls["fed"] == [base.HTTP_ATTEMPTS, 1, base.HTTP_ATTEMPTS]


def test_counts_as_failure_reads_the_statuses_the_way_the_app_client_does():
    assert [base.counts_as_failure(s) for s in (None, 429, 403, 500, 503)] == [True] * 5
    assert [base.counts_as_failure(s) for s in (400, 404, 410, 422, 451)] == [False] * 5


def test_http_get_answers_an_accepted_status_as_it_is(http_mock):
    """PR 16: a source whose 404 means "not published yet" (a daily file, a filing index) reads the answer itself:
    one call, not a failure."""
    ctx = base.RunContext(run_id="r", dataset="d", sleep=lambda s: None)
    r = base.http_get(ctx, "sec", "https://nothing.test/master.20261026.idx", accept=(404,))
    assert r.status_code == 404
    assert ctx.calls["sec"] == [1, 0, 0]


def test_raw_files_round_trip_and_gzip_by_name(tmp_path):
    p = base.write_raw(tmp_path / "a" / "x.json.gz", b'{"a": 1}')
    assert p.read_bytes()[:2] == b"\x1f\x8b" and base.read_raw_json(p) == {"a": 1}
    assert not list(tmp_path.rglob("*.tmp"))


def test_upsert_partition_merges_by_key_and_the_newest_fetch_wins(tmp_path):
    schema = [("k", "TEXT"), ("v", "DOUBLE"), ("fetched_at", "DOUBLE")]
    part = tmp_path / "year=2026" / "part-0.parquet"
    base.upsert_partition([{"k": "a", "v": 1, "fetched_at": 1}, {"k": "b", "v": 2, "fetched_at": 1}], schema, ["k"], part)
    base.upsert_partition([{"k": "b", "v": 3, "fetched_at": 2}, {"k": "c", "v": 4, "fetched_at": 2}], schema, ["k"], part)
    import duckdb
    rows = duckdb.connect().execute(f"SELECT k, v FROM read_parquet({base.sql_path(part)}) ORDER BY k").fetchall()
    assert rows == [("a", 1.0), ("b", 3.0), ("c", 4.0)]
    assert not list(tmp_path.rglob("*.tmp"))


def test_a_board_store_job_does_not_hold_the_builder_off():
    """The behaviour change of #309's follow-up: ``relatedness`` writes the board files, the builder the market one.

    This is the refusal that stopped the WRDS price backfill while the Relatedness pilot ran (30 Oct 2026).
    """
    assert base.idle_problem() is None
    with job_lock.acquire("relatedness", wait=0) as got:
        assert got
        assert base.idle_problem() is None
    assert base.idle_problem() is None


def test_a_second_builder_still_stops_the_builder():
    with job_lock.acquire(base.BUILDER_LOCK, wait=0) as got:
        assert got
        assert base.BUILDER_LOCK in base.idle_problem()
    assert base.idle_problem() is None


def test_a_lock_that_declared_nothing_still_stops_the_builder():
    """An undeclared family keeps the old all-or-nothing gate, so a new writer cannot slip past it."""
    with job_lock.acquire("a_new_writer", wait=0) as got:
        assert got
        assert "a_new_writer" in base.idle_problem()
    assert base.idle_problem() is None


def test_the_gate_answers_for_the_lock_it_is_asked_about():
    """``idle_problem`` takes the lock name, so an old-store writer can ask the same gate about its own files."""
    with job_lock.acquire("relatedness", wait=0) as got:
        assert got
        assert base.idle_problem() is None
        assert "relatedness" in base.idle_problem("edgar_sync")


def test_session_date_is_empty_outside_the_calendar_table():
    from datetime import date
    assert base.session_date_of(date(2026, 10, 25)) == date(2026, 10, 23)    # a Sunday -> Friday
    assert base.session_date_of(date(1990, 1, 2)) is None


def test_the_user_agent_carries_the_contact_from_rc_http_contact(http_mock, monkeypatch):
    http_mock.add("ua.test", b"ok")
    monkeypatch.setenv("RC_HTTP_CONTACT", "builder-contact@example.invalid")
    ctx = base.RunContext(run_id="r", dataset="d", sleep=lambda s: None)
    base.http_get(ctx, "bls", "https://ua.test/x")
    assert "builder-contact@example.invalid" in http_mock.requests[-1].headers["user-agent"]
    monkeypatch.setenv("RC_HTTP_CONTACT", "")
    assert "RC_HTTP_CONTACT" in base.user_agent()


def test_a_403_says_what_to_set(http_mock, monkeypatch):
    monkeypatch.setenv("RC_HTTP_CONTACT", "")
    http_mock.add("bls.test", b"Access Denied", status=403)
    ctx = base.RunContext(run_id="r", dataset="d", sleep=lambda s: None)
    with pytest.raises(base.SourceError, match=r"HTTP 403 \(refused: set RC_HTTP_CONTACT"):
        base.http_get(ctx, "bls", "https://bls.test/schedule/news_release/bls.ics")
    assert ctx.calls["bls"] == [1, 1, 0]


def test_a_403_to_a_keyed_request_points_at_the_key_not_the_contact(http_mock, monkeypatch):
    # The Opus review's N2: Alpaca answers a wrong key with 403, and the contact hint sent the reader the wrong way.
    monkeypatch.setenv("RC_HTTP_CONTACT", "")
    http_mock.add("alpaca.test", b"forbidden", status=403)
    ctx = base.RunContext(run_id="r", dataset="d", sleep=lambda s: None)
    with pytest.raises(base.SourceError, match=r"HTTP 403 \(refused: check the key") as err:
        base.http_get(ctx, "alpaca", "https://alpaca.test/v2/stocks/bars", headers={"APCA-API-KEY-ID": "test-key"},
                      keyed=True)
    assert "RC_HTTP_CONTACT" not in str(err.value) and "test-key" not in str(err.value)


def test_iter_sessions_crosses_the_2015_2016_year_end():
    """Before 2025 the calendar's table now has the sessions (#348): New Year's Day 2016 is closed."""
    from datetime import date
    got = list(base.iter_sessions(date(2015, 12, 28), date(2016, 1, 5)))
    assert got == [date(2015, 12, d) for d in (28, 29, 30, 31)] + [date(2016, 1, 4), date(2016, 1, 5)]
