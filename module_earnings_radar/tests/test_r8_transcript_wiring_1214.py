"""R8 scores the stored earnings call, so it can vote negative (#1214, review finding G2)."""
from __future__ import annotations

from RevenueChaser.module_earnings_radar import pipeline, store_reads


def turn(seq, title, content, ticker="MSFT", quarter="2025Q1"):
    return {"ticker": ticker, "quarter": quarter, "seq": seq, "speaker": "Someone", "title": title,
            "content": content, "provider_sentiment": 0.0}


CALL = [turn(0, "Vice President of Investor Relations", "Welcome to the call."),
        turn(1, "CEO", "We delivered a strong quarter and we are confident."),
        turn(2, "Operator", "We will now open the line for questions."),
        turn(3, "Analyst", "How uncertain is the guidance?"),
        turn(4, "CFO", "It is uncertain, it may vary, it could depend on several unpredictable factors, and the "
                       "risk may possibly change; we are uncertain about the approximate exposure.")]

FLOW = {"retail_call": 10_000.0, "inst_call": 90_000.0}          # a share well under the fade threshold


def test_the_halves_come_out_of_the_store_split_at_the_first_analyst(monkeypatch):
    from RevenueChaser.rcdata import read

    monkeypatch.setattr(read, "earnings_transcript", lambda names, **kw: list(CALL))
    rows, note = store_reads.transcript_halves(["MSFT"])
    assert "We delivered a strong quarter" in rows["MSFT"]["prepared"]
    assert "open the line for questions" in rows["MSFT"]["prepared"]
    assert "How uncertain is the guidance?" in rows["MSFT"]["qa"]
    assert rows["MSFT"]["quarter"] == "2025Q1" and rows["MSFT"]["turns"] == 5
    assert note["stored"] is True and "1 of 1 names" in note["label"]


def test_a_call_with_no_analyst_turn_has_no_qa_half_and_says_so(monkeypatch):
    from RevenueChaser.rcdata import read

    monkeypatch.setattr(read, "earnings_transcript", lambda names, **kw: [t for t in CALL
                                                                         if t["title"] != "Analyst"])
    rows, note = store_reads.transcript_halves(["MSFT"])
    assert rows["MSFT"]["qa"] is None
    assert "no Q&A half" in note["label"]


def test_a_store_error_is_not_stored_rather_than_an_exception(monkeypatch):
    from RevenueChaser.rcdata import read

    def boom(names, **kw):
        raise RuntimeError("no file")

    monkeypatch.setattr(read, "earnings_transcript", boom)
    rows, note = store_reads.transcript_halves(["MSFT"])
    assert rows == {} and note["stored"] is False
    assert "read failed" in note["label"]


def test_r8_can_vote_negative_once_it_has_both_halves():
    """The whole point of #1214: with retail share alone R8 scores +20 or 0 and can never be bearish. Uncertainty
    rising in the Q&A is what makes the score negative."""
    prepared, qa = store_reads.transcript_split.split_at_first_analyst(CALL)
    without = pipeline._score_sentiment(FLOW)
    with_text = pipeline._score_sentiment(FLOW, {"prepared": prepared, "qa": qa})
    assert without.score == 0.0
    assert with_text.score is not None and with_text.score < 0, with_text.reasons
    assert with_text.raw_metrics["tone_delta"] > 0                # the Q&A is the more uncertain half


def test_a_name_with_no_stored_call_scores_exactly_as_before():
    """Coverage climbs ~22 names a day, so most names have no call for a while: their cards must not move."""
    assert pipeline._score_sentiment(FLOW, None).score == pipeline._score_sentiment(FLOW).score
    assert pipeline._score_sentiment(FLOW, {}).score == pipeline._score_sentiment(FLOW).score
    hot = {"retail_call": 90_000.0, "inst_call": 10_000.0}        # share over the fade threshold
    assert pipeline._score_sentiment(hot, None).score == 20.0
