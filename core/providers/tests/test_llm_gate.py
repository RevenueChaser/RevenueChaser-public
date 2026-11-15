"""One model gate (avo, 15 Nov 2026): the Relatedness writers DeepSeek and EVREN call the LiteLLM gate on homesrv
with RevenueChaser's own virtual key, by the gate's Flash names. The board keeps its own model names, so a stored
setting and the llm_cache keys made before the gate stay valid (no profile is asked again because of the move)."""
from __future__ import annotations

import json

import pytest

from RevenueChaser.core import config, credentials
from RevenueChaser.core.providers import deepseek, evren

GATE = "http://127.0.0.1:9720/v1/chat/completions"
KEY = "sentinel-litellm-rc-key"


class _Client:
    def __init__(self):
        self.posts = []

    def post(self, url, **k):
        self.posts.append({"url": url, "json": k["json"], "headers": dict(k["headers"])})
        r = type("R", (), {})()
        r.status_code, r.headers = 200, {}
        r.json = lambda: {"choices": [{"message": {"content": "{}"}}]}
        r.text = json.dumps(r.json())
        return r

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _gate(monkeypatch, rawstore_tmp_db):
    for name in ("RC_DEEPSEEK_BASE", "RC_EVREN_BASE", "DEEPSEEK_API_KEY", "EVREN_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LITELLM_RC_KEY", KEY)
    monkeypatch.setenv("RC_DEEPSEEK_OFF_PEAK_ONLY", "0")


def test_both_writers_share_rc_s_gate_key_which_never_comes_from_dotenv():
    assert credentials.get("deepseek").env_var == credentials.get("evren").env_var == "LITELLM_RC_KEY"
    assert "LITELLM_RC_KEY" in config.ENV_ONLY_KEYS


@pytest.mark.parametrize("thinking, wire", [(False, "deepseek-v4-flash-nothink"), (True, "deepseek-v4-flash-think")])
def test_deepseek_goes_to_the_gate_by_its_flash_name(thinking, wire):
    c = _Client()
    deepseek.complete("s", "u", thinking=thinking, client=c, use_cache=False, model="deepseek-flash")
    (post,) = c.posts
    assert post["url"] == GATE and post["headers"]["Authorization"] == f"Bearer {KEY}"
    assert post["json"]["model"] == wire and "pro" not in wire


@pytest.mark.parametrize("model", ["deepseek-v4.1-flash", "glm-5.3", "qwen3.8-flash-next"])
def test_evren_goes_to_the_gate_by_its_evren_name(model):
    c = _Client()
    evren.complete("s", "u", client=c, use_cache=False, model=model)
    (post,) = c.posts
    assert post["url"] == GATE and post["headers"] == {"Authorization": f"Bearer {KEY}",
                                                        "Content-Type": "application/json"}
    assert post["json"]["model"] == f"evren-{model}"


def test_the_cache_key_keeps_the_board_s_model_name(monkeypatch):
    seen = []
    monkeypatch.setattr(deepseek, "_cache_get", lambda key: seen.append(key) or "{}")
    deepseek.complete("s", "u", thinking=False, client=_Client(), model="deepseek-flash")
    assert seen == [deepseek._cache_key("s", "u", False, "deepseek-flash", None)]
