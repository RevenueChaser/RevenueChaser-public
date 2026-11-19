"""News headlines from the IBKR Gateway (avo, 9 Nov 20:54 Amsterdam: "Ibkr kullanalim"): Dow Jones headlines per
ticker through ``reqHistoricalNews``, against a fake gateway. The client asks for contract ids and news only: never an
account, a position or an order.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.core.providers import ibkr_tws as ibkr
from RevenueChaser.module_news import headlines
from RevenueChaser.rcdata.tests.ibkr_fixture import ACCOUNT_PLACEHOLDER, FakeGateway, frame

NOW = datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc).timestamp()
ALLOWED = {"71", "9", "86"}          # startApi, reqContractDetails, reqHistoricalNews


class NewsGateway(FakeGateway):
    def __init__(self):
        super().__init__(last_bar=date(2026, 11, 6))
        self.con_ids = {"AAPL": 265598, "NVDA": 4815747, "CRWV": 7001}
        self.news: dict[int, list[tuple]] = {}
        self.unknown: set[str] = set()
        self.refused: dict[str, tuple[int, str]] = {}     # con id -> the error a news request gets
        self.hmds_down = False                            # 2105 at startApi, then news requests get no answer

    def recv(self, n: int) -> bytes:
        if not self._out and self.hmds_down:
            raise TimeoutError("timed out")               # the real socket's read timeout
        return super().recv(n)

    def _answer(self, fields):
        msg = fields[0]
        if msg == "9":                                    # reqContractDetails: [9, 8, reqId, conId, symbol, ...]
            req_id, symbol = fields[2], fields[4]
            if symbol in self.unknown or symbol not in self.con_ids:
                self._out += frame(4, 2, req_id, 200, "No security definition has been found", "")
                return
            self._out += frame(10, req_id, symbol, "STK", "", 0, "", "SMART", "USD", symbol, "NMS", symbol,
                               self.con_ids[symbol], 0.01, "", "ACTIVETIM", "SMART,NASDAQ")
            self._out += frame(52, 1, req_id)
        elif msg == "86":                                 # [86, reqId, conId, providers, start, end, total, options]
            req_id, con_id = fields[1], int(fields[2])
            if self.hmds_down:
                return                                    # measured 18 Nov 2026: no answer at all, not even an error
            if fields[2] in self.refused:
                code, text = self.refused[fields[2]]
                self._out += frame(4, 2, req_id, code, text, "")
                return
            for row in self.news.get(con_id, []):
                self._out += frame(86, req_id, *row)
            self._out += frame(87, req_id, 0)
        else:
            super()._answer(fields)
            if msg == "71" and self.hmds_down:
                self._out += frame(4, 2, -1, 2105, "HMDS data farm connection is broken:ushmds", "")


@pytest.fixture(autouse=True)
def _fresh_con_ids(monkeypatch):
    monkeypatch.setattr(headlines, "_CON_IDS", {})        # the cache lives as long as the dashboard process


@pytest.fixture
def gw(monkeypatch):
    g = NewsGateway()
    monkeypatch.setattr(ibkr, "CONNECT", g.connect)
    g.news[265598] = [("2026-11-09 18:20:00.0", "DJ-N", "DJ-N$1a2b", "{A:800015:L:en:K:n/a:C:0.97}!Apple Expands AI Deal"),
                      ("2026-11-09 17:00:00.0", "DJ-RT", "DJ-RT$9", "Tech Stocks Rally as Yields Slip")]
    g.news[4815747] = [("2026-11-09 18:25:00.0", "DJ-N", "DJ-N$3c", "Nvidia, Apple Lead Gains"),
                       ("2026-11-09 17:00:00.0", "DJ-N", "DJ-N$dup", "Tech Stocks Rally as Yields Slip")]
    return g


def _rows():
    return {r["headline"]: r for r in rawstore.query("SELECT * FROM news_headlines", db="news")}


def test_the_client_asks_for_contract_ids_and_news_only(gw):
    with ibkr.TWSClient("127.0.0.1", 4001, client_id=headlines.CLIENT_ID) as c:
        cid = c.con_id(1, ibkr.contract_for("AAPL"))
        got = c.news(2, cid, "DJ-N+DJ-RT", "", "", 10)
        assert ACCOUNT_PLACEHOLDER not in repr(vars(c))
    assert cid == 265598 and len(got) == 2 and got[0]["article_id"] == "DJ-N$1a2b"
    assert set(gw.message_ids()) <= ALLOWED
    assert gw.sent[0] == ["71", "2", str(headlines.CLIENT_ID), ""]


def test_an_unknown_ticker_raises_a_request_error(gw):
    gw.unknown.add("ZZZZ")
    with ibkr.TWSClient("127.0.0.1", 4001) as c:
        with pytest.raises(ibkr.HistoryError) as e:
            c.con_id(1, ibkr.contract_for("ZZZZ"))
    assert e.value.code == 200


def test_fetch_stores_clean_headlines_with_their_tickers_once(gw):
    out = headlines.fetch(["AAPL", "NVDA"], now=NOW, run_id="r1")
    rows = _rows()
    assert "Apple Expands AI Deal" in rows                              # the {…}! metadata prefix is cut
    assert rows["Apple Expands AI Deal"]["published_at"] == datetime(2026, 11, 9, 18, 20,
                                                                     tzinfo=timezone.utc).timestamp()
    assert rows["Apple Expands AI Deal"]["provider"] == "ibkr" and rows["Apple Expands AI Deal"]["source"] == "Dow Jones"
    same = rows["Tech Stocks Rally as Yields Slip"]                     # one story, two tickers, two article ids
    assert sorted(json.loads(same["tickers"])) == ["AAPL", "NVDA"]
    assert out == {"tickers": 2, "of": 2, "stored": 3, "skipped": [], "failed": [], "error": None}


def test_a_name_the_gateway_does_not_know_is_skipped_not_fatal(gw):
    gw.unknown.add("CRWV")
    out = headlines.fetch(["CRWV", "AAPL"], now=NOW, run_id="r1")
    assert out["skipped"] == ["CRWV"] and out["stored"] == 2


def test_a_gateway_that_is_down_writes_nothing_and_says_so(gw):
    gw.down = True
    out = headlines.fetch(["AAPL"], now=NOW, run_id="r1")
    assert out["stored"] == 0 and "gateway" in out["error"] and _rows() == {}


def test_a_second_fetch_asks_the_newest_and_writes_only_what_is_new(gw):
    headlines.fetch(["AAPL"], now=NOW, run_id="r1")
    gw.news[265598].insert(0, ("2026-11-09 19:40:00.0", "DJ-N", "DJ-N$new", "Apple Sets Event Date"))
    out = headlines.fetch(["AAPL"], now=NOW + 3600, run_id="r2")
    # The gateway reads a start time as the newest time to return (11 Nov: the board sat a day behind), so none is sent.
    assert [f[4] for f in gw.sent if f[0] == "86"] == ["", ""]
    assert out["stored"] == 1                                   # the two stories of the first pass are not rewritten
    assert _rows()["Apple Expands AI Deal"]["run_id"] == "r1"


def test_a_pass_asks_the_next_names_in_turn_and_wraps_round(gw, monkeypatch):
    # W1, 18 Nov 2026: every name every 5 minutes is ~780 requests; IBKR paces history requests, so names take turns.
    monkeypatch.setattr(headlines, "PER_PASS", 2)
    names = ["NVDA", "CRWV", "AAPL"]
    assert headlines.fetch(names, now=NOW, run_id="r1")["tickers"] == 2
    headlines.fetch(names, now=NOW + 300, run_id="r2")
    asked = [int(f[2]) for f in gw.sent if f[0] == "86"]
    assert asked == [265598, 7001, 4815747, 265598]            # AAPL, CRWV; then NVDA and round again to AAPL


def test_a_down_gateway_does_not_move_the_turn(gw, monkeypatch):
    monkeypatch.setattr(headlines, "PER_PASS", 1)
    gw.down = True
    headlines.fetch(["NVDA", "AAPL"], now=NOW, run_id="r1")
    assert headlines.batch(["NVDA", "AAPL"]) == ["AAPL"]


def test_a_pass_never_asks_more_than_its_share_of_a_long_list():
    names = [f"T{i:03d}" for i in range(391)]
    assert len(headlines.batch(names)) == headlines.PER_PASS <= 30


def test_the_names_are_both_lists_in_order_with_no_cap_and_no_list_in_code():
    # avo, 18 Nov 2026: every list News reads is a watch list; no hard-coded names, no 25-name cut.
    stock = [f"S{i:02d}" for i in range(30)] + ["NVDA"]
    names = headlines.tickers(stock, ["NVDA", "AAPL"])
    assert names[:31] == sorted(stock) and names[31:] == ["AAPL"] and len(set(names)) == len(names)
    assert not hasattr(headlines, "BASE_TICKERS") and not hasattr(headlines, "MAX_TICKERS")
    assert headlines.LISTS == ("", "stock", "news")              # avo's own lists first


def test_the_same_story_under_another_provider_in_a_later_run_is_one_row(gw):
    headlines.fetch(["AAPL"], now=NOW, run_id="r1")
    gw.news[265598] = [("2026-11-09 18:21:00.0", "DJ-RT", "DJ-RT$77", "Apple Expands AI Deal")]
    headlines.fetch(["AAPL"], now=NOW + 3600, run_id="r2")
    got = rawstore.query("SELECT count(*) AS n FROM news_headlines WHERE headline = 'Apple Expands AI Deal'", db="news")
    assert got == [{"n": 1}]


def test_a_later_pass_reuses_the_contract_id(gw):
    headlines.fetch(["AAPL"], now=NOW, run_id="r1")
    headlines.fetch(["AAPL"], now=NOW + 300, run_id="r2")
    assert gw.message_ids().count("9") == 1 and gw.message_ids().count("86") == 2


def test_a_broken_historical_data_farm_is_named_not_a_bare_timeout(gw):
    # Measured on homesrv 18 Nov 2026: notice 2105 "broken:ushmds", then every news request silent until the timeout.
    gw.hmds_down = True
    out = headlines.fetch(["AAPL"], now=NOW, run_id="r1")
    assert out["stored"] == 0 and "historical data farm is down" in out["error"] and "ushmds" in out["error"]


def test_a_farm_that_comes_back_is_no_longer_blamed():
    client = ibkr.TWSClient("127.0.0.1", 4001)
    client._buf = frame(4, 2, -1, 2105, "HMDS data farm connection is broken:ushmds", "") + \
        frame(4, 2, -1, 2106, "HMDS data farm connection is OK:ushmds", "")
    client._read(), client._read()
    assert client.hmds_broken is None


def test_a_refused_news_request_is_a_failure_not_an_unknown_name(gw):
    # Review F1: only 200 "no security definition" is an unknown name; another code is shown on the board.
    gw.refused["4815747"] = (10276, "News feed is not allowed")
    out = headlines.fetch(["NVDA", "AAPL"], now=NOW, run_id="r1")
    assert out["skipped"] == [] and len(out["failed"]) == 1 and out["failed"][0].startswith("NVDA (IBKR error 10276")
    assert out["stored"] == 2                                   # the other name still stores


# ── One name on demand (plan step 3, the page's ticker box) ──

def test_a_ticker_ask_is_one_request_of_its_own_client_with_briefing_too(gw):
    gw.news[4815747] = [("2026-11-09 18:25:00.0", "DJ-N", "DJ-N$3c", "Nvidia, Apple Lead Gains"),
                        ("2026-11-08 14:00:00.0", "BRFUPDN", "BRF$1", "NVDA upgraded to Buy at Example Securities"),
                        ("2026-11-01 14:00:00.0", "BRFG", "BRF$2", "Older than a week")]
    ask = headlines.fetch_ticker("nvda", now=NOW)
    assert gw.sent[0] == ["71", "2", str(headlines.ON_DEMAND_CLIENT_ID), ""] and headlines.ON_DEMAND_CLIENT_ID != headlines.CLIENT_ID
    news = [f for f in gw.sent if f[0] == "86"]
    assert len(news) == 1 and news[0][3] == "DJ-N+DJ-RT+BRFG+BRFUPDN" and news[0][6] == "300"
    assert ask == {"at": NOW, "stored": 2, "found": 2, "error": None}
    rows = _rows()
    assert rows["NVDA upgraded to Buy at Example Securities"]["source"] == "Briefing"
    assert rows["Nvidia, Apple Lead Gains"]["source"] == "Dow Jones" and "Older than a week" not in rows


def test_the_page_reads_back_the_names_rows_and_the_last_answer(gw):
    headlines.fetch(["AAPL", "NVDA"], now=NOW, run_id="r1")
    gw.hmds_down = True
    ask = headlines.fetch_ticker("NVDA", now=NOW + 60)
    got = headlines.ticker_rows("NVDA", now=NOW + 120)
    assert "historical data farm is down" in ask["error"] and got["ask"]["error"] == ask["error"]
    assert [r["headline"] for r in got["rows"]] == ["Nvidia, Apple Lead Gains", "Tech Stocks Rally as Yields Slip"]
    assert headlines.ticker_rows("MSFT", now=NOW)["ask"] is None


def test_a_name_ibkr_does_not_know_is_said_so(gw):
    gw.unknown.add("ZZZZ")
    assert headlines.fetch_ticker("ZZZZ", now=NOW)["error"] == "IBKR does not know ZZZZ"


# ── F2: one freshness a lane, read from the store ─────────────────────────────────────────────────────────────────

def _head(hid, provider, tickers, fetched):
    return {"headline_id": hid, "provider": provider, "published_at": NOW, "headline": hid, "source": None,
            "tickers": json.dumps(tickers), "url": None, "fetched_at": fetched, "run_id": "t", "run_at": fetched}


def test_lane_freshness_reads_each_lane_on_its_own():
    assert headlines.lane_freshness() == {"market": None, "stocks": None, "x": None}
    rawstore.write_rows(headlines.TABLE, [
        _head("ibkr:m", "ibkr", [], NOW - 60), _head("ibkr:m2", "ibkr", [], NOW - 600),
        _head("ibkr:s", "ibkr", ["AAPL"], NOW - 90_000),
        _head("x:1", "grok-x", [], NOW - 300), _head("x:2", "x-follow", ["SPY"], NOW - 30),
    ])
    # The newest fetch a lane, not the newest of the table: an X row with a cashtag is still the X lane, and the
    # per-ticker lane stays a day old however busy the others are (review F2, 18 Nov 2026).
    assert headlines.lane_freshness() == {"market": NOW - 60, "stocks": NOW - 90_000, "x": NOW - 30}


def test_a_lane_mark_moves_only_on_a_clean_pass_and_says_nothing_before_one():
    """Review F2 / plan step 6: the alarm reads "the fetch last came back clean", not "a row was last written",
    so a lane with no news to bring does not look dead and a quiet night does not page."""
    assert headlines.lane_ok() == {"stocks": None, "x": None}
    headlines.mark_lane_ok("stocks", NOW)
    assert headlines.lane_ok() == {"stocks": NOW, "x": None}
    headlines.mark_lane_ok("stocks", NOW + 300)                 # the next clean pass, with or without a headline
    headlines.mark_lane_ok("x", NOW + 60)
    assert headlines.lane_ok() == {"stocks": NOW + 300, "x": NOW + 60}


def test_the_lane_cadences_come_from_the_jobs_own_schedules():
    """The limit the Grafana rule reads is not a number typed twice: it follows the pass that feeds the lane."""
    from RevenueChaser.module_news import tape, x_reader
    assert headlines.lane_late_after() == {"stocks": 6 * tape.TRIGGER_S, "x": 1.5 * x_reader.OFF_EVERY_S}
    assert set(headlines.lane_late_after()) == set(headlines.OK_LANES)
