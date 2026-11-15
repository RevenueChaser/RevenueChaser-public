"""The SEC reader tool, step 1 (plan 2026-11-15_1119): the dataset ``sec/reads``, the question registry, the one
asker with its provider pools, ``read_answer``, its reader and the need ``sec.read``.

No real question exists yet, so each test registers its own and answers EVREN and DeepSeek at the HTTP boundary
(``http_mock``). The run is driven the way production drives it: one builder request of ``sec/reads``.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import date

import pytest

from RevenueChaser.core import job_lock
from RevenueChaser.core.providers import deepseek, evren
from RevenueChaser.rcdata import read, serving
from RevenueChaser.rcdata.build.sec_reads import asker, questions, reads
from RevenueChaser.rcdata.needs import serve

from . import fund_fixture as fx

EVREN = "https://evren.test/v1"
DEEPSEEK = "https://deepseek.test"
TEXT = {"789019": "Microsoft makes software and cloud services.", "320193": "Apple makes phones."}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("EVREN_API_KEY", "sentinel-evren")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sentinel-deepseek")
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
    q = questions.Question(
        id=kw.pop("id", "test.products"), owner="test", system="List the products as JSON.",
        prompt_version="t1", scope=lambda: list(ciks),
        inputs=lambda wanted: {c: questions.Input(f"acc-{c}", f"{c}.htm", date(2026, 2, 1), text[c], "ours-2")
                               for c in wanted if c in text},
        parse=parse, **kw)
    return questions.register(q)


def run() -> dict:
    return fx.run(reads.NAME)


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
    assert body["model"] == "deepseek-v4.1-flash"
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
    assert {json.loads(r.content)["model"] for r in http_mock.requests[12:]} == {"deepseek-flash"}


def test_a_run_stops_at_its_slice_and_the_next_run_asks_the_rest(http_mock, monkeypatch):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    monkeypatch.setattr(asker, "SLICE_S", -1.0)             # the slice is spent before the first company
    question()
    check = run()
    assert http_mock.requests == [] and "2 left for the next run" in check["note"]
    monkeypatch.setattr(asker, "SLICE_S", 900.0)
    run()
    assert len(http_mock.requests) == 2


def test_a_provider_stop_keeps_the_answers_already_paid_for(http_mock):
    calls = iter([(200, json.dumps(chat('{"products": ["x"]}')), {}), (401, "{}", {})])
    http_mock.add("/chat/completions", lambda req: next(calls))
    question()
    check = run()
    assert check["result"] == "failed"
    held = reads.held("test.products")
    assert [r["status"] for r in held.values()].count("ok") == 1


def test_the_registry_refuses_a_pro_model_an_unknown_provider_and_a_second_owner():
    with pytest.raises(ValueError, match="never Pro"):
        question(provider="deepseek", model="deepseek-pro")
    with pytest.raises(ValueError, match="no pool"):
        question(provider="grok")
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
            reads.held("test.products").values()] == [("partial", 1, "1", '{"products": ["a"]}')]


def test_deepseek_off_peak_holds_back_only_its_own_questions(http_mock, monkeypatch):
    http_mock.add("/chat/completions", chat('{"products": ["x"]}'))
    monkeypatch.setattr(deepseek, "peak_blocked", lambda now=None: True)
    question(ciks=("789019",))
    question(id="test.deepseek", ciks=("789019",), provider="deepseek")
    check = run()
    assert len(http_mock.requests) == 1 and EVREN in str(http_mock.requests[0].url)
    assert "DeepSeek is off-peak only" in check["note"] and "1 left for the next run" in check["note"]
