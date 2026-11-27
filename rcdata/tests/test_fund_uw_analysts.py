"""``uw/screener_analysts``: how one UW answer becomes rows, and the order pass 2 asks in (#1588).

The rating rows themselves: a row with no key is skipped and counted, a price target parses UW's string forms or
stays NULL, and the pass-2 ticker set puts the **delisted** universe first -- avo's choice of 27 Nov 2026, and the
whole reason the export exists, because the delisted names are the rows no free source has.
"""
from __future__ import annotations

from datetime import date, datetime

from revenuechaser.rcdata.build.fundamentals import uw_analysts as ua

STAMPS = {"source_as_of": date(2026, 11, 27), "fetched_at": 1.0, "run_id": "t"}
ROW = {"ticker": "MSFT", "timestamp": "2023-09-11T11:21:12Z", "action": "maintained", "recommendation": "buy",
       "target": "420.0", "analyst_name": "Tyler Radke", "firm": "Citi", "sector": "Technology"}


def test_one_answer_becomes_one_row_per_rating_event():
    rows, counts = ua.table_rows({"data": [ROW]}, STAMPS)
    assert counts == {}
    assert rows == [{"ticker": "MSFT", "published_at": datetime(2023, 9, 11, 11, 21, 12), "action": "maintained",
                     "recommendation": "buy", "target": 420.0, "analyst_name": "Tyler Radke", "firm": "Citi",
                     "sector": "Technology", "source": ua.NAME, **STAMPS}]


def test_a_bare_list_body_and_a_wrapped_one_read_the_same():
    assert ua.table_rows([ROW], STAMPS)[0] == ua.table_rows({"data": [ROW]}, STAMPS)[0]
    assert ua.table_rows({"data": None}, STAMPS) == ([], {})


def test_a_row_with_no_timestamp_or_no_ticker_is_skipped_and_counted():
    """Both are the row's key: without either it cannot be told from another rating of the same analyst."""
    rows, counts = ua.table_rows({"data": [ROW, {**ROW, "timestamp": None}, {**ROW, "timestamp": "not a date"},
                                           {**ROW, "ticker": "  "}, "junk"]}, STAMPS)
    assert len(rows) == 1
    assert counts == {"no_timestamp": 2, "no_ticker": 1, "not_a_row": 1}


def test_a_price_target_parses_uws_string_forms_and_never_becomes_zero():
    assert [ua._num(v) for v in ("266.0000", "220", "1,250.5", 11, "0")] == [266.0, 220.0, 1250.5, 11.0, 0.0]
    assert all(ua._num(v) is None for v in (None, "", "-", "null", "n/a", True))


def test_a_timestamp_is_kept_as_utc():
    assert ua._stamp("2023-09-11T11:21:12Z") == datetime(2023, 9, 11, 11, 21, 12)
    assert ua._stamp("2023-09-11T13:21:12+02:00") == datetime(2023, 9, 11, 11, 21, 12)
    assert ua._stamp("") is None and ua._stamp(None) is None


def test_the_cursor_of_a_page_is_its_oldest_row():
    page = [{"timestamp": "2024-05-02T10:00:00Z"}, {"timestamp": "2024-05-01T09:00:00Z"},
            {"timestamp": "2024-05-03T11:00:00Z"}, {"timestamp": None}]
    assert ua.oldest_stamp(page) == "2024-05-01T09:00:00Z"
    assert ua.oldest_stamp([{"timestamp": None}]) is None and ua.oldest_stamp([]) is None


def test_the_floor_is_the_tokens_own_earliest_day():
    """An explicit ``older_than`` before 2023-12-28 is refused by UW itself, so pass 1 stops at it."""
    assert ua.FLOOR == date(2023, 12, 28)
    assert ua.below_floor("2023-12-28T23:59:00Z") is True
    assert ua.below_floor("2023-06-01T00:00:00Z") is True
    assert ua.below_floor("2023-12-29T00:00:00Z") is False
    assert ua.below_floor(None) is False


def test_pass_two_asks_the_delisted_names_first(monkeypatch):
    """avo, 27 Nov 2026 (option A): delisted first, then what the feed saw, then the live universe -- each once."""
    monkeypatch.setattr(ua, "delisted_tickers", lambda: ["ATVI", "FRC", "SGEN"])
    monkeypatch.setattr(ua, "live_tickers", lambda: ["AAPL", "ACN", "MSFT"])
    assert ua.ticker_order(["MSFT", "TSM", "FRC"]) == ["ATVI", "FRC", "SGEN", "MSFT", "TSM", "AAPL", "ACN"]


def test_only_the_securities_delisted_inside_the_archive_are_asked(monkeypatch):
    """UW's archive starts in January 2023 (measured: the oldest row of 8 probe tickers was 3 Jan 2023), so a
    security that stopped trading before it has no row to fetch. Asking all 29,833 delisted securities would be
    tens of thousands of calls for nothing."""
    from revenuechaser.rcdata import read
    seen = {}

    def securities(security_ids=None, delisted_from=None, delisted_to=None):
        seen["from"] = delisted_from
        return [{"security_id": "permno:1"}, {"security_id": "permno:2"}]

    monkeypatch.setattr(read, "delisted_securities", securities)
    monkeypatch.setattr(read, "delisted_symbols",
                        lambda security_ids=None, symbols=None: [{"symbol": "FRC"}, {"symbol": " "},
                                                                 {"symbol": "SIVB"}])
    assert ua.delisted_tickers() == ["FRC", "SIVB"]
    assert seen["from"] == ua.ARCHIVE_START == date(2022, 12, 1)


def test_a_missing_delisted_file_is_no_delisted_names(monkeypatch):
    from revenuechaser.rcdata import read
    monkeypatch.setattr(read, "delisted_securities", lambda **kw: (_ for _ in ()).throw(FileNotFoundError("none")))
    assert ua.delisted_tickers() == []


def test_the_dataset_serves_no_table_and_ends_with_the_subscription():
    """It is a one-off archive: nothing reads it yet, and after 6 Dec 2026 it is never due again."""
    from revenuechaser.rcdata.build import due
    assert ua.DATASET.tables == () and ua.DATASET.feeds == () and ua.DATASET.starts_by_hand is True
    assert due.SOURCE_ENDS[ua.NAME] == date(2026, 12, 6)
