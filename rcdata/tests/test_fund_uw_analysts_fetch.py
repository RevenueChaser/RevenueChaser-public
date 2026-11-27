"""``uw/screener_analysts``'s ``fetch()`` driven at the HTTP boundary (#1588).

A transport that answers like UW: ``/screener/analysts`` serves the market-wide feed newest first, honours
``older_than`` and ``limit``, refuses an explicit ``older_than`` before the token's floor with UW's own words, and
answers a ticker-filtered query with that ticker's rows -- including rows older than the floor, the quirk pass 2
exists for. The tests read the result where it lands: the raw files, the query strings UW was sent, and the run's
issues.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs

import pytest

from revenuechaser.core.providers import unusual_whales
from revenuechaser.rcdata import ops
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.fundamentals import uw_analysts as ua

AS_OF = date(2026, 11, 27)
LIMIT = 3                       # the real 500 with small fixtures: ``PAGE_LIMIT`` is patched to it


@pytest.fixture(autouse=True)
def uw_env(monkeypatch):
    monkeypatch.setenv("UNUSUAL_WHALES_API_KEY", "test-key")
    monkeypatch.setattr(unusual_whales, "BASE", "https://uw.test/api")
    monkeypatch.setattr(unusual_whales, "_sleep", lambda _s: None)
    monkeypatch.setattr(ua, "PAGE_LIMIT", LIMIT)
    monkeypatch.setattr(ua, "delisted_tickers", lambda: [])
    monkeypatch.setattr(ua, "live_tickers", lambda: [])


def _rating(ticker: str, when: datetime) -> dict:
    return {"ticker": ticker, "timestamp": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "action": "maintained",
            "recommendation": "buy", "target": "266.0000", "analyst_name": "A", "firm": "F", "sector": "Technology"}


def _params(request) -> dict:
    return {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}


def uw_like(rows: list[dict]):
    """A transport body for ``/screener/analysts``: UW's own paging and its floor."""
    def handle(request):
        p = _params(request)
        got = sorted(rows, key=lambda r: r["timestamp"], reverse=True)
        if p.get("ticker"):
            got = [r for r in got if r["ticker"] == p["ticker"]]
        older = p.get("older_than")
        if older:
            if older[:10] < ua.FLOOR.isoformat() and not p.get("ticker"):
                return 422, json.dumps({"error": "The earliest date currently available to this token is "
                                                 "2023-12-28"}), {}
            got = [r for r in got if r["timestamp"] < older]
        return 200, json.dumps({"data": got[:int(p.get("limit", LIMIT))]}), {}
    return handle


def _fetch(as_of=AS_OF):
    ctx = base.RunContext(run_id=f"t-{as_of}", dataset=ua.NAME)
    try:
        return ctx, ua.DATASET.fetch(ctx, as_of)
    finally:
        ctx.close()
        ctx.flush_counts()


def _queries(http_mock) -> list[dict]:
    return [_params(r) for r in http_mock.calls("/screener/analysts")]


# ── Pass 1: the market-wide feed ────────────────────────────────────────────────────────────────────────────────

def test_the_feed_pages_back_with_older_than_the_oldest_row_of_the_page(http_mock):
    """Seven ratings, three to a page: the cursor of each request is the oldest ``timestamp`` of the page before
    it, and the short last page ends pass 1."""
    start = datetime(2026, 11, 20, 12)
    rows = [_rating(f"T{n}", start - timedelta(days=n)) for n in range(7)]
    http_mock.add("/screener/analysts", uw_like(rows))
    ctx, out = _fetch()
    asked = [q for q in _queries(http_mock) if "ticker" not in q]
    assert [q.get("older_than") for q in asked] == [None, rows[2]["timestamp"], rows[5]["timestamp"]]
    assert all(q["limit"] == str(LIMIT) for q in asked)
    pages = sorted(p.name for p in ua.feed_dir(AS_OF).glob("*.json.gz"))
    assert pages == ["page-0000.json.gz", "page-0001.json.gz", "page-0002.json.gz"]
    assert set(pages) <= {p.name for p in out}


def test_a_page_shorter_than_the_limit_ends_pass_one(http_mock):
    http_mock.add("/screener/analysts", uw_like([_rating("AAA", datetime(2026, 11, 20, 12))]))
    _fetch()
    assert [q for q in _queries(http_mock) if "ticker" not in q] == [{"limit": str(LIMIT)}]
    assert len(list(ua.feed_dir(AS_OF).glob("*.json.gz"))) == 1


