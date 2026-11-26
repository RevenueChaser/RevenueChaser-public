"""The SEC reader tool, step 1 (plan 2026-11-15_1119): the dataset ``sec/reads``, the question registry, the one
asker with its provider pools, ``read_answer``, its reader and the need ``sec.read``.

No real question exists yet, so each test registers its own and answers EVREN and DeepSeek at the HTTP boundary
(``http_mock``). The run is driven the way production drives it: one builder request of ``sec/reads``.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime, timezone

import pytest

from revenuechaser.core import job_lock
from revenuechaser.core.providers import deepseek, evren
from revenuechaser.rcdata import read, serving
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.sec_reads import asker, questions, reads
from revenuechaser.rcdata.needs import serve

from . import fund_fixture as fx

EVREN = "https://evren.test/v1"
DEEPSEEK = "https://deepseek.test"
TEXT = {"789019": "Microsoft makes software and cloud services.", "320193": "Apple makes phones."}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("LITELLM_RC_KEY", "sentinel-gate")
    monkeypatch.setenv("RC_EVREN_BASE", EVREN)
    monkeypatch.setenv("RC_DEEPSEEK_BASE", DEEPSEEK)
    monkeypatch.setattr(evren, "_sleep", lambda s: None)
    monkeypatch.setattr(deepseek, "peak_blocked", lambda now=None: False)
    monkeypatch.setattr(questions, "QUESTIONS", {})
    monkeypatch.setattr(reads, "QUESTIONS", questions.QUESTIONS)


def chat(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 3}}


def parse(reply: str) -> dict | None:
    data = json.loads(reply)
    return data if data.get("products") else None


def question(ciks=("789019", "320193", "999"), text=None, **kw) -> questions.Question:
    text = TEXT if text is None else text
    if kw.get("provider") == "deepseek":
        kw.setdefault("max_calls", 100)                     # a DeepSeek question must name its cap
    q = questions.Question(
        id=kw.pop("id", "test.products"), owner="test", system="List the products as JSON.",
        prompt_version=kw.pop("prompt_version", "t1"), scope=lambda: list(ciks),
        inputs=kw.pop("inputs", None) or (
            lambda wanted: {c: questions.Input(f"acc-{c}", f"{c}.htm", date(2026, 2, 1), text[c], "ours-2")
                            for c in wanted if c in text}),
        parse=parse, **kw)
    return questions.register(q)


def run(reread: bool = True) -> dict:
    """One request. ``reread`` is the owner's word, on by default so a test's first pass is asked; the tests of the
    guard itself pass False, which is what a timer or a plain Fetch sends."""
    return fx.run(reads.NAME, **({"reread": True} if reread else {}))


def rows(sql: str = "SELECT cik, status, attempts FROM read_answer ORDER BY cik") -> list[tuple]:
    con = serving.open_read("sec_reads")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_with_no_question_the_run_builds_an_empty_table_and_sends_nothing(http_mock):
    check = run()
    assert check["result"] in ("changed", "unchanged") and "no question registered" in check["note"]
    assert rows() == [] and http_mock.requests == []
    assert serve.summary("sec.read")["row_count"] == 0


def test_a_question_is_asked_once_stored_served_and_never_asked_again(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["Azure"]}'))
    question()
    run()
    assert len(http_mock.requests) == 2                    # two companies with text; the third has none
    assert rows() == [("320193", "ok", 1), ("789019", "ok", 1), ("999", "no_text", 0)]
    body = json.loads(http_mock.requests[0].content)
    assert body["model"] == "evren-deepseek-v4.1-flash"         # the gate's EVREN name
    assert body["messages"][0]["content"] == "List the products as JSON."

    got = read.sec_reads(["0000789019", "999"], "test.products")
    assert [(r["cik"], r["answer"], r["accession"]) for r in got] == [("789019", {"products": ["Azure"]},
                                                                      "acc-789019")]
    assert "raw" not in got[0]
    answer = serve.ask("sec.read", ciks=["789019"], question="test.products")
    assert answer.rows and answer.rows[0]["answer"] == {"products": ["Azure"]}

    run()
    assert len(http_mock.requests) == 2                    # same bytes, same key: no new call


def test_a_new_text_or_prompt_version_is_a_new_key(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    question(ciks=("789019",))
    run()
    questions.QUESTIONS.clear()
    question(ciks=("789019",), text={"789019": "Microsoft makes games too."})
    run()
    assert len(http_mock.requests) == 2
    assert rows("SELECT count(DISTINCT input_hash) FROM read_answer") == [(2,)]


def test_an_unusable_reply_is_counted_and_asked_at_most_three_times(http_mock):
    http_mock.add("/chat/completions", chat('{"products": []}'))
    question(ciks=("789019",))
    for _ in range(4):
        run()
    assert len(http_mock.requests) == reads.MAX_ATTEMPTS
    assert rows() == [("789019", "empty", 3)]
    assert read.sec_reads(["789019"], "test.products") == []          # an empty row is not an answer


def test_a_partial_answer_is_never_replaced_by_an_empty_one(http_mock):
    replies = iter([chat('{"products": ["a"]}'), chat('{"products": []}'),       # run 1: chunk 2 unusable
                    chat('{"products": []}'), chat('{"products": []}')])         # run 2: both unusable
    http_mock.add("/chat/completions", lambda req: (200, json.dumps(next(replies)), {}))
    question(ciks=("789019",), chunk_chars=30)              # the text is 44 characters: two chunks
    run()
    assert rows("SELECT status, attempts, missing_chunks FROM read_answer") == [("partial", 1, "1")]
    run()
    assert rows("SELECT status, attempts, missing_chunks, answer FROM read_answer") == [
        ("partial", 2, "1", '{"products": ["a"]}')]


def test_no_read_starts_while_the_relatedness_model_job_runs(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    question(ciks=("789019",))
    with job_lock.acquire(asker.RELATEDNESS_LOCK) as got:
        assert got
        check = run()
    assert check["result"] == "failed" and "one model job at a time" in check["note"]
    assert http_mock.requests == []


def test_evren_gets_one_request_at_a_time_and_deepseek_eight():
    assert asker.POOLS == {"evren": 1, "deepseek": 8}


def _in_flight(http_mock, path: str) -> list[int]:
    seen, lock, now = [], threading.Lock(), [0]

    def answer(req):
        with lock:
            now[0] += 1
            seen.append(now[0])
        time.sleep(0.02)
        with lock:
            now[0] -= 1
        return 200, json.dumps(chat('{"products": ["x"]}')), {}
    http_mock.add(path, answer)
    return seen


def test_the_pools_hold_their_caps_on_the_wire(http_mock):
    many = {str(1000 + i): f"company {i}" for i in range(12)}
    seen = _in_flight(http_mock, "/chat/completions")
    question(ciks=tuple(many), text=many)
    run()
    assert len(seen) == 12 and max(seen) == 1                   # EVREN: never two at once
    seen.clear()
    question(id="test.deepseek", ciks=tuple(many), text=many, provider="deepseek")
    run()
    assert len(seen) == 12 and 1 < max(seen) <= 8
    assert {json.loads(r.content)["model"] for r in http_mock.requests[12:]} == {"deepseek-v4-flash-nothink"}  # the gate's Flash name


def test_a_run_stops_at_its_slice_and_the_next_run_asks_the_rest(http_mock, monkeypatch):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    monkeypatch.setattr(asker, "SLICE_S", -1.0)             # the slice is spent before the first company
    question()
    check = run()
    assert http_mock.requests == [] and "2 left for the next run" in check["note"]
    monkeypatch.setattr(asker, "SLICE_S", 900.0)
    run()
    assert len(http_mock.requests) == 2


def test_a_fetch_only_run_asks_for_the_slice_the_environment_gives(http_mock, monkeypatch):
    """``--no-duckdb`` takes no builder lock, so R1 does not apply and the run may ask for longer: the whole
    reason the 15-minute slice exists is the lock this run never holds (debt.note, 25 Nov 2026)."""
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    monkeypatch.setattr(asker, "SLICE_S", -1.0)             # the default slice is spent before the first company
    monkeypatch.setenv(asker.SLICE_ENV, "7200")
    question()
    fx.run(reads.NAME, reread=True, no_duckdb=True)
    assert len(http_mock.requests) == 2                     # asked anyway: the env slice is what the run read


def test_a_run_that_builds_ignores_the_slice_environment(http_mock, monkeypatch):
    monkeypatch.setattr(asker, "SLICE_S", -1.0)
    monkeypatch.setenv(asker.SLICE_ENV, "7200")
    question()
    check = run()
    assert http_mock.requests == [] and "2 left for the next run" in check["note"]
    assert asker.SLICE_ENV in check["note"]                 # and the run says why it kept the default


def test_a_slice_value_that_is_not_positive_seconds_keeps_the_default(monkeypatch):
    monkeypatch.setenv(asker.SLICE_ENV, "nope")
    ctx = base.RunContext(run_id="r1", dataset=reads.NAME, skip_build=True)
    assert asker.slice_s(ctx) == asker.SLICE_S
    assert any(asker.SLICE_ENV in n and "positive" in n for n in ctx.notes)


def test_a_provider_stop_keeps_the_answers_already_paid_for(http_mock):
    calls = iter([(200, json.dumps(chat('{"products": ["x"]}')), {}), (401, "{}", {})])
    http_mock.add("/chat/completions", lambda req: next(calls))
    question()
    check = run()
    assert check["result"] == "failed"
    held = reads.held("test.products")
    assert [r["status"] for r in held.values()].count("ok") == 1


def test_a_writer_that_is_down_skips_its_questions_and_does_not_fail_the_run(http_mock, monkeypatch):
    """avo's night: every question is on EVREN now (19 Nov 2026), so an EVREN outage would end the whole step as
    failed and the chain behind it (Value Chain) would not run that night (Fable report F6). A transient outage
    skips that writer's questions, leaves every company stale for the next pass, and the run ends green; the other
    writer is still asked."""
    monkeypatch.setattr(asker, "TRANSIENT_STOP", 1)
    http_mock.add("evren.test", lambda req: (503, "{}", {}))        # the gate is down: a 5xx, final
    http_mock.add("deepseek.test", chat('{"products": ["Azure"]}'))
    question(ciks=("789019", "320193"))                             # EVREN, asked first
    question(id="test.second", ciks=("789019",))                    # EVREN too: not asked at all
    question(id="test.deepseek", ciks=("789019",), provider="deepseek")

    check = run()
    assert check["result"] != "failed"
    assert "evren is down" in check["note"] and "test.second: not asked" in check["note"]
    assert len(http_mock.calls("evren.test")) == 1                  # one company, then the writer is down
    assert len(http_mock.calls("deepseek.test")) == 1
    assert rows("SELECT question, cik, status FROM read_answer ORDER BY question, cik") == [
        ("test.deepseek", "789019", "ok")]                          # nothing stored for the writer that is down

    http_mock.routes.clear()                                        # the gate is back: the next run asks them
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    run()
    assert rows("SELECT count(*) FROM read_answer WHERE status = 'ok'") == [(4,)]


def test_a_rejected_key_and_a_wrong_endpoint_still_fail_the_run(http_mock):
    """Only the writer being down is tolerated: a key the gate rejects and a run whose replies are all unusable are
    the run's own failure, and a green run must not hide either."""
    assert reads.outage(evren.EvrenTransientError("HTTP 503")) is True
    assert reads.outage(evren.EvrenAuthError("rejected")) is False
    assert reads.outage(deepseek.DeepSeekTransientError("timeout")) is True
    assert reads.outage(deepseek.DeepSeekAuthError("401")) is False

    http_mock.add("/chat/completions", lambda req: (401, "{}", {}))
    question(ciks=("789019",))
    assert run()["result"] == "failed"


