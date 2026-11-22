"""The X lane after the Grok mails were removed (avo, 21 Nov 2026): one source, and no code left that reads them."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from revenuechaser.module_news import x_lane

_REPO = Path(__file__).resolve().parents[2]
#: The source trees a News row can be written or read from. Docs and this test are not source.
_SOURCE = ("module_news", "app", "core", "rcdata", "scripts")


def test_the_status_id_carries_its_own_time():
    """@kiantrades, 10 Nov 2026 21:24 Amsterdam: the id's snowflake, unchanged by the move out of x_feed."""
    at = x_lane.status_time(2120251362529419593)
    assert datetime.fromtimestamp(at, x_lane.AMS).strftime("%Y-%m-%d %H:%M") == "2026-11-10 21:24"


def test_rc_s_own_reader_is_the_lane_s_only_provider():
    """The Grok mail provider is gone, so no read may still ask for it."""
    assert x_lane.X_PROVIDERS == ("x-follow",)


def test_no_source_file_names_the_grok_mail_lane():
    """Its provider name and its mail folder, which the fetcher and the loader used to share."""
    here = Path(__file__).resolve()
    offenders = []
    for top in _SOURCE:
        for path in (_REPO / top).rglob("*.py"):
            if path.resolve() == here:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "grok-x" in text or "grok_x" in text:
                offenders.append(path.relative_to(_REPO).as_posix())
    assert not offenders, offenders


def test_the_grok_mail_fetcher_is_gone():
    assert not (_REPO / "module_news" / "x_feed.py").exists()
