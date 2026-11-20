"""#404 The LLM writers card on Settings: one row per LLM job, its provider and model as selects.

It replaces #360's two selects on the Relatedness card: the pair is a per-job setting now, so one card holds
every job's writer. A writer whose credential is absent is greyed by the variable NAME, never a value; a paid
writer is marked as paid, and no job is on one by default.

Mock approved by avo, 20 Nov 2026.
"""
from __future__ import annotations

from RevenueChaser.core import llm_jobs
from RevenueChaser.module_settings import boards, report

DS_KEY = "sentinel-deepseek-key-404"


def test_the_relatedness_card_no_longer_carries_the_writer():
    card = next(c for c in boards.BOARD_INPUTS if c["key"] == "module_relatedness")
    assert "settings" not in card                 # the pair moved to the LLM writers card


def test_the_card_has_one_row_per_llm_job(rawstore_tmp_db, monkeypatch):
    monkeypatch.setenv("LITELLM_RC_KEY", DS_KEY)
    card = boards.llm_writers_card()
    assert card["board"] == llm_jobs.BOARD
    assert [j["job"] for j in card["jobs"]] == list(llm_jobs.JOBS)
    assert card["paid"] == []                     # every job is on EVREN, which has no fee


def test_every_row_renders_both_selects_and_marks_the_fee(rawstore_tmp_db, monkeypatch):
    monkeypatch.setenv("LITELLM_RC_KEY", DS_KEY)
    html = report._llm_writers_card(boards.llm_writers_card())
    for job in llm_jobs.JOBS.values():
        assert f'data-setting="{job.writer_key}"' in html
        assert f'data-setting="{job.model_key}"' in html
        assert job.label in html and job.where in html
    assert html.count('class="llmpill free">no fee') == len(llm_jobs.JOBS)
    assert "paid · off-peak" in html              # the legend names the paid writer
    assert "Every LLM job is on EVREN" in html
    assert DS_KEY not in html


def test_a_greyed_writer_renders_disabled_and_no_value_leaks(rawstore_tmp_db, monkeypatch):
    monkeypatch.delenv("LITELLM_RC_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", DS_KEY)          # a key from before the gate: never used, never shown
    html = report._llm_writers_card(boards.llm_writers_card())
    assert '<option value="evren" selected disabled>' in html
    assert '<option value="deepseek" disabled>' in html
    assert "LITELLM_RC_KEY is not set on this box" in html
    assert 'data-kind="text"' in html
    assert DS_KEY not in html


def test_a_job_on_the_paid_writer_is_called_out_in_the_strip(rawstore_tmp_db, monkeypatch):
    monkeypatch.setenv("LITELLM_RC_KEY", DS_KEY)
    monkeypatch.setenv("RC_SEC_READS_PROVIDER", "deepseek")
    card = boards.llm_writers_card()
    assert card["paid"] == ["SEC reads · business.locate", "SEC reads · company.profile",
                            "SEC reads · debt.note"]
    html = report._llm_writers_card(card)
    assert "3 jobs on a paid writer." in html
    assert html.count('class="llmpill paid">paid · off-peak') == 4   # three rows plus the legend


def test_the_card_is_one_column_on_a_phone_and_never_scrolls_sideways():
    """Phone rule (DESIGN.md §3): the rows stack into cards; no overflow-x anywhere in the card's CSS."""
    css = report.LLM_CSS
    assert "@media (max-width:640px)" in css
    assert "#llm-writers .llmtbl{display:block" in css
    assert "overflow-x" not in css
    assert "min-height:var(--touch)" in css        # 44 px targets
