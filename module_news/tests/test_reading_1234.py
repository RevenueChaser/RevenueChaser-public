"""The hourly reading of the headline flow (#1234, avo 21 Nov 2026 decision A).

avo's decision, in his own terms: the EVREN model — no quota, no fee — reads the news stream hourly, and its
reading is stored as fixed-schema fields **where every field carries the sentence it came from**. So the tests
here are mostly one invariant, from several sides:

- a stored field carries a ``quote`` that really occurs in the headline its ``headline_id`` names;
- a field the model wrote a sentence of its own for, or cited a headline outside the window for, is **not
  stored** at all;
- the store itself refuses a field without its sentence, so no later code path can quietly drop the rule.

Plus the pass's cost rules: one call an hour, no call in an hour with no headline, and nothing at all on a paid
writer unless the run was started with avo's word.

No model is called: the writer is a fake module with the one ``complete`` the job uses (``core.llm_jobs.client``).
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.core import automations, llm_jobs, rawstore
from revenuechaser.module_news import reading, store_reads

HOUR = 1_794_999_600.0                      # an exact hour boundary (498_611 * 3600); the window is the hour before
NOW = HOUR + 1200.0                         # :20, the timer's own minute

HEADLINES = [
    ("h1", "Fed's Williams says policy is still modestly restrictive", "Dow Jones", HOUR - 600, []),
    ("h2", "NVDA guides fourth quarter above consensus on data centre demand", "Dow Jones", HOUR - 1200, ["NVDA"]),
    ("h3", "Oil slips as OPEC+ signals no change to output", "Briefing", HOUR - 2400, []),
]


def _store_headlines(rows=HEADLINES) -> None:
    rawstore.write_rows(store_reads.HEADLINES, [
        {"headline_id": hid, "provider": "ibkr", "published_at": at, "headline": text, "source": source,
         "tickers": json.dumps(tickers), "url": None, "fetched_at": at, "run_id": "r", "run_at": at}
        for hid, text, source, at, tickers in rows])


def _reply(fields: dict) -> str:
    return json.dumps(fields)


def _stored_fields() -> list[str]:
    """The fields in the store, by name. A ``SELECT`` and not a ``count(*)``: a table nothing has written yet
    reads as no rows at all (``rawstore.query`` swallows DuckDB's ``CatalogException`` on a read), so a count
    would answer with an empty list and not with a zero."""
    return [r["field"] for r in rawstore.query(f"SELECT field FROM {store_reads.READING}", db="news")]


def _writer(monkeypatch, reply, *, calls=None):
    """Stand the job's writer in with one that answers ``reply`` and records each call's user message."""
    class Fake:
        MODEL = "evren-deepseek-v4.1-flash"

        @staticmethod
        def complete(system, user, **kw):
            if calls is not None:
                calls.append({"system": system, "user": user, **kw})
            return reply(user) if callable(reply) else reply

    monkeypatch.setattr(llm_jobs, "client", lambda job_id: Fake)
    return Fake


# ── the invariant: every stored field carries the sentence it came from ───────────────────────────────────────────
def test_a_pass_stores_one_row_a_field_each_with_the_sentence_it_came_from(monkeypatch):
    _store_headlines()
    calls = []
    _writer(monkeypatch, _reply({
        "tone": {"value": "risk_off", "headline_id": "h3",
                 "quote": "Oil slips as OPEC+ signals no change to output"},
        "driver": {"value": "NVDA's guidance", "headline_id": "h2",
                   "quote": "NVDA guides fourth quarter above consensus"},
        "rates": {"value": "still restrictive", "headline_id": "h1",
                  "quote": "policy is still modestly restrictive"},
    }), calls=calls)

    out = reading.run(run_id="rid", now=NOW)

    assert (out["window_start"], out["window_end"]) == (HOUR - 3600, HOUR)
    assert (out["headlines"], out["stored"], out["unsourced"]) == (3, 3, [])
    assert out["provider"] == "evren" and not out["skipped"] and not out["error"]
    assert len(calls) == 1                                          # one call an hour, whatever the hour holds

    rows = {r["field"]: r for r in rawstore.query(f"SELECT * FROM {store_reads.READING}", db="news")}
    assert set(rows) == {"tone", "driver", "rates"}
    headline_of = {hid: text for hid, text, *_ in HEADLINES}
    for field, row in rows.items():
        assert row["quote"].strip(), f"{field} was stored without its sentence"
        assert row["headline_id"] in headline_of
        assert row["quote"] in headline_of[row["headline_id"]], f"{field}'s quote is not that headline's words"
        assert (row["window_end"], row["window_start"]) == (HOUR, HOUR - 3600)
        assert (row["provider"], row["model"], row["headlines"], row["run_id"]) == (
            "evren", "evren-deepseek-v4.1-flash", 3, "rid")
        assert row["prompt_version"] == reading.PROMPT_VERSION
    assert rows["rates"]["source"] == "Dow Jones" and rows["tone"]["source"] == "Briefing"


@pytest.mark.parametrize("field_said, why", [
    ({"value": "risk_on", "headline_id": "h1", "quote": "traders turned decisively optimistic"},
     "a sentence of the model's own"),
    ({"value": "risk_on", "headline_id": "h9", "quote": "Oil slips as OPEC+ signals no change to output"},
     "a headline the window did not hold"),
    ({"value": "risk_on", "headline_id": "h1", "quote": ""}, "no quote at all"),
    ({"value": "risk_on", "headline_id": "", "quote": "policy is still modestly restrictive"}, "no headline id"),
    ({"value": "", "headline_id": "h1", "quote": "policy is still modestly restrictive"}, "no value"),
    ({"value": "cheerful", "headline_id": "h1", "quote": "policy is still modestly restrictive"},
     "a value outside the field's set"),
])
def test_a_field_that_cannot_be_traced_to_a_headline_is_not_stored(monkeypatch, field_said, why):
    _store_headlines()
    _writer(monkeypatch, _reply({"tone": field_said,
                                 "rates": {"value": "still restrictive", "headline_id": "h1",
                                           "quote": "policy is still modestly restrictive"}}))

    out = reading.run(now=NOW)

    assert out["stored"] == 1 and len(out["unsourced"]) == 1 and "tone" in out["unsourced"][0], why
    assert _stored_fields() == ["rates"], f"{why} was stored anyway"


def test_the_store_itself_refuses_a_field_without_its_sentence():
    """``parse`` drops an unsourced field; the store refuses one too, so no other caller can bypass the rule."""
    for bad in ({"field": "tone", "value": "risk_on", "quote": "", "headline_id": "h1"},
                {"field": "tone", "value": "risk_on", "quote": "a sentence", "headline_id": ""}):
        with pytest.raises(ValueError, match="sentence it came from"):
            reading.store([bad], start=HOUR - 3600, end=HOUR, provider="evren", model="m", headlines=1)
    assert _stored_fields() == []


def test_a_reply_that_is_not_json_or_not_an_object_stores_nothing(monkeypatch):
    _store_headlines()
    for reply in ("not json at all", json.dumps(["tone"])):
        _writer(monkeypatch, reply)
        out = reading.run(now=NOW)
        assert out["stored"] == 0 and out["unsourced"]
    assert _stored_fields() == []


def test_an_unknown_field_name_is_never_stored(monkeypatch):
    """The schema is fixed: a key the form does not name is not a column, not a row and not an error."""
    _store_headlines()
    _writer(monkeypatch, _reply({"mood": {"value": "x", "headline_id": "h1", "quote": "policy is still"},
                                 "tone": {"value": "quiet", "headline_id": "h3",
                                          "quote": "OPEC+ signals no change to output"}}))
    assert reading.run(now=NOW)["stored"] == 1
    assert _stored_fields() == ["tone"]


# ── the window ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_window_is_the_clock_hour_that_has_just_finished_and_a_rerun_upserts_it(monkeypatch):
    _store_headlines()
    # A headline of the current, unfinished hour is not in the window the pass reads.
    _store_headlines([("h4", "Late print after the hour", "Dow Jones", HOUR + 60, [])])
    calls = []
    _writer(monkeypatch, _reply({"tone": {"value": "quiet", "headline_id": "h3",
                                          "quote": "Oil slips as OPEC+ signals no change to output"}}),
            calls=calls)

    assert reading.run(now=NOW)["headlines"] == 3                   # not the four stored
    assert "Late print after the hour" not in calls[0]["user"]

    _writer(monkeypatch, _reply({"tone": {"value": "risk_off", "headline_id": "h3",
                                          "quote": "Oil slips as OPEC+ signals no change to output"}}))
    reading.run(now=NOW + 300)                                      # the same hour, a second pass
    rows = rawstore.query(f"SELECT field, value FROM {store_reads.READING}", db="news")
    assert rows == [{"field": "tone", "value": "risk_off"}]         # one row an hour, upserted


def test_an_hour_with_no_stored_headline_asks_nothing(monkeypatch):
    calls = []
    _writer(monkeypatch, _reply({}), calls=calls)
    out = reading.run(now=NOW)
    assert out["headlines"] == 0 and out["stored"] == 0 and "no headline" in out["skipped"]
    assert calls == []                                              # a quiet hour costs no call


# ── the writer and what it costs ─────────────────────────────────────────────────────────────────────────────────
def test_the_job_is_registered_and_defaults_to_the_free_writer():
    job = llm_jobs.get(reading.JOB)
    assert job.id == "news.reading" and not job.env
    assert llm_jobs.default_provider(reading.JOB) == "evren"
    assert llm_jobs.pair(reading.JOB)[0] == "evren"                 # no fee by default (avo, #1234 decision A)


def test_a_paid_writer_asks_nothing_unless_the_run_carries_avos_word(monkeypatch):
    _store_headlines()
    calls = []
    _writer(monkeypatch, _reply({"tone": {"value": "quiet", "headline_id": "h3",
                                          "quote": "Oil slips as OPEC+ signals no change to output"}}),
            calls=calls)
    monkeypatch.setattr(llm_jobs, "pair", lambda job_id: ("deepseek", "deepseek-v4-flash"))

    out = reading.run(now=NOW)
    assert out["stored"] == 0 and calls == [] and "paid" in out["skipped"]

    out = reading.run(now=NOW, allow_paid=True)                     # avo's word on the request
    assert out["stored"] == 1 and len(calls) == 1 and out["provider"] == "deepseek"


def test_a_writer_that_does_not_answer_is_a_note_and_not_a_failed_pass(monkeypatch):
    _store_headlines()

    class Down:
        @staticmethod
        def complete(system, user, **kw):
            raise llm_jobs.TransientError("the gate answered 503")

    monkeypatch.setattr(llm_jobs, "client", lambda job_id: Down)
    out = reading.run(now=NOW)
    assert out["stored"] == 0 and "503" in out["error"]              # no exception reaches the hourly timer


def test_the_prompt_carries_the_form_and_every_headline_with_its_id(monkeypatch):
    _store_headlines()
    calls = []
    _writer(monkeypatch, _reply({}), calls=calls)
    reading.run(now=NOW)
    user = calls[0]["user"]
    for name in reading.FIELDS:
        assert name in user
    for hid, text, *_ in HEADLINES:
        assert f"[{hid}]" in user and text in user
    assert "risk_on" in user and "risk_off" in user                 # the closed value set is in the form
    assert calls[0]["json_mode"] and calls[0]["model"] == "evren-deepseek-v4.1-flash"


# ── reading it back ──────────────────────────────────────────────────────────────────────────────────────────────
def test_the_stored_reading_reads_back_by_hour_with_its_sentences(monkeypatch):
    _store_headlines()
    _writer(monkeypatch, _reply({"tone": {"value": "risk_off", "headline_id": "h3",
                                          "quote": "Oil slips as OPEC+ signals no change to output"},
                                 "rates": {"value": "still restrictive", "headline_id": "h1",
                                           "quote": "policy is still modestly restrictive"}}))
    reading.run(now=NOW)

    windows = reading.api_rows(hours=24, now=NOW)
    assert len(windows) == 1 and windows[0]["window_end"] == HOUR and windows[0]["headlines"] == 3
    fields = windows[0]["fields"]
    assert set(fields) == {"tone", "rates"}
    assert fields["tone"]["value"] == "risk_off"
    assert fields["tone"]["quote"] == "Oil slips as OPEC+ signals no change to output"
    assert fields["tone"]["headline_id"] == "h3" and fields["rates"]["source"] == "Dow Jones"
    assert store_reads.newest_reading_window() == HOUR
    assert [r["field"] for r in store_reads.reading_window(HOUR)] == ["rates", "tone"]
    assert reading.api_rows(hours=1, now=NOW + 4 * 3600) == []       # an hour long past the window


# ── the hourly timer ─────────────────────────────────────────────────────────────────────────────────────────────
def test_the_registry_row_runs_hourly_through_the_dashboard():
    e = automations.entry("RC-News-Reading-Hourly")
    assert e.hourly and e.time.endswith(":20") and e.days == () and e.after is None
    assert e.schedule == "hourly at :20 (local)"
    assert e.args == ("-m", "revenuechaser.scripts.board_fetch", "news-reading")
    assert e.tables_written == ("news_reading",) and e.unit == "life-rc-fetch-news-reading"
    assert not e.default_install and not e.offpeak_gated


def test_the_task_queues_the_dashboard_job_and_waits_for_no_session():
    from revenuechaser.scripts import board_fetch
    assert board_fetch.ROUTES["news-reading"] == "news_reading"
    # The hour that has just finished is not a trading session: the pass must not wait for SPY's bar.
    assert "news-reading" not in board_fetch.NEEDS_SESSION


# ── the dashboard: the one writer ────────────────────────────────────────────────────────────────────────────────
def _client():
    from revenuechaser.app import dashboard
    from revenuechaser.core.tests.panel_client import panel_test_client
    dashboard.app.config["TESTING"] = True
    return dashboard, panel_test_client(dashboard.app)


def test_the_route_queues_the_pass_in_the_dashboard_and_paid_is_never_the_default(monkeypatch):
    """The dashboard holds the DuckDB writer (CLAUDE.md), so the hourly task queues it here and writes nothing
    itself. ``paid`` has to be said on the request: it is avo's word, never a default."""
    dashboard, client = _client()
    captured = []
    monkeypatch.setattr(dashboard.jobs, "submit", lambda module, params: captured.append((module, params)) or "j1")
    monkeypatch.setattr(dashboard.jobs, "active_id", lambda modules: None)

    assert client.post("/run/news_reading").status_code == 202
    assert captured == [("news_reading", {"allow_paid": False})]

    assert client.post("/run/news_reading", json={"paid": "1"}).status_code == 202
    assert captured[-1] == ("news_reading", {"allow_paid": True})

    monkeypatch.setattr(dashboard.jobs, "active_id", lambda modules: "busy")
    r = client.post("/run/news_reading")
    assert r.status_code == 409 and r.get_json()["job_id"] == "busy" and len(captured) == 2


def test_the_read_route_serves_the_stored_windows(monkeypatch):
    """The route reads the real clock, so this one stores the hour that has really just finished.

    A fixed past ``HOUR`` cannot be used here: ``hours`` is counted back from now, so a reading of a day the
    test chose would fall outside the route's default window and the route would correctly answer nothing.
    """
    start, end = reading.window()
    _store_headlines([("r1", "Oil slips as OPEC+ signals no change to output", "Briefing", end - 600, [])])
    _writer(monkeypatch, _reply({"tone": {"value": "risk_off", "headline_id": "r1",
                                          "quote": "Oil slips as OPEC+ signals no change to output"}}))
    assert reading.run()["stored"] == 1
    _dashboard, client = _client()
    body = client.get("/api/news/reading").get_json()
    assert body["ok"] and body["fields"] == list(reading.FIELDS)
    window = next(w for w in body["windows"] if w["window_end"] == end)
    assert window["window_start"] == start
    assert window["fields"]["tone"]["quote"] == "Oil slips as OPEC+ signals no change to output"
    assert client.get("/api/news/reading", query_string={"hours": "x"}).status_code == 400
    assert client.get("/api/news/reading", query_string={"hours": "0"}).status_code == 400


def test_the_job_is_wired_and_the_runner_notes_what_it_stored(monkeypatch):
    from revenuechaser.app import jobs, runners
    assert jobs._PRODUCES["news_reading"] == []            # it writes no page; the shell reloads nothing
    notes = []
    monkeypatch.setattr(runners.ledger, "add_note", notes.append)
    monkeypatch.setattr(reading, "run", lambda **kw: {
        "window_start": HOUR - 3600, "window_end": HOUR, "headlines": 12, "stored": 2,
        "unsourced": ["tone: no quote"], "provider": "evren", "model": "m", "skipped": None, "error": None})
    assert runners.run_news_reading() is None
    assert "2 of 7 fields stored from 12 headlines" in notes[0] and "tone: no quote" in notes[0]

    monkeypatch.setattr(reading, "run", lambda **kw: dict(
        window_start=0, window_end=0, headlines=0, stored=0, unsourced=[], provider=None, model=None,
        skipped="no headline was stored in this hour", error=None))
    runners.run_news_reading()
    assert "no headline" in notes[1]
