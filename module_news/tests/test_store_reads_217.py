"""#217 (F12): every read of ``boards/news.duckdb`` goes through ``module_news/store_reads.py``.

Two halves. The first is the invariant the strangler step buys: no file outside the reader queries the News store,
no module of the board carries a news table name of its own, and every table the schema files under ``db="news"``
has a reader here — so the SQL cannot creep back, and a new table cannot be added without a seam. The second is
the behaviour of each reader, against a real temp store (``rawstore_tmp_db``), because a refactor that moves SQL
is only safe if the SQL's answers are pinned.

No network and no real store: ``conftest.py`` redirects the roots and the autouse fixture gives each test its own
file.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from RevenueChaser.core import provenance, rawstore
from RevenueChaser.module_news import store_reads as sr

REPO = Path(__file__).resolve().parents[2]
#: The six tables of the board's file, as the names a stray ``SELECT`` would spell.
TABLE_NAMES = (sr.EVENTS, sr.EARNINGS, sr.HIGHLIGHT, sr.HEADLINES, sr.META, sr.READING)
NOW = 1_763_000_000.0


# ── the invariant ─────────────────────────────────────────────────────────────────────────────────────────────────
def _sources() -> list[Path]:
    """Every non-test Python file of the repository."""
    return [p for p in REPO.rglob("*.py")
            if "tests" not in p.parts and not p.name.startswith("test_") and ".git" not in p.parts]


def test_only_the_reader_queries_the_news_store():
    """A ``rawstore.query(..., db="news")`` anywhere else is embedded board SQL, which is what #217 is about.

    ``core/datasets.py`` names ``db="news"`` too, but as the dataset's declaration, not a query — the check looks
    for the two together in one call, so a declaration does not match.
    """
    call = re.compile(r"\.query\((?:[^()]|\([^()]*\))*db\s*=\s*[\"']news[\"']", re.S)
    offenders = [str(p.relative_to(REPO)) for p in _sources()
                 if p != Path(sr.__file__) and call.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"these files still query the News store directly: {offenders}"


def test_no_module_of_the_board_spells_a_news_table_name_itself():
    """The board's modules take the names from the reader, so a rename is a change to one file."""
    offenders = {}
    for p in sorted((REPO / "module_news").glob("*.py")):
        if p == Path(sr.__file__):
            continue
        text = p.read_text(encoding="utf-8")
        # Only a string literal counts: the docstrings name the tables in prose on purpose.
        named = [t for t in TABLE_NAMES if f'"{t}"' in text or f"'{t}'" in text]
        if named:
            offenders[p.name] = named
    assert offenders == {}, f"these modules carry a news table name of their own: {offenders}"


def test_every_news_table_in_the_schema_has_a_name_here():
    """A table added to the News store without a reader seam would reopen the hole this PR closes.

    ``news_earnings`` (#886) is the first table this guard caught: it was added to the board while this step was
    in draft, with its own ``TABLE = "news_earnings"`` and its own two queries.
    """
    schema = {name for name, spec in rawstore.MANIFEST.items() if spec.get("db") == "news"}
    assert schema, "the schema should file some table under the news store"
    assert schema == set(TABLE_NAMES), f"the reader names {sorted(TABLE_NAMES)}, the schema has {sorted(schema)}"


def test_the_lane_cut_is_shared_with_the_page():
    """``report.lane`` (one row) and ``lane_freshness`` (the SQL) must cut the lanes the same way."""
    from RevenueChaser.module_news import headlines, report
    assert sr.LANES == headlines.LANES == ("market", "stocks", "x")
    assert report.lane({"provider": "x-follow", "tickers": "[]"}) == "x"
    assert report.lane({"provider": "ibkr", "tickers": "[]"}) == "market"
    assert report.lane({"provider": "ibkr", "tickers": '["AAPL"]'}) == "stocks"


# ── news_meta ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _meta(**pairs) -> None:
    rawstore.write_rows(sr.META, [{"key": k, "value": v, "run_at": NOW} for k, v in pairs.items()])


def test_a_mark_never_written_reads_as_none(rawstore_tmp_db):
    assert sr.meta_value("nothing_here") is None
    assert sr.meta_values(["a", "b"]) == {}
    assert sr.meta_values([]) == {}


def test_a_mark_reads_back_as_the_text_it_was_written_as(rawstore_tmp_db):
    _meta(calendar_mark="1763000000.0", x_follow_state=json.dumps({"newest": 7}))
    assert sr.meta_value("calendar_mark") == "1763000000.0"
    assert json.loads(sr.meta_value("x_follow_state")) == {"newest": 7}
    assert sr.meta_values(["calendar_mark", "absent"]) == {"calendar_mark": "1763000000.0"}