def test_pass_one_stops_at_the_tokens_floor_and_never_asks_below_it(http_mock):
    """The feed reaching 2023-12-28 is the end: an explicit ``older_than`` before it is refused by UW, so the run
    must not send one."""
    rows = [_rating("AAA", datetime(2024, 1, 2, 12)), _rating("BBB", datetime(2024, 1, 1, 12)),
            _rating("CCC", datetime(2023, 12, 28, 12)), _rating("DDD", datetime(2023, 11, 1, 12))]
    http_mock.add("/screener/analysts", uw_like(rows))
    _fetch()
    sent = [q.get("older_than") for q in _queries(http_mock) if "ticker" not in q]
    assert sent == [None]
    assert not [s for s in sent if s and s[:10] < ua.FLOOR.isoformat()]


def test_a_feed_page_already_written_is_read_and_not_asked_again(http_mock):
    """The raw page is the resume marker: a run that stopped halfway carries on from the next page."""
    start = datetime(2026, 11, 20, 12)
    rows = [_rating(f"T{n}", start - timedelta(days=n)) for n in range(6)]
    base.write_raw_json(ua.feed_path(AS_OF, 0), {"as_of": AS_OF.isoformat(), "fetched_at": 1.0, "run_id": "earlier",
                                                 "pass": "feed", "page": 0, "body": {"data": rows[:3]}})
    http_mock.add("/screener/analysts", uw_like(rows))
    _fetch()
    # Page 0 is not asked again (no request without a cursor); paging carries on from its oldest row.
    asked = [q.get("older_than") for q in _queries(http_mock) if "ticker" not in q]
    assert None not in asked and asked[0] == rows[2]["timestamp"]
    assert base.read_raw_json(ua.feed_path(AS_OF, 0))["run_id"] == "earlier"


def test_a_provider_side_failure_in_the_feed_fails_the_run_and_keeps_the_pages(http_mock):
    rows = [_rating(f"T{n}", datetime(2026, 11, 20, 12) - timedelta(days=n)) for n in range(6)]
    answers = uw_like(rows)
    state = {"n": 0}

    def flaky(request):
        state["n"] += 1
        return (503, b"upstream down", {}) if state["n"] > 1 else answers(request)

    http_mock.add("/screener/analysts", flaky)
    with pytest.raises(base.SourceError):
        _fetch()
    assert [p.name for p in ua.feed_dir(AS_OF).glob("*.json.gz")] == ["page-0000.json.gz"]


# ── Pass 2: one call per ticker, delisted first ─────────────────────────────────────────────────────────────────

def test_pass_two_asks_every_ticker_the_feed_saw_and_the_delisted_names_first(http_mock, monkeypatch):
    monkeypatch.setattr(ua, "delisted_tickers", lambda: ["SGEN"])
    rows = [_rating("AAA", datetime(2026, 11, 20, 12)), _rating("SGEN", datetime(2023, 11, 1, 12))]
    http_mock.add("/screener/analysts", uw_like(rows))
    ctx, out = _fetch()
    assert [q["ticker"] for q in _queries(http_mock) if "ticker" in q] == ["SGEN", "AAA"]
    assert sorted(p.name for p in ua.ticker_dir(AS_OF).glob("*.json.gz")) == ["AAA.json.gz", "SGEN.json.gz"]
    doc = base.read_raw_json(ua.ticker_path(AS_OF, "SGEN"))
    assert [r["ticker"] for r in ua.rows_of(doc["body"])] == ["SGEN"]      # pre-floor rows, the quirk pass 2 is for


def test_every_pass_two_call_asks_below_the_floor(http_mock, monkeypatch):
    """A ticker call carries `older_than` = the day after the floor, so it answers the pre-floor tail instead of
    the newest 500 rows -- which for a busy name would never reach 2023 and would only repeat pass 1."""
    monkeypatch.setattr(ua, "delisted_tickers", lambda: ["SGEN"])
    rows = [_rating("AAA", datetime(2026, 11, 20, 12)), _rating("SGEN", datetime(2023, 11, 1, 12))]
    http_mock.add("/screener/analysts", uw_like(rows))
    _fetch()
    asked = [q for q in _queries(http_mock) if "ticker" in q]
    assert asked and all(q["older_than"] == ua.PASS2_FROM.isoformat() for q in asked)


def test_a_full_pass_two_page_is_paged_on(http_mock, monkeypatch):
    """Measured: every probe ticker answered in one call (AAPL, the busiest, 127 rows). A name nobody measured
    with more than a page still has its whole tail read."""
    monkeypatch.setattr(ua, "delisted_tickers", lambda: ["BIG"])
    start = datetime(2023, 12, 20, 12)
    rows = [_rating("BIG", start - timedelta(days=n)) for n in range(7)]
    http_mock.add("/screener/analysts", uw_like(rows))
    _fetch()
    asked = [q["older_than"] for q in _queries(http_mock) if q.get("ticker") == "BIG"]
    assert asked == [ua.PASS2_FROM.isoformat(), rows[2]["timestamp"], rows[5]["timestamp"]]
    assert len(ua.rows_of(base.read_raw_json(ua.ticker_path(AS_OF, "BIG"))["body"])) == 7


