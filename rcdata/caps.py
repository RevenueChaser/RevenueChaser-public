"""Provider limits, as the providers publish them (master plan Order 5, rule 3). Each number names its source.

``DAY_CAPS``: the quotas published per day. The builder refuses to start a dataset whose provider has reached its cap
for the New York day; the counter is ``ops.provider_calls_daily``, which holds **both** halves of what this machine
spends: every HTTP request the builder sends, retries included, and since #166 the dashboard's own Fetches, through
``core/providers/spend.py``. Its unit per provider is that provider's unit in both halves -- requests for ``uw`` and
``sec``, Yahoo reads for ``yfinance`` -- and no row says which half it came from: the cap is the account's, so what
the cap wants to know is the total. A gate on the app side is a separate decision and does not exist (#166 item 5).

``WINDOWS``: the published request windows, ``(requests, seconds)``, enforced by ``base.Pacer`` (``base.run_pacer``).
A provider with no published limit (FRED, WRDS, the fund-file hosts, Nasdaq Trader, the NYSE threshold file, IBKR's
short-stock file) is in neither table: no number is invented for it. A pacer some of them keep is politeness, not a
provider limit, and is labelled so where it is set.
"""
from __future__ import annotations

from . import ops

# Yahoo (yfinance) has no window: Yahoo publishes none and the owner removed ours (avo 2026-11-23, #1473).
# UW has no day cap: the owner removed it (avo 2026-11-10, "UW icin sinir koyma, siniri tamamen kaldir").
DAY_CAPS: dict[str, int] = {
    # shared by the earnings calendar (one a run) and the spine's listing status (two a run, #346)
    "alphavantage": 25,  # free tier requests a day: https://www.alphavantage.co/support/#api-key
}

WINDOWS: dict[str, tuple[int, float]] = {
    # per User-Agent, both hosts
    "sec": (10, 1.0),  # https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
    "alpaca": (200, 60.0),  # Basic plan historical calls: https://docs.alpaca.markets/us/docs/about-market-data-api
    "openfigi": (250, 60.0),  # /v3/mapping with a key: https://www.openfigi.com/api/documentation
    "openfigi_search": (20, 60.0),  # /v3/search with a key (no caller yet): https://www.openfigi.com/api/documentation
    "finra": (1_200, 60.0),  # synchronous, per IP: https://developer.finra.org/docs
}


def cap_for(provider: str) -> int | None:
    return DAY_CAPS.get(provider)


def at_cap(provider: str) -> tuple[bool, int, int | None]:
    """``(refused, calls today, cap)``; ``refused`` is True once today's calls reached the cap."""
    cap = cap_for(provider)
    used = ops.calls_today(provider)
    return (cap is not None and used >= cap), used, cap
