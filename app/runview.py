"""The Runs tab (``/view/runs``, ``GET /api/runs``): the dashboard's own run log.

The log it read, ``job_runs``, lived in the old raw.duckdb and went with that file (#860), so the tab lists no runs
until a run log in the new store takes its place. The page and its route stay, so the tab opens and says so; the
builder's own runs are on the Settings Logs tab (``ops.job_runs2``).
"""
from __future__ import annotations

import logging

from markupsafe import Markup

from RevenueChaser.core import templating
from RevenueChaser.core.html_safe import script_json

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000
MAX_QUERY = 100
POLL_PATH = "/api/runs"


def clamp_limit(value) -> int:
    """How many rows to read: a bad or missing value falls back, a silly one is capped."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(n, MAX_LIMIT))


def clean_query(value) -> str:
    """The name filter as a bounded string; anything unusable is no filter at all."""
    return value.strip()[:MAX_QUERY] if isinstance(value, str) else ""


def read(limit=DEFAULT_LIMIT, problems: bool = False, query=None) -> dict:
    """What ``/api/runs`` returns: no rows, in the shape the page reads (see the module docstring)."""
    return {"rows": [], "total": 0, "shown": 0, "limit": clamp_limit(limit), "problems": bool(problems),
            "query": clean_query(query)}


def page_payload() -> dict:
    """What the Runs page is rendered from: the first page of rows, so the first view needs no poll."""
    return {"initial": read()}


def render_page(payload: dict) -> str:
    # script_json output is the one trusted fragment: Markup keeps autoescape from turning its quotes into
    # entities, which an inline <script> would not decode. Every value in it reaches the page as textContent.
    # The page-size control offers what ``clamp_limit`` accepts: the default page first, then the cap.
    return templating.render("runs.html.j2", limits=(DEFAULT_LIMIT, MAX_LIMIT),
                             initial_json=Markup(script_json(payload.get("initial") or {})))