# ── news_events ───────────────────────────────────────────────────────────────────────────────────────────────────
def _event(ts, name, kind="report", retired=None, last_seen=None, run_at=None) -> dict:
    return {"event_ts": ts, "event": name, "type": kind, "importance": 3, "forecast": None, "prev": None,
            "reported_period": None, "first_seen": NOW, "last_seen": NOW if last_seen is None else last_seen,
            "retired_at": retired, "run_id": "t", "run_at": NOW if run_at is None else run_at}


def test_the_build_sees_a_retired_row_and_the_page_does_not(rawstore_tmp_db):
    """A retired event keeps its row for ever (nothing is deleted), so a page read has to filter it out and the
    build read must not: it carries ``first_seen`` forward from exactly that row."""
    rawstore.write_rows(sr.EVENTS, [_event(NOW, "CPI"), _event(NOW + 60, "Gone", retired=NOW)])
    assert {r["event"] for r in sr.events_between(NOW - 1, NOW + 100)} == {"CPI", "Gone"}
    assert {r["event"] for r in sr.live_economic_between(NOW - 1, NOW + 100)} == {"CPI"}
    assert {r["event"] for r in sr.live_economic_from(NOW - 1)} == {"CPI"}
    assert {r["event"] for r in sr.live_events_in_window(NOW - 1, NOW + 100)} == {"CPI"}


def test_the_event_windows_are_inclusive_and_half_open_as_their_callers_expect(rawstore_tmp_db):
    rawstore.write_rows(sr.EVENTS, [_event(100.0, "At the start"), _event(200.0, "At the end")])
    # ``BETWEEN`` for the build's key span: both ends in.
    assert len(sr.events_between(100.0, 200.0)) == 2
    assert len(sr.live_economic_between(100.0, 200.0)) == 2
    # ``[start, end)`` for the page's week: the day after the window is the next page's first row.
    assert [r["event"] for r in sr.live_events_in_window(100.0, 200.0)] == ["At the start"]
    assert len(sr.live_events_in_window(100.0, 201.0)) == 2
    assert [r["event"] for r in sr.live_economic_from(200.0)] == ["At the end"]


def test_the_window_breaks_a_tie_by_name_so_two_pages_cannot_disagree(rawstore_tmp_db):
    """The Welcome card read this window ordered by ``event_ts`` alone; both read this one now."""
    rawstore.write_rows(sr.EVENTS, [_event(100.0, "Zeta"), _event(100.0, "Alpha"), _event(90.0, "Earlier")])
    assert [r["event"] for r in sr.live_events_in_window(0.0, 200.0)] == ["Earlier", "Alpha", "Zeta"]
    assert [r["event"] for r in sr.live_economic_from(0.0)][0] == "Earlier"


def test_the_two_event_stamps_answer_different_questions(rawstore_tmp_db):
    """``last_seen`` is the source's fetch, ``run_at`` the build's write: the page's "updated" is the second, the
    provenance line's data date the first."""
    assert sr.newest_event_fetch_at() is None and sr.newest_event_run_at() is None
    rawstore.write_rows(sr.EVENTS, [_event(100.0, "Old", last_seen=10.0, run_at=50.0),
                                    _event(200.0, "New", last_seen=20.0, run_at=60.0)])
    assert sr.newest_event_fetch_at() == 20.0
    assert sr.newest_event_run_at() == 60.0


def test_the_news_boards_data_date_is_the_newest_calendar_fetch(rawstore_tmp_db):
    """The bug this PR fixes: ``core/provenance._news_day`` asked ``news_calendar`` for ``max(fetched_at)``, and
    no such table exists in that file, so the News board showed no data date whatever it held (a read of a missing
    table answers no rows)."""
    assert provenance._news_day() is None                     # nothing stored: still None, for the right reason
    rawstore.write_rows(sr.EVENTS, [_event(100.0, "CPI", last_seen=NOW)])
    assert provenance._news_day() == provenance.session_of(NOW)
    assert provenance._news_day() is not None


# ── news_events: the FDA lane shares the table (#807) ─────────────────────────────────────────────────────────────
def _fda(ts, name, precision="day", retired=None) -> dict:
    return {**_event(ts, name, kind=sr.FDA_TYPE, retired=retired), "ticker": "ABC", "drug": "d",
            "catalyst": "PDUFA", "target_text": name, "target_precision": precision, "indication": None,
            "status": None, "outcome": None, "url": None}


