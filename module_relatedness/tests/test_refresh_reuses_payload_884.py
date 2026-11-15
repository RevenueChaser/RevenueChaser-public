"""#884 A: a Refresh of the whole board renders the saved payload when no profile is newer than it."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_relatedness import engine

NOW = datetime(2026, 11, 15, 15, 5, 1, tzinfo=timezone.utc)


def _saved(tmp_path, monkeypatch, writer=("deepseek", "deepseek-flash")):
    payload = {"as_of": NOW.isoformat(), "writer": {"provider": writer[0], "model": writer[1]}, "n": 1,
               "companies": [{"ticker": "AAPL"}], "peers": {"AAPL": []}}
    path = tmp_path / "relatedness_latest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(engine.config, "RELATEDNESS_JSON", path)
    return payload


def _profiles(monkeypatch, fetched_at):
    monkeypatch.setattr(rawstore, "get_all", lambda table: [{"ticker": "AAPL", "fetched_at": fetched_at}])


def _run_must_not_happen(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the pairs were rescored")
    monkeypatch.setattr(engine, "_run", boom)


def test_a_whole_board_refresh_renders_the_saved_payload_when_no_profile_is_newer(tmp_path, monkeypatch):
    saved = _saved(tmp_path, monkeypatch)
    _profiles(monkeypatch, (NOW - timedelta(seconds=13)).timestamp())
    _run_must_not_happen(monkeypatch)
    assert engine.run(no_fetch=True, provider="deepseek", model="deepseek-flash") == saved


def test_a_newer_profile_rescored(tmp_path, monkeypatch):
    _saved(tmp_path, monkeypatch)
    _profiles(monkeypatch, (NOW + timedelta(seconds=1)).timestamp())
    monkeypatch.setattr(engine, "_run", lambda *a, **k: {"n": 0, "rescored": True})
    assert engine.run(no_fetch=True, provider="deepseek", model="deepseek-flash")["rescored"]


@pytest.mark.parametrize("kw", [{"tickers": ["AAPL"]}, {"limit": 5}, {"provider": "evren"}])
def test_a_partial_refresh_or_another_writer_rescored(tmp_path, monkeypatch, kw):
    _saved(tmp_path, monkeypatch)
    _profiles(monkeypatch, (NOW - timedelta(seconds=13)).timestamp())
    monkeypatch.setattr(engine, "_run", lambda *a, **k: {"n": 0, "rescored": True})
    args = {"no_fetch": True, "provider": "deepseek", "model": "deepseek-flash"}
    args.update(kw)
    if kw.get("provider") == "evren":
        args["model"] = None
    assert engine.run(**args)["rescored"]


def test_no_saved_payload_rescored(tmp_path, monkeypatch):
    monkeypatch.setattr(engine.config, "RELATEDNESS_JSON", tmp_path / "missing.json")
    _profiles(monkeypatch, NOW.timestamp())
    monkeypatch.setattr(engine, "_run", lambda *a, **k: {"n": 0, "rescored": True})
    assert engine.run(no_fetch=True)["rescored"]