def test_the_registry_refuses_a_pro_model_an_unknown_provider_and_a_second_owner():
    with pytest.raises(ValueError, match="never Pro"):
        question(provider="deepseek", model="deepseek-pro")
    with pytest.raises(ValueError, match="no pool"):
        question(provider="grok")
    with pytest.raises(ValueError, match="needs max_calls"):
        question(provider="deepseek", max_calls=None)
    question()
    with pytest.raises(ValueError, match="already registered"):
        question()


def test_a_stop_inside_a_filing_keeps_the_chunks_already_answered(http_mock):
    calls = iter([(200, json.dumps(chat('{"products": ["a"]}')), {}), (401, "{}", {})])
    http_mock.add("/chat/completions", lambda req: next(calls))
    question(ciks=("789019",), chunk_chars=30)              # two chunks; the second is refused
    check = run()
    assert check["result"] == "failed"
    assert [(r["status"], r["attempts"], r["missing_chunks"], r["answer"]) for r in
            reads.held("test.products").values()] == [("partial", 0, "1", '{"products": ["a"]}')]  # not an attempt


def test_a_questions_merge_is_given_each_answer_with_the_length_of_its_message(http_mock):
    """The profile weights a segment's share by its chunk's length, so the lengths go to the merge."""
    http_mock.add("/chat/completions", chat('{"products": ["a"]}'))
    seen = []
    question(ciks=("789019",), chunk_chars=30,
             merge=lambda parts: seen.append([chars for _answer, chars in parts]) or parts[0][0])
    run()
    assert seen == [[30, len(TEXT["789019"]) - 30]]
    assert [r["answer"] for r in reads.held("test.products").values()] == ['{"products": ["a"]}']


