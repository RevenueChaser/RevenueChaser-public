"""Every board must report the date its data is computed against.

Regression: the Swing board read "Last run: 2026-09-02 09:51:27" over bars that
stopped at 2026-08-31. ``generated_at`` is only when the scan executed — and the
dashboard's self-healing view re-runs a module with ``no_fetch=True``, which
touches no network, so a cached re-render stamps "now" over week-old data.

The label must therefore come from the DATA, not the run, and it must exist for
every tab rather than the ones someone remembered to wire up.
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.core import provenance, rawstore


class TestResolvers:
    def test_swing_and_fundamentals_report_the_newest_bar(self, rawstore_tmp_db):
        """Their own names' newest D01 bar since K7 (#383 R3; ``test_provenance_k7_383.py``)."""
        from revenuechaser.core.tests.d01_seed import seed_d01
        assert provenance.data_as_of("module_swing_potential") is None
        seed_d01("AAPL", ["2026-08-28", "2026-08-31"], 1.0)
        seed_d01("MSFT", ["2026-08-27", "2026-08-28"], 1.0)
        rawstore.replace_all("swing_scores", [{"ticker": "AAPL"}, {"ticker": "MSFT"}])
        rawstore.replace_all("fundamentals_scores", [{"ticker": "MSFT"}])
        assert provenance.data_as_of("module_swing_potential") == "2026-08-31"
        assert provenance.data_as_of("module_fundamentals") == "2026-08-28"

    # An Earnings Fetch run Thursday 27 Aug 2026 after the close (18:00 New York).
    EARNINGS_RUN_AT = 1787868000.0





    def test_rotation_uses_the_newest_snapshot_date(self, rawstore_tmp_db):
        rawstore.write_rows("rotation_snapshots", [
            {"as_of_date": "2026-09-01", "ticker": "XLK", "group": "sector"},
            {"as_of_date": "2026-08-14", "ticker": "XLF", "group": "sector"},
        ])
        assert provenance.data_as_of("module_sector_rotation") == "2026-09-01"



    def test_leaps_is_the_newest_far_contract_session_not_the_old_tables(self, rawstore_tmp_db, monkeypatch):
        """#746: the chip reads the table the board reads; the old scan's two tables are gone."""
        from datetime import date
        from revenuechaser.rcdata import read
        monkeypatch.setattr(read, "far_contract_sessions", lambda: [])
        assert provenance.data_as_of("module_leaps") is None
        monkeypatch.setattr(read, "far_contract_sessions", lambda: [{"session_date": date(2026, 11, 13)},
                                                                   {"session_date": date(2026, 11, 12)}])
        assert provenance.data_as_of("module_leaps") == "2026-11-13"


    def test_an_unknown_module_reports_nothing(self, rawstore_tmp_db):
        assert provenance.data_as_of("module_does_not_exist") is None

    def test_a_broken_resolver_never_breaks_the_board(self, rawstore_tmp_db, monkeypatch):
        monkeypatch.setitem(provenance.RESOLVERS, "module_swing_potential",
                            lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert provenance.data_as_of("module_swing_potential") is None


class TestTheLabelIsAboutDataNotTheRun:
    def test_data_date_is_independent_of_when_the_scan_ran(self, rawstore_tmp_db):
        """The exact bug: a scan run today over bars from days ago."""
        from revenuechaser.core.tests.d01_seed import seed_d01
        seed_d01("AAPL", ["2026-08-28", "2026-08-31"], 1.0)
        rawstore.replace_all("swing_scores", [{"ticker": "AAPL"}])
        from revenuechaser.module_swing_potential.pipeline import build_payload
        p = build_payload([], run_stats={"data_as_of": provenance.data_as_of("module_swing_potential")})
        assert p["data_as_of"] == "2026-08-31"
        assert p["generated_at"][:10] != p["data_as_of"], (
            "generated_at is the run time; it must not be mistaken for the data date")

    def test_no_internal_jargon_reaches_the_payload(self, rawstore_tmp_db):
        from revenuechaser.module_swing_potential.pipeline import build_payload
        p = build_payload([], run_stats={})
        assert "model_only" not in p, "no_fetch is an implementation detail, not a UI field"


class TestApi:
    def _client(self):
        from revenuechaser.app import dashboard
        return dashboard.app.test_client()

    def test_endpoint_returns_the_data_date(self, rawstore_tmp_db):
        from revenuechaser.core.tests.d01_seed import seed_d01
        seed_d01("AAPL", ["2026-08-28", "2026-08-31"], 1.0)
        rawstore.replace_all("swing_scores", [{"ticker": "AAPL"}])
        d = self._client().get("/api/data_asof/module_swing_potential").get_json()
        assert d == {"module": "module_swing_potential", "data_as_of": "2026-08-31", "last_run": None}

    def test_endpoint_is_lenient_for_an_empty_store(self, rawstore_tmp_db):
        d = self._client().get("/api/data_asof/module_sec_13f").get_json()
        assert d["data_as_of"] is None

    def test_endpoint_never_500s_on_a_bogus_module(self, rawstore_tmp_db):
        r = self._client().get("/api/data_asof/../../etc/passwd")
        assert r.status_code in (200, 404)


def test_settings_header_names_the_prices_session_and_the_builders_last_run(monkeypatch):
    """avo, 10 Nov 2026 ("su bolumlerde dogru gelmeli"): Settings read "Data: n/a · Last run: —"."""
    from revenuechaser.rcdata import ops
    monkeypatch.setitem(provenance.RESOLVERS, "module_settings", lambda: "2026-11-09")
    monkeypatch.setattr(ops, "last_builder_run", lambda: {"started_at": 1762804800.0})
    from revenuechaser.app import dashboard
    r = dashboard.app.test_client().get("/api/data_asof/module_settings").get_json()
    assert r["data_as_of"] == "2026-11-09" and r["last_run"] == "2025-11-10T20:00:00+00:00"
    assert provenance.last_run("module_swing_potential") is None
    monkeypatch.setattr(ops, "last_builder_run", lambda: None)
    assert provenance.last_run("module_settings") is None


def test_settings_reads_the_universe_prices_close():
    assert provenance.RESOLVERS["module_settings"] is provenance._comovement_day


def test_every_dashboard_tab_declares_a_data_date():
    """Gate: a new board must say what its data date is — even if the answer is
    'none'. Otherwise it silently shows a blank while looking authoritative."""
    from revenuechaser.app import dashboard
    tabs = {t["key"] for t in dashboard.TABS if t.get("type") == "tab"}
    undeclared = sorted(tabs - set(provenance.RESOLVERS))
    assert not undeclared, (
        f"tabs missing from core/provenance.RESOLVERS: {undeclared} — add a resolver, "
        f"or map to None if the board holds no downloaded data")


def test_the_template_asks_for_the_data_date_on_every_tab():
    """The label is wired once in showTab, not per board."""
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent.parent / "templates" / "dashboard.html"
            ).read_text(encoding="utf-8")
    assert 'id="data-label"' in html
    assert "checkDataAsOf(key);" in html, "showTab must request it for whichever tab opened"
    assert "model-only" not in html, "internal jargon must not reach the UI"


def test_template_edits_do_not_need_a_server_restart():
    """debug=False makes Jinja cache the compiled template for the process
    lifetime, so a dashboard.html fix silently does not appear until restart —
    which is exactly why the first 'Last run' fix looked like it had not landed."""
    from revenuechaser.app.dashboard import app
    assert app.jinja_env.auto_reload is True


class TestSessionOf:
    """#283: one helper maps mixed time columns (epoch, ISO text, date) to a session date."""

    def test_maps_each_column_type_to_the_ny_session(self):
        from datetime import datetime, timezone
        sat = datetime(2026, 7, 18, 15, 0, tzinfo=timezone.utc).timestamp()
        assert provenance.session_of(sat) == "2026-07-17"
        assert provenance.session_of("2026-07-18T11:00:00-04:00") == "2026-07-17"
        assert provenance.session_of("2026-07-15") == "2026-07-15"

    def test_never_raises(self):
        assert provenance.session_of(None) is None
        assert provenance.session_of("garbage") is None
        assert provenance.session_of(1e18) is None