def test_neither_pass_can_retire_the_other_lanes_rows(rawstore_tmp_db):
    """The two passes write the same table and each retires what its own source stopped listing, so the economic
    reads must not see an FDA row and the FDA read must see nothing else. Before #217 that was four ``type``
    filters in two files, each spelling the word ``fda`` itself."""
    rawstore.write_rows(sr.EVENTS, [_event(100.0, "CPI"), _fda(200.0, "PDUFA ABC")])
    assert [r["event"] for r in sr.live_economic_between(0.0, 500.0)] == ["CPI"]
    assert [r["event"] for r in sr.live_economic_from(0.0)] == ["CPI"]
    assert [r["event"] for r in sr.live_fda_between(0.0, 500.0)] == ["PDUFA ABC"]
    # The week strip is the one read that shows both, because the page draws them on the same days (#808).
    assert {r["event"] for r in sr.live_events_in_window(0.0, 500.0)} == {"CPI", "PDUFA ABC"}


def test_a_retired_row_is_invisible_to_both_lane_reads(rawstore_tmp_db):
    rawstore.write_rows(sr.EVENTS, [_fda(100.0, "Gone", retired=NOW), _fda(200.0, "Here")])
    assert [r["event"] for r in sr.live_fda_between(0.0, 500.0)] == ["Here"]


def test_the_undated_catalysts_are_the_ones_with_no_day_of_their_own(rawstore_tmp_db):
    """A quarter or a half year belongs to no day of the week strip, so the page reads those rows on their own
    (#808). A row with no precision at all counts as dated, which is the coalesce in the SQL."""
    rawstore.write_rows(sr.EVENTS, [
        _fda(100.0, "On a day", precision="day"),
        _fda(200.0, "In Q2 2027", precision="quarter"),
        _fda(300.0, "Late 2027", precision="half"),
        {**_fda(400.0, "No precision"), "target_precision": None},
        _event(500.0, "CPI"),                                      # an economic row is never undated
        _fda(50.0, "Before the window", precision="quarter"),
    ])
    got = [r["event"] for r in sr.live_fda_outside_a_day("day", 60.0, 10)]
    assert got == ["In Q2 2027", "Late 2027"]
    assert [r["event"] for r in sr.live_fda_outside_a_day("day", 60.0, 1)] == ["In Q2 2027"]   # the page's cap


def test_the_api_read_answers_for_the_types_it_was_asked_for(rawstore_tmp_db):
    rawstore.write_rows(sr.EVENTS, [_event(100.0, "CPI", kind="report"), _event(200.0, "Powell", kind="fed-speaker"),
                                    _fda(300.0, "PDUFA ABC"), _event(400.0, "Later", kind="report")])
    assert [r["event"] for r in sr.live_events_of_types(0.0, 500.0, None, 10)] == ["CPI", "Powell", "PDUFA ABC",
                                                                                   "Later"]
    assert [r["event"] for r in sr.live_events_of_types(0.0, 500.0, ("REPORT",), 10)] == ["CPI", "Later"]
    assert [r["event"] for r in sr.live_events_of_types(0.0, 500.0, ("fda",), 10)] == ["PDUFA ABC"]
    assert len(sr.live_events_of_types(0.0, 500.0, None, 2)) == 2            # the route's own cap
    assert sr.live_events_of_types(0.0, 500.0, ("", "  "), 10) == [], "an ask of blanks is no types, not every type"
    assert [r["event"] for r in sr.live_events_of_types(0.0, 400.0, None, 10)] == ["CPI", "Powell", "PDUFA ABC"]


# ── news_earnings (#886) ──────────────────────────────────────────────────────────────────────────────────────────
def test_the_earnings_tab_reads_one_week_and_in_the_pages_order(rawstore_tmp_db):
    """The weekly pass empties the table first, so a table holding another week answers no rows here and the tab
    says the week is not built rather than showing last week's days."""
    def row(week_start, ticker, day):
        return {"week_start": week_start, "ticker": ticker, "company": ticker, "report_date": day,
                "report_time": "post-market", "confirmed": True, "source": "alphavantage", "run_id": "t",
                "run_at": NOW}
    assert sr.earnings_week("2026-11-23") == []
    rawstore.write_rows(sr.EARNINGS, [row("2026-11-23", "NVDA", "2026-11-25"),
                                      row("2026-11-23", "AAPL", "2026-11-24"),
                                      row("2026-11-23", "AA", "2026-11-24"),
                                      row("2026-11-16", "MSFT", "2026-11-17")])
    assert [r["ticker"] for r in sr.earnings_week("2026-11-23")] == ["AA", "AAPL", "NVDA"]
    assert [r["ticker"] for r in sr.earnings_week("2026-11-16")] == ["MSFT"]
    assert sr.earnings_week("2026-11-30") == []