def test_a_question_that_keeps_no_text_reads_one_company_at_a_time(http_mock):
    """``inputs`` gives a hash and no text; ``fill`` gives the text of the company being asked, and only of it."""
    from dataclasses import replace
    http_mock.add("/chat/completions", chat('{"products": ["Azure"]}'))
    filled = []

    def fill(cik, inp):
        filled.append(cik)
        return replace(inp, text=TEXT[cik], messages=(f"Company {cik}: {TEXT[cik]}",))

    q = questions.register(questions.Question(
        id="test.light", owner="test", system="List the products as JSON.", prompt_version="t1",
        scope=lambda: ["789019", "320193", "999"],
        inputs=lambda wanted: {c: questions.Input(f"acc-{c}", f"{c}.htm", date(2026, 2, 1), "", "ours-2",
                                                  hash=f"hash-of-{c}") for c in wanted if c in TEXT},
        parse=parse, fill=fill))
    run()
    assert sorted(filled) == ["320193", "789019"]
    sent = sorted(json.loads(r.content)["messages"][1]["content"] for r in http_mock.requests)
    assert sent == [f"Company 320193: {TEXT['320193']}", f"Company 789019: {TEXT['789019']}"]
    assert [(k[2], k[5], r["status"]) for k, r in sorted(reads.held(q.id).items())] == [
        ("320193", "hash-of-320193", "ok"), ("789019", "hash-of-789019", "ok"), ("999", "", "no_text")]

    run()
    assert len(filled) == 2 and len(http_mock.requests) == 2        # the same hash: nothing is read or asked again


