"""What the News board's X lane shares: who its providers are, the status-id clock and the text cap.

The lane had two sources until 21 Nov 2026: avo's Grok "X saatlik özet" mails (provider ``grok-x``, fetched by
``module_news/x_feed.py``) and RC's own reader (``x_reader.py``, provider ``x-follow``). avo asked for everything
Grok to go (21 Nov 2026 10:05 Amsterdam, "Evet hakkındaki alakali herseyi sil", scope "only the Grok mails"), so the
mail half and its rows were removed and RC's own reader is the lane's one source. These few values stayed shared
because ``x_reader``, ``x_check``, ``store_reads`` and ``report`` all read them and must not disagree.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

AMS = ZoneInfo("Europe/Amsterdam")
#: RC's own X reader (``x_reader.py``): the Following timeline of RC's X account, the X lane's one source.
PROVIDER = "x-follow"
#: Every provider whose rows are the X lane. A tuple, as the reads that cut the lane take one parameter per name.
X_PROVIDERS = (PROVIDER,)
TEXT_MAX = 280
_TWEPOCH_MS = 1288834974657


def status_time(status_id: int) -> float:
    """The creation time (epoch seconds) an X status id carries (snowflake), exact to the millisecond."""
    return ((int(status_id) >> 22) + _TWEPOCH_MS) / 1000.0


def published_local(row: dict) -> str:
    """The row's time as ``YYYY-MM-DD HH:MM`` in Amsterdam (for the board and for checks)."""
    return datetime.fromtimestamp(row["published_at"], timezone.utc).astimezone(AMS).strftime("%Y-%m-%d %H:%M")
