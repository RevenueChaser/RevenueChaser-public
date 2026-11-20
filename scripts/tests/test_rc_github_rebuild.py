"""``scripts/rc_github_rebuild.py``: the runner's own entry point (#1125).

The build itself is ``base.build_kind_many``, tested where it lives. What is this script's own is the one decision
it makes: whether the swap's shrink guard is relaxed for the kind it builds. Those are the rules here, with
``build_kind_many`` replaced by a stub, because a real build needs a Parquet tree.
"""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "rc_github_rebuild.py"


def _load():
    spec = importlib.util.spec_from_file_location("rc_github_rebuild_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod(monkeypatch, tmp_path):
    m = _load()
    seen = {}

    def build_kind_many(kind, members, lead=None):
        seen["kind"] = kind
        seen["allow_shrink"] = [c.allow_shrink for _ds, c in members]
        return {"stub": {"ok": True}}

    monkeypatch.setattr(m.base, "build_kind_many", build_kind_many)
    monkeypatch.setattr(m.backup, "_table_fingerprints", lambda path: {"t": (1, "abc")})
    monkeypatch.setattr(m.serving, "live_path", lambda kind: tmp_path / f"{kind}.duckdb")
    monkeypatch.chdir(tmp_path)
    m.seen = seen
    return m


def _result(tmp_path):
    return json.loads((tmp_path / "result.json").read_text())


def test_without_the_flag_the_guard_is_not_relaxed(mod, tmp_path):
    assert mod.main("ownership") == 0
    assert mod.seen["allow_shrink"] == [False]
    assert _result(tmp_path)["allow_shrink"] is False


def test_the_flag_relaxes_the_guard_for_ownership(mod, tmp_path):
    """#935 drops the partial first 13F quarter, so sec13f_periods loses over 1 % of its rows."""
    assert mod.main("ownership", allow_shrink=True) == 0
    assert mod.seen["allow_shrink"] == [True]
    assert _result(tmp_path)["allow_shrink"] is True


def test_prices_never_takes_the_flag(mod):
    """avo's standing rule: prices are never narrowed."""
    with pytest.raises(SystemExit) as e:
        mod.main("prices", allow_shrink=True)
    assert "prices" in str(e.value)
    assert "kind" not in mod.seen, "the build must not start"


def test_prices_still_builds_without_the_flag(mod, tmp_path):
    """The refusal is of the flag, not of the kind: prices builds as before, and says it was not relaxed."""
    assert mod.main("prices") == 0
    assert mod.seen["allow_shrink"] == [False]
    assert _result(tmp_path)["allow_shrink"] is False


def test_the_cli_reads_the_flag(mod):
    assert mod.parse_argv(["ownership"]) == ("ownership", False)
    assert mod.parse_argv(["ownership", "--allow-shrink"]) == ("ownership", True)
    with pytest.raises(SystemExit):
        mod.parse_argv(["ownership", "--whatever"])
    with pytest.raises(SystemExit):
        mod.parse_argv([])