def test_deepseek_off_peak_holds_back_only_its_own_questions(http_mock, monkeypatch):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    monkeypatch.setattr(deepseek, "peak_blocked", lambda now=None: True)
    question(ciks=("789019",))
    question(id="test.deepseek", ciks=("789019",), provider="deepseek")
    check = run()
    assert len(http_mock.requests) == 1 and EVREN in str(http_mock.requests[0].url)
    assert "DeepSeek is off-peak only" in check["note"] and "1 left for the next run" in check["note"]


def test_a_reply_cut_short_counts_no_attempt_and_never_shrinks_a_partial(http_mock):
    ok, bad, refused = (200, json.dumps(chat('{"products": ["a"]}')), {}), \
        (200, json.dumps(chat('{"products": []}')), {}), (401, "{}", {})
    calls = iter([ok, ok, bad,          # run 1: chunks 0 and 1 answered, chunk 2 unusable -> partial
                  ok, refused])         # run 2: chunk 0 answered, then the provider stops
    http_mock.add("/chat/completions", lambda req: next(calls))
    question(ciks=("789019",), chunk_chars=15)              # the text is 44 characters: three chunks
    run()
    assert rows("SELECT status, attempts, missing_chunks FROM read_answer") == [("partial", 1, "2")]
    run()
    held = list(reads.held("test.products").values())
    assert [(r["status"], r["attempts"], r["missing_chunks"]) for r in held] == [("partial", 1, "2")]


# ── Serving version 2 (plan 2026-11-15_1722, step 1): the four gaps and the failure log ─────────────────────────

def test_a_changed_context_asks_nothing_again_when_the_staleness_text_is_the_same(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))

    def ask_with(context: str):
        questions.QUESTIONS.clear()
        questions.register(questions.Question(
            id="test.products", owner="test", system="s", prompt_version="t1", scope=lambda: ["789019"],
            inputs=lambda wanted: {"789019": questions.Input("acc", "d.htm", date(2026, 2, 1),
                                                             f"Sector: {context}\n\nMicrosoft makes software.",
                                                             hash_text="Microsoft makes software.")},
            parse=parse))
        run()

    ask_with("Technology")
    ask_with("Communication Services")                     # reclassified: other bytes sent, the same staleness text
    assert len(http_mock.requests) == 1
    assert rows("SELECT count(*) FROM read_answer") == [(1,)]


def test_an_answer_by_another_writer_is_current_and_is_what_a_board_reads(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["Azure"]}'))
    question(ciks=("789019",), provider="deepseek")
    run()
    questions.QUESTIONS.clear()
    question(ciks=("789019",))                             # the writer goes back to EVREN: nothing is asked again
    run()
    assert len(http_mock.requests) == 1
    assert [(r["provider"], r["answer"]) for r in read.sec_reads(["789019"], "test.products")] == [
        ("deepseek", {"products": ["Azure"]})]
    assert read.sec_reads(["789019"], "test.products", provider="evren") == []


def test_an_answer_carries_what_was_read_and_what_it_cost(http_mock):
    reply = {**chat('{"products": ["a"]}'), "usage": {"prompt_tokens": 40, "completion_tokens": 7}}
    http_mock.add("/chat/completions", reply)
    questions.register(questions.Question(
        id="test.products", owner="test", system="s", prompt_version="t1", scope=lambda: ["789019"],
        inputs=lambda wanted: {"789019": questions.Input("acc", "d.htm", date(2026, 2, 1), TEXT["789019"],
                                                         kind="section:business", form="10-K",
                                                         report_date=date(2025, 12, 31))},
        parse=parse, chunk_chars=30))                      # the text is 44 characters: two calls
    run()
    assert rows("SELECT form, input_kind, calls, tokens_in, tokens_out, error FROM read_answer") == [
        ("10-K", "section:business", 2, 80, 14, None)]
    assert rows("SELECT report_date FROM read_answer") == [(date(2025, 12, 31),)]     # serving version 3
    assert read.sec_reads(["789019"], "test.products")[0]["report_date"] == date(2025, 12, 31)


def test_every_call_is_logged_with_how_it_failed(http_mock, monkeypatch):
    logged = []
    monkeypatch.setattr(asker.ops, "log_call", lambda provider, what=None, **kw: logged.append((what, kw["result"])))
    calls = iter([(400, "context too long", {}), (200, json.dumps(chat('{"products": []}')), {}),
                  (200, json.dumps(chat('{"products": ["a"]}')), {})])
    http_mock.add("/chat/completions", lambda req: next(calls))
    question(ciks=("789019",), chunk_chars=15)             # three chunks: an error, an unusable reply, an answer
    run()
    assert [w for w, _ in logged] == [f"test.products cik 789019 chunk {i}/3" for i in (1, 2, 3)]
    assert "EvrenError: EVREN HTTP 400: context too long" in logged[0][1] and [r for _, r in logged[1:]] == ["unusable reply", "ok"]
    assert rows("SELECT status, missing_chunks, error FROM read_answer") == [("partial", "0,1", "unusable reply")]


