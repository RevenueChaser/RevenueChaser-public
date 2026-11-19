"""#1123: one EDGAR document the archive fails on is deferred, not fatal.

Measured in RC-Build.log on homesrv, 19 Nov 2026: every builder pass that exited 1 failed in ``sec/13dg`` on one
document of cik 102909 -- HTTP 504 at 17:06 and 20:08, 502 at 19:07 -- while the 18:05 pass fetched the same
document and added 1,009 rows. The fetch had no shape for "ask again later": a status that is not
``base.is_missing`` raised, the dataset failed, the pass exited 1, and the next pass sorted the same accession
first and failed on it again, so the day never reached ``.done``.

What is asserted here: the day's other filings are served, the failing one is recorded in a ``.defer`` note and
asked again on the next pass, the day keeps no ``.done`` and the dataset stays due, nothing is ever written off or
dropped, and a run of failures -- the path, not a document -- still stops the run.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from RevenueChaser.core.providers import sec_edgar
from RevenueChaser.rcdata import serving
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.ownership import edgar, sched13dg, sec

from . import ownership_fixture as ox

DAY = "2026-10-27"
AS_OF = "2026-10-28"
VANGUARD = "0000102909-26-000001"          # the filer the live failures were all under
ACTIVIST = "0001111111-26-000002"


@pytest.fixture
def feed(monkeypatch, http_mock):
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec, "_shared_pace", lambda: True)
    e = ox.Edgar()
    g = ox.sched_filing(VANGUARD, "SCHEDULE 13G", DAY, (14693, "BROWN FORMAN CORP"), (102909, "VANGUARD GROUP INC"),
                        ox.sched_xml("13G", 14693, "BROWN FORMAN CORP", "115637209",
                                     [("VANGUARD GROUP INC", 25_000_000, 8.4, 0)]))
    d = ox.sched_filing(ACTIVIST, "SCHEDULE 13D/A", DAY, (1326380, "GAMESTOP CORP"), (1111111, "ACTIVIST LP"),
                        ox.sched_xml("13D", 1326380, "GAMESTOP CORP", "36467W109",
                                     [("ACTIVIST LP", 30_000_000, 6.7, 30_000_000)]))
    e.add_day(DAY, [
        (ox.idx_row(14693, "BROWN FORMAN CORP", "SCHEDULE 13G", DAY, VANGUARD), g),
        (ox.idx_row(1326380, "GAMESTOP CORP", "SCHEDULE 13D/A", DAY, ACTIVIST), d),
    ])
    e.install(http_mock)
    ox.make_spine()
    return e


def _run(day: str = AS_OF) -> dict:
    return base.run_request({"dataset": sched13dg.NAME, "params": {"as_of": day}}, sleep=lambda s: None)


def _backfill(first: str, last: str) -> dict:
    return base.run_request({"dataset": sched13dg.NAME, "params": {"mode": "backfill", "from": first, "to": last}},
                            sleep=lambda s: None)


def _served(sql: str) -> list[tuple]:
    with serving.open_read("ownership") as con:
        return con.execute(sql).fetchall()


def _accessions() -> list[str]:
    return [r[0] for r in _served("SELECT DISTINCT accession FROM beneficial_ownership ORDER BY accession")]


def _defer(acc: str, day: str = DAY) -> dict | None:
    path = sched13dg.DATASET.filing_defer(date.fromisoformat(day), acc)
    return json.loads(path.read_text()) if path.exists() else None


# ── One document the archive fails on ──────────────────────────────────────────────────────────────────────────

def test_a_gateway_failure_on_one_filing_neither_fails_the_dataset_nor_drops_the_day(feed):
    """The incident itself. The 13D/A answers 504 for ever; the 13G of the same day is still served, the dataset
    does not fail, and the day is not written off: no ``.none`` for the filing, no ``.done`` for the day."""
    feed.failing[ACTIVIST] = 504
    row = _run()
    assert row["result"] != "failed", row["note"]
    assert _accessions() == [VANGUARD]                            # what was fetched is served, nothing less
    assert not sched13dg.DATASET.filing_none(date.fromisoformat(DAY), ACTIVIST).exists()
    assert not sched13dg.DATASET.is_done(date.fromisoformat(DAY))


def test_the_deferred_filing_is_recorded_and_the_dataset_stays_due(feed):
    """It is recorded, not dropped: a ``.defer`` note with the status, and a run note that names it. The dataset
    asks to be due again the same day (``more_left``), so the next pass picks the filing up."""
    feed.failing[ACTIVIST] = 502
    row = _run()
    note = _defer(ACTIVIST)
    assert note and note["status"] == 502 and note["passes"] == 1, note
    assert note["form"] == "SCHEDULE 13D/A" and "/Archives/" in note["url"]
    assert "deferred" in row["note"] and ACTIVIST in row["note"], row["note"]
    assert row["next_check_due"] == AS_OF, row["next_check_due"]


def test_the_next_pass_asks_only_the_deferred_filing_and_the_day_then_finishes(feed, http_mock):
    """What the live builder could not do: come back for the one document. The filings already in are not asked
    again, the deferred one is, and once it answers the day is complete and its note is gone."""
    feed.failing[ACTIVIST] = 504
    _run()
    http_mock.requests.clear()
    del feed.failing[ACTIVIST]
    row = _run()
    asked = sorted(str(c.url).rsplit("/", 1)[1] for c in http_mock.calls("/Archives/edgar/data/"))
    assert asked == [f"{ACTIVIST}.txt"], asked
    assert row["result"] == "changed", row["note"]
    assert _accessions() == sorted([VANGUARD, ACTIVIST])
    assert _defer(ACTIVIST) is None
    assert sched13dg.DATASET.is_done(date.fromisoformat(DAY))


def test_the_note_counts_the_passes_so_a_document_failing_for_ever_shows_its_age(feed):
    """A document that fails every pass must not look new each time, or nobody can tell it from a fresh blip."""
    feed.failing[ACTIVIST] = 504
    _run()
    row = _run()
    assert _defer(ACTIVIST)["passes"] == 2
    assert "2 passes" in row["note"], row["note"]


def test_a_filing_the_edge_clears_after_four_tries_is_fetched_and_not_deferred(feed, http_mock):
    """Why the filing fetch has a ladder of its own: the shared one is three attempts over about six seconds, and
    an EDGAR edge 504 clears in seconds. Four failures then an answer is fetched; nothing is deferred."""
    feed.failing[ACTIVIST], feed.clears_after[ACTIVIST] = 504, edgar.FILING_ATTEMPTS - 1
    row = _run()
    assert len(http_mock.calls(ACTIVIST)) == edgar.FILING_ATTEMPTS
    assert edgar.FILING_ATTEMPTS > base.HTTP_ATTEMPTS
    assert row["result"] == "changed", row["note"]
    assert _defer(ACTIVIST) is None and sched13dg.DATASET.is_done(date.fromisoformat(DAY))


def test_a_404_is_still_written_off_and_not_deferred(feed):
    """A deferral is for a failure, never for an answer: a filing the archive holds no object for is marked
    ``.none`` as before (#505), so the walk does not ask it for ever."""
    feed.not_found.add(ACTIVIST)
    row = _run()
    assert row["result"] == "changed", row["note"]
    assert sched13dg.DATASET.filing_none(date.fromisoformat(DAY), ACTIVIST).exists()
    assert _defer(ACTIVIST) is None


# ── The path failing, not a document ───────────────────────────────────────────────────────────────────────────

def test_more_than_the_ceiling_of_deferrals_on_one_day_stops_the_run(feed):
    """A day of failures is the data path and not an agent's documents, so the run stops and says so rather than
    deferring hundreds of filings and churning through them every hour."""
    day = "2026-10-26"
    accs = [f"0001000060-26-{i:06d}" for i in range(edgar.DEFER_MAX + 2)]
    feed.add_day(day, [(ox.idx_row(1000060, "XI FUND", "SCHEDULE 13G", day, a), None) for a in accs])
    for a in accs:
        feed.failing[a] = 502
    row = _run()
    assert row["result"] == "failed", row["note"]
    assert f"more than {edgar.DEFER_MAX} on one day is the path" in row["note"], row["note"]
    assert not sched13dg.DATASET.is_done(date.fromisoformat(day))


def test_a_days_index_failing_leaves_the_day_open_instead_of_failing_the_run(feed, http_mock):
    """The same shape one level up: a 5xx on the daily index says nothing about the day, so the day is left
    unmarked and unwalked and the next pass asks for it again. A missing index (403 with no object) is a different
    answer and still marks the day absent. The day before answers, so the walk itself goes on."""
    earlier = "0000315066-26-000003"
    feed.add_day("2026-10-26", [
        (ox.idx_row(320193, "APPLE INC", "SCHEDULE 13G", "2026-10-26", earlier),
         ox.sched_filing(earlier, "SCHEDULE 13G", "2026-10-26", (320193, "APPLE INC"), (315066, "FMR LLC"),
                         ox.sched_xml("13G", 320193, "APPLE INC", "037833100",
                                      [("FMR LLC", 12_000_000, 5.1, 0)])))])
    feed.index_failing[DAY.replace("-", "")] = 504
    row = _run()
    assert row["result"] != "failed", row["note"]
    assert "the daily index failed" in row["note"], row["note"]
    assert not edgar.index_none(date.fromisoformat(DAY)).exists()
    assert _accessions() == [earlier]                  # 26 October is in; 27 October is not written off
    assert row["next_check_due"] == AS_OF
    del feed.index_failing[DAY.replace("-", "")]
    assert _run()["result"] == "changed"
    assert _accessions() == sorted([VANGUARD, ACTIVIST, earlier])


def test_more_than_the_ceiling_of_failing_index_days_stops_the_run(feed):
    """A stretch of them is the path, and a backfill must not walk a month of days it knows nothing about."""
    feed.index_failing |= {f"202609{d:02d}": 503 for d in range(1, 31)}
    row = _backfill("2026-09-01", "2026-09-30")
    assert row["result"] == "failed", row["note"]
    assert f"more than {edgar.DEFER_MAX} is the path and not one day" in row["note"], row["note"]
    for d in (date(2026, 9, 30), date(2026, 9, 29)):
        assert not edgar.index_none(d).exists(), d


# ── What a caller asks to tell the two apart ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kwargs, transient", [
    ({"status": 502}, True), ({"status": 504}, True), ({"status": 500}, True), ({"status": 429}, True),
    ({"transport": True}, True), ({"status": 403}, False), ({"status": 404}, False), ({}, False)])
def test_a_source_error_says_whether_it_is_worth_asking_again(kwargs, transient):
    assert base.SourceError("x", **kwargs).transient is transient


def test_http_get_tags_the_status_it_gave_up_on(http_mock):
    http_mock.add("flaky.test", b"gateway", status=504)
    ctx = base.RunContext(run_id="r", dataset="d", sleep=lambda s: None)
    with pytest.raises(base.SourceError) as e:
        base.http_get(ctx, "sec", "https://flaky.test/x.txt")
    assert e.value.status == 504 and e.value.transient and not e.value.transport


def test_http_get_takes_a_longer_ladder_for_one_call(http_mock):
    """``attempts`` buys patience for one request and is paid in counted requests, nothing else."""
    http_mock.add("flaky.test", b"gateway", status=502)
    ctx = base.RunContext(run_id="r", dataset="d", sleep=lambda s: None)
    with pytest.raises(base.SourceError):
        base.http_get(ctx, "sec", "https://flaky.test/x.txt", attempts=5)
    assert len(http_mock.calls("flaky.test")) == 5
    assert ctx.calls["sec"] == [5, 1, 0]
