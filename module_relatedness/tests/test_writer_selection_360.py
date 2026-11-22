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

from revenuechaser.core import board_settings, rawstore
from revenuechaser.module_relatedness.tests.test_relatedness import v3_reply
from revenuechaser.core.providers import deepseek, evren
from revenuechaser.module_relatedness import __main__ as cli
from revenuechaser.core import llm_writers as writers
from revenuechaser.module_relatedness import engine, settings, store
from revenuechaser.module_relatedness.tests.test_relatedness import long_body

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


# avo, 20 Nov 2026: "Fetch ve build sirasinda deepseek api kullanilan islem kalmasin hepsi evren deepseek olmali".
# Every one of these defaulted to the paid writer, so a caller that forgot the argument spent money. The scheduled
# Fetch always passed the board's writer, so nothing scheduled changes; the hazard was the omitted argument.

# This folder's ``_deepseek_default`` fixture pins the writer to DeepSeek, because its tests drive that writer;
# these two are about the default itself, so they put the registry's own back.

def test_a_module_call_without_a_writer_runs_on_the_free_one(monkeypatch):
    from revenuechaser.module_relatedness import config as rel_config
    from revenuechaser.module_relatedness import profiles as profiles_mod
    assert writers.DEFAULT == "evren" and not writers.get(writers.DEFAULT).paid
    monkeypatch.setattr(rel_config, "default_writer", lambda: writers.DEFAULT)
    assert profiles_mod.llm() is profiles_mod._writers().client("evren")
    assert profiles_mod.llm() is not deepseek


def test_a_profile_saved_without_a_writer_names_the_free_one(rawstore_tmp_db, monkeypatch):
    from revenuechaser.module_relatedness import config as rel_config
    monkeypatch.setattr(rel_config, "default_writer", lambda: writers.DEFAULT)
    store.save_profile("ZZZ", "1", {}, "{}", "a-model")
    rows = [r for r in rawstore.get_all("relatedness_profiles") if r["ticker"] == "ZZZ"]
    assert [r.get("provider") for r in rows] == ["evren"]


def test_the_naming_cli_banner_names_the_free_writer(rawstore_tmp_db, monkeypatch, capsys):
    """``--name-themes`` printed DeepSeek's off-peak gate although naming calls its own pair (#404, EVREN)."""
    monkeypatch.setenv("LITELLM_RC_KEY", EVREN_KEY)
    monkeypatch.setattr("revenuechaser.module_relatedness.naming.name_themes",
                        lambda run_id=None: {"named": 0, "pending": 0})
    assert cli.main(["--name-themes"]) == 0
    out = capsys.readouterr().out
    assert "EVREN" in out and "no fee, no off-peak gate" in out        # not ``offpeak.describe()``
    assert "DeepSeek" not in out and "Peak override" not in out






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
    """Since #1255 the run happens in the dashboard, so the cap travels in the request, not on a command line."""
    from revenuechaser.core import automations
    from revenuechaser.scripts import board_fetch
    e = automations.entry("RC-Relatedness-OffPeak")
    assert e.args == ("-m", "revenuechaser.scripts.board_fetch", "relatedness")
    assert board_fetch.FORM["relatedness"] == {"usd_cap": "10"}
    assert e.time == "22:15" and e.days == ("Sunday",)          # weekly Sunday (avo 20 Nov 2026: "Tamam haftalik")




# ── review S1 (PR 362): the board's model is a parameter, never a module-level swap ─────────────────









def test_the_writer_modules_take_the_model_per_call(rawstore_tmp_db, monkeypatch):
    from revenuechaser.core.providers import evren as ev
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


def test_an_evren_call_waits_longer_than_two_minutes_and_the_wait_is_a_process_setting(monkeypatch):
    """A profile over a whole document took longer than the old 120 s and the read timeout killed the night's SEC
    read (20 Nov 2026, 01:10); a cold full-size call was then measured at 235 s. The wait is twice that over, and
    ``RC_EVREN_TIMEOUT_S`` sets it."""
    from revenuechaser.core.providers import evren as ev
    monkeypatch.delenv("RC_EVREN_TIMEOUT_S", raising=False)
    assert ev.DEFAULT_TIMEOUT_S == 600.0 and ev.timeout_s() == ev.DEFAULT_TIMEOUT_S
    client = ev._new_client()
    try:
        assert client.timeout.read == ev.DEFAULT_TIMEOUT_S
    finally:
        client.close()
    monkeypatch.setenv("RC_EVREN_TIMEOUT_S", "45")
    assert ev.timeout_s() == 45.0
    for bad in ("", "soon", "0", "-1"):                     # unreadable or useless: the default stands
        monkeypatch.setenv("RC_EVREN_TIMEOUT_S", bad)
        assert ev.timeout_s() == ev.DEFAULT_TIMEOUT_S


# ── review S2 + nit4 (PR 362): a partial reset and a shared model name never leave an invalid pair ──────────