# ── The Fable review of 15 Nov 2026 (claude-coordinator reviews/2026-11-15_1905): F1 to F5 ─────────────────────

def test_a_second_asker_asks_nothing_while_one_holds_the_ask_lock(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    question(ciks=("789019",))
    with job_lock.acquire(asker.ASK_LOCK) as got:
        assert got
        check = run()
    assert http_mock.requests == [] and "another SEC read is asking" in check["note"]
    run()
    assert len(http_mock.requests) == 1


def test_a_question_is_answered_before_the_next_one_builds_its_inputs(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    seen = []
    question(id="test.first", ciks=("789019",))

    def inputs(wanted):
        seen.append([r["status"] for r in reads.held("test.first").values()])
        return {"789019": questions.Input("acc", "d.htm", date(2026, 2, 1), "second text")}

    questions.register(questions.Question(id="test.second", owner="test", system="s", prompt_version="t1",
                                          scope=lambda: ["789019"], inputs=inputs, parse=parse))
    run()
    assert seen == [["ok"]] and len(http_mock.requests) == 2


def test_a_board_reads_the_current_prompt_version_whoever_wrote_it(http_mock):
    replies = iter([chat('{"products": ["old"]}'), chat('{"products": ["new"]}')])
    http_mock.add("/chat/completions", lambda req: (200, json.dumps(next(replies)), {}))
    question(ciks=("789019",))                             # EVREN, the configured writer, prompt t1
    run()
    questions.QUESTIONS.clear()
    question(ciks=("789019",), provider="deepseek", prompt_version="t2")   # a bulk pass by the other writer
    run()
    questions.QUESTIONS.clear()
    question(ciks=("789019",), prompt_version="t2")        # the writer goes back to EVREN
    run()
    assert len(http_mock.requests) == 2                    # t2 is answered: nothing asked again
    assert [(r["prompt_version"], r["answer"]) for r in read.sec_reads(["789019"], "test.products")] == [
        ("t2", {"products": ["new"]})]


def test_a_run_whose_first_replies_are_all_unusable_stops_and_stores_none(http_mock):
    many = {str(1000 + i): f"company {i}" for i in range(8)}
    http_mock.add("/chat/completions", chat('{"products": []}'))
    question(ciks=tuple(many), text=many)
    check = run()
    assert check["result"] == "failed" and "all unusable" in check["note"]
    assert len(http_mock.requests) == asker.UNUSABLE_STOP and reads.held("test.products") == {}


def test_a_key_at_its_attempts_is_tried_again_after_the_retry_time(http_mock, monkeypatch):
    http_mock.add("/chat/completions", chat('{"products": []}'))
    question(ciks=("789019",))
    for _ in range(4):
        run()
    assert len(http_mock.requests) == reads.MAX_ATTEMPTS
    monkeypatch.setattr(reads, "RETRY_AFTER_S", 0.0)
    run()
    assert len(http_mock.requests) == reads.MAX_ATTEMPTS + 1


def test_nothing_is_asked_when_the_parquet_tree_is_behind_the_live_table(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    question(ciks=("789019",))
    run()
    reads.partition_path("test.products").unlink()         # the tree is lost; the live table still has the answer
    check = run()
    assert check["result"] == "failed" and "the tree is behind" in check["note"]
    assert len(http_mock.requests) == 1


# ── The same review, F6, F8 and F9 ──────────────────────────────────────────────────────────────────────────────
def test_a_question_sends_its_inputs_ready_messages_and_keeps_the_staleness_text(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    body = "Microsoft makes software. It sells cloud."

    def ask_with(context: str):
        questions.QUESTIONS.clear()
        questions.register(questions.Question(
            id="test.products", owner="test", system="s", prompt_version="t1", scope=lambda: ["789019"],
            inputs=lambda wanted: {"789019": questions.Input(
                "acc", "d.htm", date(2026, 2, 1), body, hash_text=body,
                messages=(f"{context} (part 1 of 2)\nMicrosoft makes software.",
                          f"{context} (part 2 of 2)\nIt sells cloud."))},
            parse=parse))
        run()

    ask_with("Sector: Technology")
    assert [json.loads(r.content)["messages"][-1]["content"] for r in http_mock.requests] == [
        "Sector: Technology (part 1 of 2)\nMicrosoft makes software.",
        "Sector: Technology (part 2 of 2)\nIt sells cloud."]       # the input's own bytes, not a slice of its text
    ask_with("Sector: Communication Services")
    assert len(http_mock.requests) == 2                             # the same staleness text: nothing asked again
    assert rows("SELECT status, calls FROM read_answer") == [("ok", 2)]


def test_a_transient_error_gives_up_on_one_company_and_the_run_goes_on(http_mock):
    calls = iter([(500, "busy", {}), (200, json.dumps(chat('{"products": ["x"]}')), {})])
    http_mock.add("/chat/completions", lambda req: next(calls))
    question()                                                      # 320193 is asked first and times out
    check = run()
    assert check["result"] != "failed" and "1 left for the next run" in check["note"]
    assert rows("SELECT cik, status, attempts FROM read_answer WHERE status <> 'no_text'") == [("789019", "ok", 1)]


def test_the_fifth_company_with_a_transient_error_stops_the_run(http_mock):
    """The fifth transient company still stops the asking and stores nothing; since 19 Nov 2026 the run itself does
    not fail on it, because the writer being down is not the step's failure (``reads.outage``, and the test above:
    a failed step keeps Value Chain from running that night)."""
    many = {str(1000 + i): f"company {i}" for i in range(8)}
    http_mock.add("/chat/completions", lambda req: (500, "busy", {}))
    question(ciks=tuple(many), text=many)
    check = run()
    assert check["result"] != "failed" and "evren is down" in check["note"]
    assert len(http_mock.requests) == asker.TRANSIENT_STOP and reads.held("test.products") == {}


def test_a_run_sends_at_most_the_questions_max_calls(http_mock):
    many = {str(1000 + i): f"company {i}" for i in range(6)}
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    question(ciks=tuple(many), text=many, max_calls=4)
    check = run()
    assert len(http_mock.requests) == 4
    assert "cap of 4 calls" in check["note"] and "2 left for the next run" in check["note"]
    run()
    assert len(http_mock.requests) == 6                             # the next run asks the rest


# ── The review of 16 Nov 2026 (claude-coordinator reviews/2026-11-16_0750_sec-engine-review-summary.md) ─────────
def filing(accession: str, day: date, text: str, **kw):
    """A question over company 789019 whose one input is this filing."""
    questions.QUESTIONS.clear()
    return questions.register(questions.Question(
        id="test.products", owner="test", system="s", prompt_version=kw.pop("prompt_version", "t1"),
        scope=lambda: ["789019"], parse=parse,
        inputs=lambda wanted: {"789019": questions.Input(accession, "d.htm", day, text)}, **kw))


def test_a_run_without_the_owners_word_asks_a_new_filing_and_never_a_changed_prompt(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    filing("acc-2025", date(2025, 2, 1), "Microsoft makes software.")
    check = run(reread=False)                               # a question's first pass waits for the word
    assert http_mock.requests == [] and "1 wait for the owner's word" in check["note"] and "first 1" in check["note"]
    run()
    assert len(http_mock.requests) == 1
    filing("acc-2026", date(2026, 2, 1), "Microsoft makes software and games.")
    run(reread=False)                                       # next year's report: asked by itself
    assert len(http_mock.requests) == 2
    filing("acc-2026", date(2026, 2, 1), "Microsoft makes software and games.", prompt_version="t2")
    check = run(reread=False)                               # a new prompt would re-read every company
    assert len(http_mock.requests) == 2 and "changed 1" in check["note"]
    filing("acc-2026", date(2026, 2, 1), "Microsoft makes software, games and chips.")
    check = run(reread=False)                               # the same filing cut again: a re-cut of every filing
    assert len(http_mock.requests) == 2 and "changed 1" in check["note"]
    run()
    assert len(http_mock.requests) == 3


def test_a_run_without_the_word_stops_at_the_day_cap_and_goes_on_the_next_day(http_mock, monkeypatch):
    many = {str(1000 + i): f"company {i}" for i in range(6)}
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    monkeypatch.setattr(reads, "DAY_CAP", 3)
    question(ciks=("1000",), text=many, provider="deepseek")
    run()                                                   # one company asked today, by hand
    questions.QUESTIONS.clear()
    question(ciks=tuple(many), text=many, provider="deepseek")
    check = run(reread=False)
    # New companies are asked by themselves once the question has answers; the cap counts today's, whoever asked.
    assert len(http_mock.requests) == 3
    assert "day cap of 3" in check["note"] and "3 wait for tomorrow" in check["note"]
    assert run(reread=False) and len(http_mock.requests) == 3
    monkeypatch.setattr(reads, "_now", lambda: time.time() + 2 * 86400)
    run(reread=False)
    assert len(http_mock.requests) == 6


def test_an_evren_question_has_no_day_cap(http_mock, monkeypatch):
    many = {str(1000 + i): f"company {i}" for i in range(6)}
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    monkeypatch.setattr(reads, "DAY_CAP", 3)
    question(ciks=("1000",), text=many)
    run()
    questions.QUESTIONS.clear()
    question(ciks=tuple(many), text=many)                   # five new companies in one day: EVREN has no quota
    check = run(reread=False)
    assert len(http_mock.requests) == 6 and "day cap" not in check["note"]


def test_many_companies_with_no_answer_at_once_are_a_scope_change_and_wait_for_the_word(http_mock, monkeypatch):
    many = {str(1000 + i): f"company {i}" for i in range(6)}
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    monkeypatch.setattr(reads, "NEW_COMPANY_LIMIT", 3)
    question(ciks=("1000",), text=many)
    run()
    questions.QUESTIONS.clear()
    question(ciks=tuple(many)[:4], text=many)               # three new companies: asked by themselves
    run(reread=False)
    assert len(http_mock.requests) == 4
    questions.QUESTIONS.clear()
    monkeypatch.setattr(reads, "NEW_COMPANY_LIMIT", 1)
    question(ciks=tuple(many), text=many)                   # two more at once, over the limit: a scope change
    check = run(reread=False)
    assert len(http_mock.requests) == 4 and "new_company 2" in check["note"]
    run()                                                   # the owner's word
    assert len(http_mock.requests) == 6


def test_the_plan_counts_what_a_run_would_ask_and_calls_nobody(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    question(ciks=("789019", "320193"))
    assert reads.plan_counts()["would_ask"] == {"test.products": 0}        # a first pass waits for the word
    assert reads.plan_counts(reread=True)["would_ask"] == {"test.products": 2}
    assert len(http_mock.requests) == 0
    run()
    assert reads.plan_counts(reread=True)["would_ask"] == {"test.products": 0}


def test_a_word_for_one_question_rereads_that_one_and_leaves_the_others_waiting(http_mock):
    """25 Nov 2026: debt.note's 316 needed the owner's word, and the only word there was would also have asked
    company.profile's 4,769. A request's ``"reread"`` may name the questions it is for."""
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    question(ciks=("789019",))
    question(id="test.other", ciks=("320193",))
    assert reads.plan_counts(reread=("test.products",))["would_ask"] == {"test.products": 1, "test.other": 0}
    fx.run(reads.NAME, reread="yes")                        # not true and not a list: no word at all
    assert len(http_mock.requests) == 0
    check = fx.run(reads.NAME, reread=["test.products"])
    assert len(http_mock.requests) == 1
    assert rows("SELECT question, cik FROM read_answer WHERE status = 'ok'") == [("test.products", "789019")]
    assert "test.other: 1 wait for the owner's word" in check["note"]


def test_a_usable_reply_after_the_unusable_stop_does_not_store_the_held_back_ones(http_mock, monkeypatch):
    many = {str(1000 + i): f"company {i}" for i in range(8)}
    gave_up = threading.Event()
    # Every request is in flight before any reply comes back: on a loaded runner the fifth unusable reply could
    # otherwise land before the eighth request was sent, and that one is then not asked at all (a flake, #920).
    arrived, all_in = [], threading.Event()
    real = asker.as_completed

    def in_order(futs):
        for n, f in enumerate(real(futs)):
            yield f
            if n == asker.UNUSABLE_STOP - 1:                # the run has read its fifth unusable reply
                gave_up.set()

    def reply(req):
        arrived.append(1)
        if len(arrived) >= len(many):
            all_in.set()
        all_in.wait(10)
        if any(f"company {i}" in req.content.decode() for i in range(5)):
            return 200, json.dumps(chat('{"products": []}')), {}
        gave_up.wait(10)                                    # in flight until the run has given up
        return 200, json.dumps(chat('{"products": ["x"]}')), {}

    monkeypatch.setattr(asker, "as_completed", in_order)
    http_mock.add("/chat/completions", reply)
    question(ciks=tuple(many), text=many, provider="deepseek")      # eight at a time
    check = run()
    assert check["result"] == "failed" and "all unusable" in check["note"]
    assert sorted((r["cik"], r["status"]) for r in reads.held("test.products").values()) == [
        ("1005", "ok"), ("1006", "ok"), ("1007", "ok")]


def test_the_builder_converts_nothing_after_the_ask_lock_is_released(http_mock, monkeypatch):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    seen = []
    real = reads.Reads.to_parquet_all

    def spy(self, ctx, raws):
        seen.append((len(raws), asker.ASK_LOCK in [name for name, _ in job_lock.holders()]))
        return real(self, ctx, raws)

    monkeypatch.setattr(reads.Reads, "to_parquet_all", spy)
    question()
    run()
    assert (1, True) in seen and all(locked for n, locked in seen if n)   # every write happens under the lock
    assert rows() == [("320193", "ok", 1), ("789019", "ok", 1), ("999", "no_text", 0)]


def test_a_board_reads_the_current_prompt_over_a_newer_filing_under_an_older_one(http_mock):
    replies = iter([chat('{"products": ["old prompt"]}'), chat('{"products": ["current prompt"]}')])
    http_mock.add("/chat/completions", lambda req: (200, json.dumps(next(replies)), {}))
    filing("acc-2026", date(2026, 2, 1), "the newer filing", prompt_version="t1")
    run()
    filing("acc-2025", date(2025, 2, 1), "the older filing", prompt_version="t2")     # e.g. an imported row
    run()
    assert [(r["prompt_version"], r["accession"]) for r in read.sec_reads(["789019"], "test.products")] == [
        ("t2", "acc-2025")]


def test_an_error_text_never_carries_the_gate_key(http_mock):
    http_mock.add("/chat/completions", lambda req: (400, "invalid key sentinel-gate for this model", {}))
    question(ciks=("789019",), provider="deepseek")
    run()
    (error,), = rows("SELECT error FROM read_answer")
    assert "sentinel-gate" not in error and "[key]" in error


def test_a_company_with_no_text_keeps_one_row_when_the_writer_changes(http_mock):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    question()
    run()
    questions.QUESTIONS.clear()
    question(provider="deepseek")
    run()
    assert rows("SELECT count(*) FROM read_answer WHERE status = 'no_text'") == [(1,)]


def test_a_company_given_up_on_gives_its_calls_back_to_the_runs_cap(http_mock):
    many = {str(1000 + i): f"company {i}" for i in range(3)}
    calls = iter([(500, "busy", {})] + [(200, json.dumps(chat('{"products": ["x"]}')), {})] * 2)
    http_mock.add("/chat/completions", lambda req: next(calls))
    question(ciks=tuple(many), text=many, max_calls=2)
    run()
    assert len(http_mock.requests) == 3                     # the failed company did not use up the cap
    assert rows("SELECT cik FROM read_answer WHERE status = 'ok' ORDER BY cik") == [("1001",), ("1002",)]


def test_a_flash_model_whose_name_only_contains_the_letters_pro_is_not_refused():
    question(id="test.improved", provider="deepseek", model="deepseek-v4-flash-improved")
    with pytest.raises(ValueError, match="never Pro"):
        question(id="test.pro", provider="deepseek", model="deepseek-v4-pro")


def test_the_daily_check_is_due_from_the_0105_amsterdam_pass(monkeypatch):
    """avo, 16 Nov 2026 09:51: the check runs at night. Its day starts at 19:00 New York, which is 01:00 Amsterdam."""
    from revenuechaser.core import calendar
    monkeypatch.setattr(calendar, "_now", lambda: datetime(2026, 11, 16, 23, 59, tzinfo=timezone.utc))  # 00:59 Tue
    assert reads.DATASET.default_as_of() == date(2026, 11, 15)
    monkeypatch.setattr(calendar, "_now", lambda: datetime(2026, 11, 17, 0, 5, tzinfo=timezone.utc))    # 01:05 Tue
    assert reads.DATASET.default_as_of() == date(2026, 11, 16)


def test_the_dataset_says_its_limits_for_the_settings_page_and_grafana():
    assert reads.DATASET.limits == "EVREN: no day cap · DeepSeek: 200 companies a day"


def test_a_no_text_row_carries_the_reason_the_question_named(http_mock):
    """#1419: a company with no text gets a ``no_text`` row, but nothing on it said why, so the board's coverage
    could not be explained and the reasons could not be counted. A question that names its reasons now has them
    stored in the row's ``error`` column; no new column, no schema bump."""
    http_mock.add("/chat/completions", chat('{"products": ["Azure"]}'))
    question(inputs=lambda wanted: (
        {c: questions.Input(f"acc-{c}", f"{c}.htm", date(2026, 2, 1), TEXT[c], "ours-2")
         for c in wanted if c in TEXT},
        {c: "no debt note" for c in wanted if c not in TEXT}))
    run()
    assert rows("SELECT cik, status, error FROM read_answer ORDER BY cik") == [
        ("320193", "ok", None), ("789019", "ok", None), ("999", "no_text", "no debt note")]



def test_a_stored_no_text_row_gains_the_reason_without_a_call(http_mock):
    """The backlog matters most: every company skipped before #1419 already has a ``no_text`` row, and a stored row
    stops a new one being written, so without this the reason would never appear for them. The row is written once
    more with the reason and nothing is asked for it.

    The first run is also the guard on the old shape: a question whose ``inputs`` returns the mapping alone names
    no reason and its row carries none. That half passes on the merge-base, which is the point of a guard, so it
    is asserted here rather than as a test of its own that ``red-on-base`` would list as proving nothing."""
    http_mock.add("/chat/completions", chat('{"products": ["Azure"]}'))
    question()
    run()
    assert rows("SELECT cik, error FROM read_answer WHERE status = 'no_text'") == [("999", None)]
    calls = len(http_mock.requests)

    questions.QUESTIONS.clear()
    question(inputs=lambda wanted: (
        {c: questions.Input(f"acc-{c}", f"{c}.htm", date(2026, 2, 1), TEXT[c], "ours-2")
         for c in wanted if c in TEXT},
        {c: "no debt note" for c in wanted if c not in TEXT}))
    run()
    assert rows("SELECT cik, status, error FROM read_answer WHERE status = 'no_text'") == [
        ("999", "no_text", "no debt note")]
    assert len(http_mock.requests) == calls          # the stored answers are current; nothing was asked again