def test_a_rejected_ticker_is_kept_as_an_empty_answer_once_a_later_one_answers(http_mock, monkeypatch):
    monkeypatch.setattr(ua, "delisted_tickers", lambda: ["GONE"])
    rows = [_rating("AAA", datetime(2026, 11, 20, 12))]
    answers = uw_like(rows)

    def handle(request):
        return (422, json.dumps({"error": "unknown ticker"}), {}) if _params(request).get("ticker") == "GONE" \
            else answers(request)

    http_mock.add("/screener/analysts", handle)
    ctx, out = _fetch()
    doc = base.read_raw_json(ua.ticker_path(AS_OF, "GONE"))
    assert doc["body"] is None and doc["rejected"]
    assert ua.table_rows(doc["body"], {"source_as_of": AS_OF, "fetched_at": 1.0, "run_id": "t"}) == ([], {})
    assert "fetch_failed" in [i["kind"] for i in ops.open_issues(ua.NAME)[1]]


def test_reject_streak_rejected_requests_in_a_row_stop_the_run(http_mock, monkeypatch):
    monkeypatch.setattr(ua, "delisted_tickers", lambda: [f"D{n:02d}" for n in range(ua.REJECT_STREAK + 5)])
    http_mock.add("/screener/analysts", uw_like([_rating("AAA", datetime(2026, 11, 20, 12))]))

    def handle(request):
        p = _params(request)
        if p.get("ticker", "").startswith("D"):
            return 404, b"no such path", {}
        return uw_like([_rating("AAA", datetime(2026, 11, 20, 12))])(request)

    http_mock.routes.clear()
    http_mock.add("/screener/analysts", handle)
    with pytest.raises(base.SourceError, match="rejected"):
        _fetch()
    assert len([q for q in _queries(http_mock) if "ticker" in q]) == ua.REJECT_STREAK


def test_fail_streak_provider_side_failures_stop_the_run_and_keep_what_was_answered(http_mock, monkeypatch):
    monkeypatch.setattr(ua, "delisted_tickers", lambda: ["AAA", *[f"Z{n}" for n in range(ua.FAIL_STREAK + 3)]])
    good = uw_like([_rating("AAA", datetime(2026, 11, 20, 12))])

    def handle(request):
        p = _params(request)
        if p.get("ticker", "").startswith("Z"):
            return 503, b"upstream down", {}
        return good(request)

    http_mock.add("/screener/analysts", handle)
    with pytest.raises(base.SourceError, match="provider-side failures"):
        _fetch()
    assert [p.name for p in ua.ticker_dir(AS_OF).glob("*.json.gz")] == ["AAA.json.gz"]
    # The day's Parquet is written before the run fails: what UW answered is not thrown away.
    assert (ua.common.parquet_dir(ua.NAME) / f"date={AS_OF}" / "part-0.parquet").exists()


def test_a_ticker_already_written_is_not_asked_again(http_mock, monkeypatch):
    monkeypatch.setattr(ua, "delisted_tickers", lambda: ["SGEN"])
    base.write_raw_json(ua.ticker_path(AS_OF, "SGEN"), {"as_of": AS_OF.isoformat(), "fetched_at": 1.0,
                                                        "run_id": "earlier", "pass": "ticker", "ticker": "SGEN",
                                                        "body": {"data": []}})
    http_mock.add("/screener/analysts", uw_like([_rating("AAA", datetime(2026, 11, 20, 12))]))
    _fetch()
    assert [q["ticker"] for q in _queries(http_mock) if "ticker" in q] == ["AAA"]


# ── The key ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_without_a_key_nothing_is_asked_and_the_run_says_so(http_mock, monkeypatch):
    monkeypatch.delenv("UNUSUAL_WHALES_API_KEY", raising=False)
    ctx, out = _fetch()
    assert out == [] and not http_mock.calls("/screener/analysts")
    assert [i["kind"] for i in ops.open_issues(ua.NAME)[1]] == ["missing_key"]


# ── The day's Parquet ──────────────────────────────────────────────────────────────────────────────────────────

def test_the_days_parquet_holds_each_rating_event_once(http_mock):
    """The feed page and the ticker call answer the same event: it is written once."""
    rows = [_rating("AAA", datetime(2026, 11, 20, 12)), _rating("BBB", datetime(2026, 11, 19, 12))]
    http_mock.add("/screener/analysts", uw_like(rows))
    ctx, out = _fetch()
    parts = ua.DATASET.to_parquet_all(ctx, out)
    import duckdb
    con = duckdb.connect()
    try:
        got = con.execute("SELECT ticker, published_at, target FROM read_parquet(?) ORDER BY ticker",
                          [str(parts[0])]).fetchall()
    finally:
        con.close()
    assert got == [("AAA", datetime(2026, 11, 20, 12), 266.0), ("BBB", datetime(2026, 11, 19, 12), 266.0)]
