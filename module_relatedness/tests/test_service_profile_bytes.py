"""The SEC reading service's ``company.profile`` and ``business.locate`` send what the Relatedness board sends for
the same filing (#894).

Both sides are run for one company and the requests each makes are compared: the board's at its writer
(``profiles.deepseek.complete``), the service's at the HTTP boundary. Nothing is registered outside a test.
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.core import rawstore, universe
from revenuechaser.core.providers import evren
from revenuechaser.module_relatedness import config, engine, locator, profiles
from revenuechaser.module_relatedness.tests.test_locator_400 import DOC, PROFILE
from revenuechaser.module_relatedness.tests.test_sec_forms_reader_841 import filings_only, layer  # noqa: F401
from revenuechaser.rcdata import read
from revenuechaser.rcdata.build.sec_reads import company_profile as cp
from revenuechaser.rcdata.build.sec_reads import questions, reads
from revenuechaser.rcdata.tests import fund_fixture as fx
from revenuechaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401  (fixtures)

MSFT = "789019"


def answer(system: str, user: str) -> str:
    """The writer both sides talk to: the locator from the heading list, the profile from the text."""
    if system == locator.system_prompt():
        names = [line.split(": ", 1)[1] for line in user.split("Headings:\n", 1)[1].splitlines()]
        return json.dumps({"start": names.index("Our Company"), "end": names.index("Risk Factors")})
    return json.dumps(PROFILE)


@pytest.fixture
def world(layer, monkeypatch):  # noqa: F811
    """MSFT's stored annual report, a universe of that one company, and the writer on both sides. Returns
    ``(the board's requests, the mock the service's requests reach)``."""
    monkeypatch.setenv("LITELLM_RC_KEY", "sentinel-gate")
    monkeypatch.setenv("RC_EVREN_BASE", "https://evren.test/v1")
    monkeypatch.setattr(evren, "_sleep", lambda s: None)
    monkeypatch.setattr(questions, "QUESTIONS", {})
    monkeypatch.setattr(reads, "QUESTIONS", questions.QUESTIONS)
    monkeypatch.setattr(universe, "classification_universe", lambda *a, **k: ["MSFT"])
    board = []
    monkeypatch.setattr(profiles.deepseek, "complete",
                        lambda system, user, **k: board.append((system, user)) or answer(system, user))

    def gate(request):
        system, user = (m["content"] for m in json.loads(request.content)["messages"])
        return 200, json.dumps({"choices": [{"message": {"content": answer(system, user)}}],
                                "usage": {"total_tokens": 3}}), {}
    layer.add("/chat/completions", gate)
    return board, layer


def service_requests(mock) -> list[tuple[str, str]]:
    return [tuple(m["content"] for m in json.loads(r.content)["messages"]) for r in mock.calls("/chat/completions")]


def ask_the_service() -> dict:
    cp.register_all()
    return fx.run(reads.NAME, reread=True)


def suspect_cut(monkeypatch) -> None:
    """The rule cut is flagged suspect and the whole document is one whose headings the writer can place."""
    business, whole = read.form_business, read.form_whole
    monkeypatch.setattr(read, "form_business",
                        lambda ciks, **k: [{**d, "quality": "ok;suspect:S4"} for d in business(ciks, **k)])
    monkeypatch.setattr(read, "form_whole", lambda ciks, **k: [{**d, "text": DOC} for d in whole(ciks, **k)])


def test_the_service_sends_the_boards_request_for_a_rule_cut(world):
    board, mock = world
    engine.build_profiles(["MSFT"], usd_cap=1.0)
    assert len(board) == 1 and board[0][0] == cp.PROFILE.system

    inp = cp.PROFILE.inputs([MSFT])[MSFT]
    assert inp.text == "" and inp.messages == () and len(inp.hash) == 32      # the plan holds no company's text
    ask_the_service()
    assert service_requests(mock) == board
    (row,) = read.sec_reads([MSFT], cp.PROFILE_ID)
    assert row["answer"] == rawstore.get("relatedness_profiles", "MSFT")["profile_json"]
    assert row["input_hash"] == inp.hash
    (doc,) = read.form_business([MSFT], text=False)
    assert row["report_date"] == doc["report_date"]             # the period the filing reports on
    assert read.sec_reads([MSFT], cp.LOCATE_ID) == []                         # an unflagged cut asks no locator


def test_the_service_sends_the_boards_two_requests_for_a_suspect_cut(world, monkeypatch):
    board, mock = world
    suspect_cut(monkeypatch)
    engine.build_profiles(["MSFT"], usd_cap=1.0)
    assert [system for system, _user in board] == [locator.system_prompt(), profiles.system_prompt()]
    assert "Competition" in board[1][1] and "Risks are many" not in board[1][1]     # the located section was read

    assert cp._locate_scope() == [MSFT]
    ask_the_service()
    assert service_requests(mock) == board
    (row,) = read.sec_reads([MSFT], cp.PROFILE_ID)
    assert row["input_kind"] == "located"
    assert cp._locate_scope() == []            # a company with a current profile pays for no heading list
    fx.run(reads.NAME, reread=True)
    assert len(mock.calls("/chat/completions")) == 2


def test_the_services_limits_and_prompts_are_the_boards():
    assert cp.FORMS_RULES_VERSION == config.FORMS_RULES_VERSION
    assert cp.MAX_BUSINESS_CHARS == config.MAX_BUSINESS_CHARS
    assert cp.MAX_FALLBACK_CHARS == engine.MAX_FALLBACK_CHARS
    assert cp.NOT_IN_DOCUMENT == engine.NOT_IN_DOCUMENT and cp.NOTE_BLOCKS == engine.NOTE_BLOCKS
    assert cp.MAX_SEGMENT_LINES == engine.MAX_SEGMENT_LINES
    assert (cp.PROFILE.system, cp.PROFILE.prompt_version) == (profiles.system_prompt(), config.PROMPT_VERSION)
    assert cp.PROFILE.max_tokens == profiles.token_budget()
    assert (cp.LOCATE.system, cp.LOCATE.prompt_version) == (locator.system_prompt(), locator.PROMPT_VERSION)


def test_the_builder_registers_the_three_questions_the_locator_first(tmp_path):
    """In a fresh interpreter: this process's registry is emptied by the fixtures and tests around it."""
    import subprocess
    import sys
    from pathlib import Path

    code = ("import revenuechaser.rcdata.build; from revenuechaser.rcdata.build.sec_reads.questions import QUESTIONS; "
            "print(','.join(QUESTIONS))")
    env = {"PATH": "", "PYTHONPATH": str(Path(cp.__file__).resolve().parents[4]), "RC_STORE_DIR": str(tmp_path / "s"),
           "RC_CACHE_DIR": str(tmp_path / "c"), "RC_EDGAR_DOCS_DIR": str(tmp_path / "e"),
           "RC_MARKET_DIR": str(tmp_path / "m")}

    def child(code: str, **more) -> str:
        out = subprocess.run([sys.executable, "-c", code], env={**env, **more}, capture_output=True, text=True,
                             cwd=str(tmp_path), timeout=120)
        assert out.returncode == 0, out.stderr
        return out.stdout.strip()

    assert child(code) == f"{cp.LOCATE_ID},{cp.PROFILE_ID},debt.note"        # #737's question runs last
    # The writer: EVREN with no call cap, or DeepSeek Flash with one, by the process's environment.
    writers = ("import revenuechaser.rcdata.build; from revenuechaser.rcdata.build.sec_reads.questions import "
               "QUESTIONS; print(';'.join(f'{q.provider},{q.writer_model},{q.max_calls}' for q in QUESTIONS.values()))")
    # All three follow the one switch: EVREN uncapped by default (avo, 19 Nov 2026 "Fundamentals icinde evren
    # deepseek olmali"), DeepSeek Flash with each question's own cap when the process names DeepSeek.
    assert child(writers) == ("evren,evren-deepseek-v4.1-flash,None;evren,evren-deepseek-v4.1-flash,None;"
                              "evren,evren-deepseek-v4.1-flash,None")
    assert (child(writers, RC_SEC_READS_PROVIDER="deepseek")
            == "deepseek,deepseek-v4-flash,150;deepseek,deepseek-v4-flash,800;deepseek,deepseek-v4-flash,200")
