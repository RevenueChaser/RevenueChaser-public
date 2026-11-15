"""#388 Grok option for the Relatedness profile writer (avo 2026-10-16: "grok kullan direk").

- ``--run --provider grok --limit N`` writes v2 profiles through SuperGrok (``core/providers/grok.py``); ``--limit``
  caps the calls (never the universe), the allowance gate stops the run cleanly, there is no off-peak gate.
- The stored row names its writer: ``relatedness_profiles.model`` is the Grok model and the cache key carries
  ``"provider": "grok"``; the LLM cache keeps the two providers apart.
- **Mixed writers (avo, 11 Nov 2026, replacing #360's one writer per board):** a Grok profile stays current for a
  DeepSeek run and the other way round; a v1 profile stays stale for both.
- Peer scores do not depend on which model wrote a profile.

Offline, temp store: the Grok HTTP client and ``deepseek.complete`` are fakes; nothing reaches xAI, DeepSeek or SEC.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from RevenueChaser.core import offpeak, rawstore, subscription_usage
from RevenueChaser.module_relatedness.tests.test_relatedness import v3_reply
from RevenueChaser.core.providers import deepseek, grok
from RevenueChaser.module_relatedness import __main__ as cli
from RevenueChaser.module_relatedness import config, engine, profiles, similarity, store
from RevenueChaser.module_relatedness.tests.test_relatedness import _prof, long_body

TICKERS = ["AAA", "BBB", "CCC"]
TOKEN = "sentinel-grok-token-388"


def _seed_filings(texts: dict[str, str]) -> None:
    rawstore.write_rows("chain_filings", [
        {"ticker": t, "cik": "", "form": "10-K", "filed": "2026-01-01", "accession": "a-" + t,
         "primary_doc": "u", "item_text": long_body(text), "quality": "ok", "fetched_at": 1.0}
        for t, text in texts.items()])


class _Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)
        self.headers: dict = {}

    def json(self):
        return self._payload


class _GrokHttp:
    """The SuperGrok endpoint: answers a profile naming the company of the prompt (or a scripted reply)."""

    def __init__(self):
        self.posts: list[dict] = []
        self.reply = None             # a fixed content string, or None for a profile per company
        self.bad: set[str] = set()    # tickers whose reply is unusable
        self.status = 200

    def post(self, url, **k):
        body = k.get("json")
        self.posts.append({"url": url, "json": body, "headers": dict(k.get("headers") or {})})
        if self.status != 200:
            return _Resp(self.status, text="model grok-x not found")
        user = body["messages"][-1]["content"]
        m = re.match(r"Company: (.+)\n", user)
        name = (m.group(1) if m else "x").lower()
        if self.reply is not None:
            content = self.reply
        elif name.split()[0].upper() in self.bad:
            content = "I cannot help with that."
        else:
            content = v3_reply([f"{name} gpu"], ["data center"])
        return _Resp(200, {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 5}})

    def close(self):
        pass


# ``core.subscription_usage.next_available`` keeps only a reset that is still ahead of ``now``, so a fixed date
# makes ``next_reset`` None once that date passes (it did, 2026-10-21). The reset is relative to this run.
RESETS_AT = (datetime.now(timezone.utc) + timedelta(days=1)).replace(second=0, microsecond=0)
RESETS_AT_TEXT = RESETS_AT.strftime("%Y-%m-%d %H:%M")


def _window(percent):
    return subscription_usage.Window(key="seven_day", percent=percent, resets_at=RESETS_AT)




@pytest.fixture
def deepseek_calls(monkeypatch):
    """The DeepSeek side (the nightly): every request it would bill, answered with a profile."""
    seen: list[str] = []

    def fake(system, user, **k):
        seen.append(user)
        return v3_reply(["deepseek gpu"], ["data center"])

    monkeypatch.setattr(deepseek, "complete", fake)
    return seen


def _ck(ticker: str) -> dict:
    v = rawstore.get("relatedness_profiles", ticker)["cache_key"]
    return v if isinstance(v, dict) else json.loads(v)


# ── the trap: staleness across providers ────────────────────────────────────









# ── the stored writer ───────────────────────────────────────────────────────



def test_a_deepseek_cache_key_is_unchanged():
    old = '{"effort":"high","input_hash":"h","model":"m","prompt_version":"v2","thinking":1,"ticker":"AAA"}'
    assert store.cache_key("m", True, "high", "v2", "aaa", "h") == old
    assert store.cache_key("m", True, "high", "v2", "aaa", "h", provider="deepseek") == old
    assert json.loads(store.cache_key("g", False, "", "v2", "aaa", "h", provider="grok"))["provider"] == "grok"


def test_the_mode_stamp_is_unchanged():
    assert store.mode_stamp() == {"model": deepseek.MODEL, "thinking": False,      # v3 sends no thinking (#400)
                                  "effort": "", "prompt_version": config.PROMPT_VERSION}


# ── the Grok run: --limit caps calls, the allowance gate, no off-peak gate ───



















# ── the CLI ─────────────────────────────────────────────────────────────────

def test_a_deepseek_run_calls_the_engine_exactly_as_before(monkeypatch, capsys):
    got = {}
    monkeypatch.setattr(cli.engine, "run", lambda **k: got.update(k) or {"n": 1, "pending": 0})
    assert cli.main(["--run", "--provider", "deepseek", "--cap", "8"]) == 0
    assert got == {"tickers": None, "limit": None, "usd_cap": 8.0}
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {"n": 1, "pending": 0,
                                                                           "next_off_peak": None}


def test_the_grok_run_passes_the_limit_as_a_call_cap(monkeypatch, capsys):
    monkeypatch.setattr(grok, "preflight", lambda now=None: None)
    got = {}
    monkeypatch.setattr(cli.engine, "run", lambda **k: got.update(k) or {"n": 1, "pending": 0, "companies": []})
    assert cli.main(["--run", "--provider", "grok", "--limit", "40"]) == 0
    assert got == {"tickers": None, "provider": "grok", "max_calls": 40}


@pytest.mark.parametrize("argv", [
    ["--run", "--provider", "grok", "--limit", "5", "--cap", "8"],  # --cap is USD, DeepSeek only
    ["--run", "--provider", "grok", "--limit", "0"],
    ["--rebuild-themes", "--provider", "grok"],                    # Grok names themes only with --name
    ["--status", "--provider", "grok"],
    ["--cutover", "--run-id", "x", "--provider", "grok"],
    ["--provider", "chatgpt", "--run"],
])
def test_bad_grok_combinations_are_refused(argv, monkeypatch):
    monkeypatch.setattr(cli.engine, "run", lambda **k: pytest.fail("must not run"))
    with pytest.raises(SystemExit) as exit_:
        cli.main(argv)
    assert exit_.value.code == 2


def test_a_grok_run_needs_no_limit(monkeypatch):
    """No call cap for Grok (avo, 2 Nov 2026, #360): ``--limit`` is optional."""
    monkeypatch.setattr(grok, "preflight", lambda now=None: None)
    got = {}
    monkeypatch.setattr(cli.engine, "run", lambda **k: got.update(k) or {"n": 1, "pending": 0, "companies": []})
    assert cli.main(["--run", "--provider", "grok"]) == 0
    assert got == {"tickers": None, "provider": "grok", "max_calls": None}






# ── theme naming with Grok (#108 S1) ────────────────────────────────────────

def test_name_themes_takes_the_grok_client(monkeypatch, capsys):
    from RevenueChaser.module_relatedness import naming
    monkeypatch.setattr(grok, "preflight", lambda now=None: None)
    calls = []
    monkeypatch.setattr(naming, "name_themes",
                        lambda run_id=None, **k: calls.append(k) or {"run_id": "r", "named": 1, "pending": 0})
    assert cli.main(["--name-themes", "--provider", "grok"]) == 0
    assert cli.main(["--name-themes"]) == 0
    assert calls[0]["complete"] is grok.complete
    assert calls[1].get("complete") in (None, deepseek.complete)






# ── scores do not depend on the writer ──────────────────────────────────────

def test_peer_scores_do_not_depend_on_which_model_wrote_a_profile(rawstore_tmp_db):
    profs = {"AAA": _prof(products=["gpu", "cpu"], end_markets=["data center"]),
             "BBB": _prof(products=["gpu"], end_markets=["data center", "gaming"]),
             "CCC": _prof(products=["bread"], end_markets=["grocery"])}

    def peers(provider, model):
        for t, p in profs.items():
            ck = store.cache_key(model, False, "", config.PROMPT_VERSION, t, "h", provider=provider)
            store.save_profile(t, "", p, ck, model)
        return similarity.peer_lists(store.load_profiles(list(profs)), config.TOP_PEERS)

    assert peers("deepseek", deepseek.MODEL) == peers("grok", grok.MODEL)


# ── result history ──────────────────────────────────────────────────────────



