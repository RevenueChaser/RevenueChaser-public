"""B5 (DF100, #371): the index lists read UW through ``UWClient.get_result``, and a failed read is an error.

``_uw_get`` was a bare ``httpx.get`` with the import-time ``UW_API_KEY``: every exception was logged at debug
and answered ``[]``, with no retry, breaker, ``auth_error`` or health record. A rejected key therefore read as
"sp500 below floor (0 < 400)" in the weekly index-lists job, with no cause. Now ``_uw_get`` goes through the
client and raises ``IndexFetchError`` naming the failure, so the step's row says ``error (... HTTP 401 ...)``
and the stored list is kept, as before. Fake clients only; no request leaves the process.
"""
from __future__ import annotations

import ast
import inspect

import httpx
import pytest

from RevenueChaser.core import index_registry as ir
from RevenueChaser.core import rawstore
from RevenueChaser.core.providers.result import ProviderResult


class _FakeUW:
    """Stands in for ``UWClient``: answers ``get_result`` / ``etf_holdings_result`` from ``answers``."""

    def __init__(self, answers: dict, key: str = "k"):
        self.key = key
        self.answers = answers
        self.calls: list[tuple[str, dict | None]] = []
        self.closed = False

    @property
    def active(self) -> bool:
        return bool(self.key)

    def get_result(self, ep, params=None):
        self.calls.append((ep, params))
        return self.answers[ep]

    def etf_holdings_result(self, ticker):
        self.calls.append((f"/etfs/{ticker}/holdings", None))
        return self.answers[f"/etfs/{ticker}/holdings"]

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


SP = "/screener/stocks"
NQ = "/stock-directory/ticker-exchanges"
DIA = "/etfs/DIA/holdings"


def _ok(data, ep=""):
    return ProviderResult("ok", data, None, ep)


def _failed(status, ep=""):
    return ProviderResult("failed", {}, {"endpoint": ep, "status": status, "error": f"HTTP {status}",
                                         "attempts": 1}, ep)




def test_the_module_makes_no_bare_httpx_request():
    tree = ast.parse(inspect.getsource(ir))
    bare = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "get"
            and isinstance(n.value, ast.Name) and n.value.id == "httpx"]
    assert bare == []




















