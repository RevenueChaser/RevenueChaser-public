"""#360 The Relatedness card on Settings: the writer and its model as selects, a missing key greyed by name."""
from __future__ import annotations

from RevenueChaser.module_settings import boards, report

DS_KEY = "sentinel-deepseek-key-360"


def _card():
    return next(c for c in boards.BOARD_INPUTS if c["key"] == "module_relatedness")


def test_the_card_offers_the_writer_and_its_model(rawstore_tmp_db, monkeypatch):
    monkeypatch.delenv("LITELLM_RC_KEY", raising=False)
    s = _card()["settings"]()
    assert s["board"] == "module_relatedness"
    rows = {f["key"]: f for f in s["inputs"]}
    assert set(rows) == {"WRITER", "WRITER_MODEL"}
    writer = {c[0]: c for c in rows["WRITER"]["choices"]}
    assert writer["evren"][2] == "LITELLM_RC_KEY is not set on this box"
    assert writer["deepseek"][2] == "LITELLM_RC_KEY is not set on this box"  # one gate key for both
    assert set(writer) == {"evren", "deepseek"}


def test_a_greyed_option_renders_disabled_and_no_value_leaks(rawstore_tmp_db, monkeypatch):
    monkeypatch.delenv("LITELLM_RC_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", DS_KEY)          # a key from before the gate: never used, never shown
    s = _card()["settings"]()
    html = "".join(report._setting_field(f) for f in s["inputs"])
    assert '<option value="evren" selected disabled>' in html
    assert "LITELLM_RC_KEY is not set on this box" in html
    assert 'data-kind="text"' in html
    assert DS_KEY not in html