# ── news_highlight ────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_highlight_of_a_day_is_one_row_or_none(rawstore_tmp_db):
    assert sr.highlight("2026-11-20") is None
    rawstore.write_rows(sr.HIGHLIGHT, [{"session_date": "2026-11-20", "event_ts": NOW, "event": "CPI",
                                        "type": "report", "importance": 3, "forecast": None, "prev": None,
                                        "text": "t", "text_source": "template", "run_id": "t", "run_at": NOW}])
    assert sr.highlight("2026-11-20")["event"] == "CPI"
    assert sr.highlight("2026-11-21") is None


# ── news_headlines ────────────────────────────────────────────────────────────────────────────────────────────────
def _head(hid, provider="ibkr", tickers=(), published=None, kind=None, fetched=None, run_at=None) -> dict:
    return {"headline_id": hid, "provider": provider, "published_at": NOW if published is None else published,
            "headline": hid, "source": None, "tickers": json.dumps(list(tickers)), "url": None,
            "fetched_at": NOW if fetched is None else fetched, "run_id": "t",
            "run_at": NOW if run_at is None else run_at, "kind": kind, "option": None, "x_check": None}


def test_an_empty_ask_asks_the_store_nothing(rawstore_tmp_db, monkeypatch):
    """Both id readers are called with whatever a pass brought back, which is often nothing."""
    def boom(*a, **k):
        raise AssertionError("an empty ask must not reach the store")
    monkeypatch.setattr(rawstore, "query", boom)
    assert sr.stored_headline_ids([]) == set()
    assert sr.stored_tickers([]) == {}


def test_the_stored_ids_and_tickers_answer_only_for_what_is_held(rawstore_tmp_db):
    rawstore.write_rows(sr.HEADLINES, [_head("ibkr:1", tickers=["AAPL"]), _head("ibkr:2")])
    assert sr.stored_headline_ids(["ibkr:1", "ibkr:9"]) == {"ibkr:1"}
    assert sr.stored_tickers(["ibkr:1", "ibkr:9"]) == {"ibkr:1": '["AAPL"]'}
    # A generator is as good as a list: the callers pass one.
    assert sr.stored_headline_ids(h for h in ("ibkr:2",)) == {"ibkr:2"}


def test_each_lane_gets_its_own_limit_so_a_busy_lane_cannot_crowd_the_page(rawstore_tmp_db):
    rawstore.write_rows(sr.HEADLINES, [
        *[_head(f"ibkr:m{i}", published=NOW - i) for i in range(3)],          # market: three
        _head("ibkr:s1", tickers=["AAPL"], published=NOW - 10),               # stocks: one
        _head("x:1", provider="x-follow", kind="option", published=NOW - 20),   # x: one kept...
        _head("x:2", provider="x-follow", kind="other", published=NOW - 21),    # ...one filed as "other"
    ])
    got = sr.headlines_by_lane(NOW - 3600, limit=2)
    ids = [r["headline_id"] for r in got]
    assert ids.count("ibkr:m0") == 1 and len([i for i in ids if i.startswith("ibkr:m")]) == 2   # limit per lane
    assert "ibkr:s1" in ids and "x:1" in ids
    assert "x:2" not in ids, "the X lane leaves out a row filed as other"


def test_the_lane_read_leaves_out_what_was_published_before_the_window(rawstore_tmp_db):
    rawstore.write_rows(sr.HEADLINES, [_head("ibkr:new", published=NOW), _head("ibkr:old", published=NOW - 90_000)])
    assert [r["headline_id"] for r in sr.headlines_by_lane(NOW - 3600, limit=5)] == ["ibkr:new"]


def test_the_poll_draws_only_rows_written_after_its_mark(rawstore_tmp_db):
    rawstore.write_rows(sr.HEADLINES, [_head("ibkr:1", run_at=100.0), _head("ibkr:2", run_at=200.0)])
    assert [r["headline_id"] for r in sr.headlines_since(100.0, 0.0, 10)] == ["ibkr:2"]
    assert len(sr.headlines_since(0.0, 0.0, 10)) == 2
    assert sr.headlines_since(0.0, NOW + 1, 10) == []          # published before the window
    assert set(sr.headlines_since(0.0, 0.0, 10)[0]) == set(sr.API_COLUMNS)


