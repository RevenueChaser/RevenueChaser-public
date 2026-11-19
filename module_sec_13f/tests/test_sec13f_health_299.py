"""#299: the 13F board's SEC EDGAR banner comes from the builder's newest check of each 13F source, so a failed
SEC fetch shows on the board instead of the banner being dead code."""
from __future__ import annotations

from RevenueChaser.app import runners
from RevenueChaser.core.reporting_common import provider_health_html
from RevenueChaser.rcdata import ops


def _checks(monkeypatch, rows):
    monkeypatch.setattr(ops, "read_latest_check", lambda ds: rows.get(ds))


def test_a_failed_13f_fetch_raises_the_banner(monkeypatch):
    _checks(monkeypatch, {"sec/13f": {"result": "failed", "checked_on": "2026-11-17", "note": "HTTP 503"},
                          "sec/13f_sets_listed": {"result": "unchanged", "checked_on": "2026-11-17"}})
    health = runners._sec13f_health()
    assert (health["provider"], health["calls"], health["failed"]) == ("SEC EDGAR", 2, 1)
    banner = provider_health_html(health)
    assert "2 SEC EDGAR çağrısının 1 tanesi başarısız" in banner
    assert "sec/13f: 2026-11-17: HTTP 503" in banner


def test_clean_or_unread_checks_raise_nothing(monkeypatch):
    _checks(monkeypatch, {"sec/13f": {"result": "changed", "checked_on": "2026-11-17"}})
    assert provider_health_html(runners._sec13f_health()) == ""

    def boom(ds):
        raise OSError("no ops state")
    monkeypatch.setattr(ops, "read_latest_check", boom)
    assert runners._sec13f_health() is None
