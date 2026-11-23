"""What the prices store (PR 7) adds to the shared parts: the ``prices`` serving kind, the two Alpaca credential
names (names only: a value is never read here) and the yfinance day cap."""
from __future__ import annotations

from revenuechaser.core import credentials
from revenuechaser.rcdata import caps, serving


def test_prices_is_a_serving_kind_of_version_1():
    assert serving.SERVING_SCHEMA_VERSION["prices"] == 1
    assert "prices" in serving.KINDS
    assert serving.live_path("prices").name == "prices.duckdb"


def test_the_alpaca_key_id_and_secret_are_two_declared_names():
    assert credentials.get("alpaca").env_var == "ALPACA_API_KEY_ID"
    assert credentials.get("alpaca_secret").env_var == "ALPACA_API_SECRET_KEY"
    assert "ALPACA_API_KEY_ID" in credentials.missing_message("alpaca")


def test_yfinance_has_no_limit_and_alpaca_a_window_not_a_day_cap():
    # avo 23 Nov 2026 (#1473): no rate limit of ours on Yahoo
    assert caps.cap_for("yfinance") is None and "yfinance" not in caps.WINDOWS
    assert caps.cap_for("alpaca") is None and caps.WINDOWS["alpaca"] == (200, 60.0)
