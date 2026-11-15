"""#360 The profile writer is chosen on the board (framework D9, avo 1-2 Nov 2026): EVREN by default.

- ``WRITER`` / ``WRITER_MODEL`` are board settings (``value_text``); a model outside its provider's list is refused.
- An option whose key or login is absent is greyed with the variable NAME, never a value.
- The CLI and the dashboard run the board's writer when no ``--provider`` is given; the off-peak gate and the USD cap
  are DeepSeek's only; EVREN and Grok have no call cap (avo, 2 Nov).
- One writer per board: a profile of another writer is stale and stays out of the peer matrix.
- Every profile and every run names its provider and model.

Offline, temp store: the EVREN HTTP client and ``deepseek.complete`` are fakes.
"""
from __future__ import annotations

import json
import re

import pytest

from RevenueChaser.core import board_settings, rawstore
from RevenueChaser.module_relatedness.tests.test_relatedness import v3_reply
from RevenueChaser.core.providers import deepseek, evren
from RevenueChaser.module_relatedness import __main__ as cli
from RevenueChaser.module_relatedness import engine, settings, store, writers
from RevenueChaser.module_relatedness.tests.test_relatedness import long_body

TICKERS = ["AAA", "BBB", "CCC"]
EVREN_KEY = "sentinel-evren-key-360"
DS_KEY = "sentinel-deepseek-key-360"


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = json.dumps(self._payload)
        self.headers: dict = {}

    def json(self):
        return self._payload


class _EvrenHttp:
    def __init__(self):
        self.posts: list[dict] = []

    def post(self, url, **k):
        body = k.get("json")
        self.posts.append({"url": url, "json": body})
        name = re.match(r"Company: (.+)\n", body["messages"][-1]["content"]).group(1).lower()
        content = v3_reply([f"{name} gpu"], ["data center"])
        return _Resp(200, {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 5}})

    def close(self):
        pass


def _seed_filings(texts: dict[str, str]) -> None:
    rawstore.write_rows("chain_filings", [
        {"ticker": t, "cik": "", "form": "10-K", "filed": "2026-01-01", "accession": "a-" + t,
         "primary_doc": "u", "item_text": long_body(text), "quality": "ok", "fetched_at": 1.0}
        for t, text in texts.items()])




@pytest.fixture
def deepseek_calls(monkeypatch):
    seen: list[str] = []

    def fake(system, user, **k):
        seen.append(user)
        return v3_reply(["deepseek gpu"], ["data center"])

    monkeypatch.setattr(deepseek, "complete", fake)
    return seen


# ── the setting ─────────────────────────────────────────────────────────────

def test_the_default_writer_is_evren(rawstore_tmp_db):
    assert settings.writer() == ("evren", "evren-deepseek-v4.1-flash")
    assert writers.DEFAULT == "evren" and set(writers.WRITERS) == {"evren", "deepseek"}








def test_options_grey_a_missing_key_by_name_and_never_show_a_value(rawstore_tmp_db, monkeypatch):
    # EVREN and DeepSeek both go through the LiteLLM gate with RevenueChaser's one key (one model gate, 15 Nov 2026).
    monkeypatch.delenv("LITELLM_RC_KEY", raising=False)
    opts = {o["provider"]: o for o in writers.options()}
    assert opts["evren"]["available"] is False and opts["evren"]["missing"] == "LITELLM_RC_KEY"
    assert opts["deepseek"]["available"] is False and opts["deepseek"]["missing"] == "LITELLM_RC_KEY"
    monkeypatch.setenv("LITELLM_RC_KEY", DS_KEY)
    opts = {o["provider"]: o for o in writers.options()}
    assert opts["evren"]["available"] is True and opts["deepseek"]["available"] is True
    assert DS_KEY not in json.dumps(opts)


# ── the run ─────────────────────────────────────────────────────────────────

def test_the_cli_runs_the_boards_writer_without_a_call_cap(rawstore_tmp_db, monkeypatch, capsys):
    monkeypatch.setenv("LITELLM_RC_KEY", EVREN_KEY)
    got = {}
    monkeypatch.setattr(cli.engine, "run", lambda **k: got.update(k) or {"n": 1, "pending": 0, "companies": []})
    assert cli.main(["--run", "--cap", "10"]) == 0          # what RC-Relatedness-OffPeak runs
    assert got == {"tickers": None, "provider": "evren", "max_calls": None}




def test_a_writer_without_its_key_stops_before_any_call(rawstore_tmp_db, monkeypatch, capsys):
    monkeypatch.delenv("LITELLM_RC_KEY", raising=False)
    monkeypatch.setattr(cli.engine, "run", lambda **k: pytest.fail("must not run"))
    assert cli.main(["--run", "--cap", "10"]) == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["provider"] == "evren" and out["calls"] == 0 and out["stopped_reason"] == "missing"
    assert "LITELLM_RC_KEY" in out["error"]












def test_the_scheduled_job_carries_the_10_usd_deepseek_cap():
    from RevenueChaser.core import automations
    e = automations.entry("RC-Relatedness-OffPeak")
    assert e.args == ("-m", "RevenueChaser.module_relatedness", "--run", "--cap", "10")
    assert e.time == "07:30" and e.days == ("Sunday",)          # every other Sunday (avo 15 Nov 2026); the timer carries the fortnight




# ── review S1 (PR 362): the board's model is a parameter, never a module-level swap ─────────────────









def test_the_writer_modules_take_the_model_per_call(rawstore_tmp_db, monkeypatch):
    from RevenueChaser.core.providers import evren as ev
    posts = []

    class _C:
        def post(self, url, **k):
            posts.append(k["json"]["model"])
            return _Resp(200, {"choices": [{"message": {"content": "{}"}}]})

        def close(self):
            pass

    monkeypatch.setenv("LITELLM_RC_KEY", EVREN_KEY)
    ev.complete("s", "u", client=_C(), use_cache=False, model="evren-glm-5.3")
    assert posts == ["evren-glm-5.3"] and ev.MODEL != "evren-glm-5.3"
    assert not hasattr(writers, "use")                      # no module-level swap left


# ── review S2 + nit4 (PR 362): a partial reset and a shared model name never leave an invalid pair ──────────





