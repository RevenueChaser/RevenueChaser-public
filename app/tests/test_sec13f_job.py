"""The 13F Fetch after G9: names -> shares out -> render -> history (#206, G9).

The numbers are the builder's (``ownership.duckdb``), so the Fetch asks the SEC for nothing. What is left here:

* the Unusual Whales meta step is best-effort — a missing key or an outage keeps the stored names/sectors and says
  so on the board;
* a meta that already covers the served totals: the UW screener is not re-run (F-1);
* the client the runner opens itself is always closed;
* the CUSIPs the newest stored quarter could not name are a board note (DF89), now counted by the builder.
"""
import gzip
import json

import pytest

from RevenueChaser.app import jobs, runners
from RevenueChaser.module_sec_13f import engine as sec_13f
from RevenueChaser.rcdata.tests.ownership_fixture import serve_13f

GOOD = {"name": "Apple Inc", "sector": "Technology", "type": "Stock"}
Q = "2026-03-31"
AAPL = {"AAPL": {Q: {"shares": 300.0, "value": 3000.0, "holders": 2, "top10_pct": 100.0, "hhi": 5000.0,
                     "new_holders": None, "exited_holders": None, "buy_flow": None, "sell_flow": None,
                     "breadth": None, "breadth_chg": None}}}




def _serve(totals=None, *, cusips=None, **kw):
    """The builder's served tables, as a finished build leaves them."""
    totals = AAPL if totals is None else totals
    serve_13f(totals, cusips=cusips if cusips is not None else {"AAPL": ["111111111"]}, **kw)
    runners.SEC_13F_LATEST.unlink(missing_ok=True)


@pytest.fixture
def store(rawstore_tmp_db):
    """The dashboard's own store, empty, beside a served ownership file holding one name."""
    _serve()
    return rawstore_tmp_db


class _FakeUW:
    """A UW client double: counts constructions and what the screener was asked."""
    built = 0
    closed = 0
    ok = (True, None)
    health_ = None

    def __init__(self, *a, **k):
        type(self).built += 1

    def verify(self):
        return type(self).ok

    def screener_batch(self, tickers):
        return {}

    def health(self):
        return type(self).health_

    def close(self):
        type(self).closed += 1


@pytest.fixture
def fake_uw(monkeypatch):
    _FakeUW.built, _FakeUW.closed, _FakeUW.ok, _FakeUW.health_ = 0, 0, (True, None), None
    monkeypatch.setattr(runners, "UWClient", _FakeUW)
    return _FakeUW


def _board() -> str:
    return runners.SEC_13F_LATEST.read_text(encoding="utf-8")


def _payload() -> dict:
    """The board's rows from the payload route (#429): the page is chrome and scripts now."""
    from RevenueChaser.core.reporting_common import payload_path
    return json.loads(gzip.decompress(payload_path(runners.SEC_13F_LATEST).read_bytes()).decode("utf-8"))


def _tickers() -> set:
    return {row[0] for row in _payload()["rows"]}




class TestOwnUwClientIsClosed:
    """N1: the client the runner opens itself is always closed."""




    def test_a_client_passed_in_is_not_closed(self, store, fake_uw):
        runners.build_sec13f(fake_uw())
        assert fake_uw.closed == 0