def test_the_newest_list_crosses_the_lanes_for_the_welcome_card(rawstore_tmp_db):
    rawstore.write_rows(sr.HEADLINES, [_head("ibkr:1", published=NOW - 5),
                                       _head("x:1", provider="x-follow", kind="other", published=NOW)])
    # Unlike the board's own page, this one does not cut the lanes — the card shows the latest, whatever lane.
    assert [r["headline_id"] for r in sr.headlines_newest(NOW - 3600, 5)] == ["x:1", "ibkr:1"]
    assert [r["headline_id"] for r in sr.headlines_newest(NOW - 3600, 1)] == ["x:1"]


def test_a_ticker_matches_as_a_whole_name_and_not_as_a_prefix(rawstore_tmp_db):
    """``tickers`` is JSON text: a bare substring match would let AA answer for AAPL."""
    rawstore.write_rows(sr.HEADLINES, [_head("ibkr:1", tickers=["AAPL"]), _head("ibkr:2", tickers=["AA"]),
                                       _head("x:1", provider="x-follow", tickers=["AAPL"])])
    assert [r["headline_id"] for r in sr.headlines_for_ticker("AA", 0.0, 10)] == ["ibkr:2"]
    assert [r["headline_id"] for r in sr.headlines_for_ticker("aapl", 0.0, 10)] == ["ibkr:1"]
    assert set(sr.headlines_for_ticker("AA", 0.0, 10)[0]) == set(sr.TICKER_COLUMNS)


def test_the_window_read_is_bounded_at_both_ends(rawstore_tmp_db):
    """``GET /api/news/headlines`` asked for a window is what makes the join of #809 possible: the headlines
    around a release, not the last 24 hours. The lane and ticker cuts stay with the route, in Python."""
    rawstore.write_rows(sr.HEADLINES, [_head("ibkr:before", published=100.0), _head("ibkr:in", published=200.0),
                                       _head("ibkr:also", published=300.0), _head("ibkr:after", published=400.0)])
    assert [r["headline_id"] for r in sr.headlines_in_window(200.0, 300.0, 10)] == ["ibkr:also", "ibkr:in"]
    assert [r["headline_id"] for r in sr.headlines_in_window(200.0, 300.0, 1)] == ["ibkr:also"]
    assert set(sr.headlines_in_window(0.0, 500.0, 10)[0]) == set(sr.API_COLUMNS)


def test_the_option_check_walks_the_x_lane_only(rawstore_tmp_db):
    rawstore.write_rows(sr.HEADLINES, [
        _head("x:1", provider="x-follow", kind="option", published=NOW),
        _head("x:2", provider="x-follow", kind="news", published=NOW - 1),
        _head("x:3", provider="x-follow", kind="other", published=NOW - 2),
        _head("ibkr:1", kind="news", published=NOW - 3),
        _head("x:old", provider="x-follow", kind="option", published=NOW - 90_000),
    ])
    assert [r["headline_id"] for r in sr.x_headlines_since(NOW - 3600)] == ["x:1", "x:2"]


def test_the_lane_freshness_reads_each_lane_on_its_own(rawstore_tmp_db):
    assert sr.lane_freshness() == {"market": None, "stocks": None, "x": None}
    rawstore.write_rows(sr.HEADLINES, [
        _head("ibkr:m", fetched=NOW - 60), _head("ibkr:m2", fetched=NOW - 600),
        _head("ibkr:s", tickers=["AAPL"], fetched=NOW - 90_000),
        _head("x:1", provider="x-follow", fetched=NOW - 300),
        _head("x:2", provider="x-follow", tickers=["SPY"], fetched=NOW - 30),
    ])
    # The newest fetch a lane, not of the table: an X row with a cashtag is still the X lane, and the per-ticker
    # lane stays a day old however busy the others are (review F2, 18 Nov 2026).
    assert sr.lane_freshness() == {"market": NOW - 60, "stocks": NOW - 90_000, "x": NOW - 30}


def test_an_x_provider_is_passed_as_a_parameter_and_not_interpolated(rawstore_tmp_db, monkeypatch):
    """The lane SQL used to splice ``repr(provider)`` into the text. The providers are our own constants, so this
    was never an injection, but a parameter is the shape the rest of the board already used."""
    seen = {}
    real = rawstore.query

    def spy(sql, params=None, **kw):
        seen["sql"], seen["params"] = sql, params
        return real(sql, params, **kw)
    monkeypatch.setattr(rawstore, "query", spy)
    sr.lane_freshness()
    assert "x-follow" not in seen["sql"] and "'x-follow'" not in seen["sql"]
    assert "x-follow" in (seen["params"] or [])
