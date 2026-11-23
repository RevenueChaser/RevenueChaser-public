"""Tests for the SEC Form 13F parser + dashboard."""
import re
from datetime import date

import pytest

from revenuechaser.module_sec_13f import engine as sf


class TestQuarterEnds:
    def test_the_quarters_start_in_2019(self):
        """#1442 (avo, 22 Nov 2026): the board goes back to 2019q1."""
        qs = sf.quarter_ends(today=date(2026, 8, 15))
        assert qs[:2] == ["2019-03-31", "2019-06-30"] and qs[-1] == "2026-06-30" and len(qs) == 30

    def test_early_year(self):
        assert sf.quarter_ends(start="2025-03-31", today=date(2025, 5, 1)) == ["2025-03-31"]


class TestReleaseSchedule:
    def test_two_quarters(self):
        sched = sf.release_schedule(n=2, today=date(2026, 8, 15))
        assert sched[0]["report_period"] == "2026 Q3"
        assert sched[0]["quarter_end"] == "2026-09-30"
        assert sched[0]["filing_due"] == "2026-11-14"
        assert sched[1]["quarter_end"] == "2026-12-31"


class TestNormalize:
    def test_period(self):
        assert sf.normalize_period("31-MAR-2026") == "2026-03-31"
        assert sf.normalize_period("2025-06-30") == "2025-06-30"
        assert sf.normalize_period("") is None
        assert sf.normalize_period("garbage") is None

class TestDashboard:
    def test_no_sector_chips_are_left(self):
        """KF (#375): the old sector chips are gone; the shared filter kit handles Sector."""
        from revenuechaser.module_sec_13f.report import render_sec13f_dashboard
        cell = {"shares": 100.0, "value": 1000.0, "holders": 2}
        totals = {t: {"2025-03-31": dict(cell), "2025-06-30": dict(cell, shares=120.0)} for t in ("AAA", "BBB")}
        meta = {"AAA": {"name": "A", "sector": "Technology"}, "BBB": {"name": "B", "sector": "Healthcare"}}
        h = render_sec13f_dashboard(totals, meta, {})
        assert 'filter-btn' not in h
        assert 'data-sector=' not in h
        assert 'setSector' not in h

    def test_the_filter_bar_mounts_with_the_four_facets(self):
        """KF (#375): Index, Market cap, Sector and Theme are present; Earnings is not."""
        from revenuechaser.module_sec_13f.report import render_sec13f_dashboard
        cell = {"shares": 100.0, "value": 1000.0, "holders": 2}
        totals = {"AAA": {"2025-03-31": dict(cell), "2025-06-30": dict(cell, shares=120.0)}}
        h = render_sec13f_dashboard(totals, {"AAA": {"name": "A"}}, {})
        assert '<section class="rcf-bar" id="rc-filters"></section>' in h
        assert 'var META = ' in h
        assert '"facets":["index","mc","gics","theme"]' in h.replace(' ', '')
        # The shared kit JS is inlined so the bar can mount client-side.
        assert 'RCFilters.mount' in h
        # Earnings facet is omitted.
        assert '"facets":["index","mc","gics","theme","earnings"]' not in h.replace(' ', '')

    def test_filter_rows_ride_the_payload_not_the_html(self):
        """KF (#375): the K1 rows are in the payload's ``fields`` key, not embedded in the page."""
        from revenuechaser.module_sec_13f.report import board_payload, render_sec13f_dashboard
        cell = {"shares": 100.0, "value": 1000.0, "holders": 2}
        totals = {"AAA": {"2025-03-31": dict(cell), "2025-06-30": dict(cell, shares=120.0)},
                  "BBB": {"2025-03-31": dict(cell), "2025-06-30": dict(cell, shares=120.0)}}
        h = render_sec13f_dashboard(totals, {"AAA": {"name": "A"}, "BBB": {"name": "B"}}, {})
        # The HTML never inlines a fields dict or a ticker field row.
        assert '"fields":' not in h or 'var FIELDS = {}' in h
        payload = board_payload(totals, {"AAA": {"name": "A"}, "BBB": {"name": "B"}}, {})
        assert "fields" in payload
        assert set(payload["fields"]) >= {"AAA", "BBB"}
        for f in payload["fields"].values():
            assert "ticker" in f and "name" in f

    def test_unknown_sectors_read_unclassified_in_the_rows(self):
        """R3 (#86): ``Other`` (stored before R3 / the vendor fallback) and ``Unclassified`` are one bucket."""
        from revenuechaser.module_sec_13f.report import board_payload, render_sec13f_dashboard
        cell = {"shares": 100.0, "value": 1000.0, "holders": 2}
        totals = {t: {"2025-03-31": dict(cell), "2025-06-30": dict(cell, shares=120.0)} for t in ("AAA", "BBB", "CCC")}
        meta = {"AAA": {"name": "A", "sector": "Other"}, "BBB": {"name": "B", "sector": "Unclassified"},
                "CCC": {"name": "C"}}                                               # no sector stored at all
        h = render_sec13f_dashboard(totals, meta, {})
        assert 'data-sector=' not in h
        rows = board_payload(totals, meta, {})["rows"]
        assert [r[2] for r in rows] == ["Unclassified", "Unclassified", "Unclassified"]

    def test_a_stored_gics_spelling_reads_as_its_morningstar_sector(self):
        """#266: a meta row stored before the rename (``Information Technology``, ``Health Care``, ``Financials``)
        gets the Morningstar row value; no row keeps the old spelling."""
        from revenuechaser.module_sec_13f.report import board_payload, render_sec13f_dashboard
        cell = {"shares": 100.0, "value": 1000.0, "holders": 2}
        totals = {t: {"2025-03-31": dict(cell), "2025-06-30": dict(cell, shares=120.0)} for t in ("AAA", "BBB", "CCC")}
        meta = {"AAA": {"name": "A", "sector": "Information Technology"},
                "BBB": {"name": "B", "sector": "Health Care"},
                "CCC": {"name": "C", "sector": "Financials"}}
        h = render_sec13f_dashboard(totals, meta, {})
        for old in ("Information Technology", "Health Care", "Financials"):
            assert f'data-sector="{old}"' not in h and f'data-val="{old}"' not in h
        rows = board_payload(totals, meta, {})["rows"]
        assert sorted(r[2] for r in rows) == ["Financial Services", "Healthcare", "Technology"]

    def test_an_asset_class_row_keeps_its_label(self):
        """Crypto / indices carry an asset class instead of a sector: shown on the row."""
        from revenuechaser.module_sec_13f.report import board_payload, render_sec13f_dashboard
        cell = {"shares": 100.0, "value": 1000.0, "holders": 2}
        totals = {"BTC": {"2025-03-31": dict(cell), "2025-06-30": dict(cell, shares=120.0)}}
        meta = {"BTC": {"name": "Bitcoin", "sector": "Crypto / Digital Assets"}}
        h = render_sec13f_dashboard(totals, meta, {})
        assert board_payload(totals, meta, {})["rows"][0][2] == "Crypto / Digital Assets"
        assert 'data-sector=' not in h

    def test_render_with_new_columns(self):
        from revenuechaser.module_sec_13f.report import board_payload, render_sec13f_dashboard
        totals = {"RKT": {"2025-03-31": {"shares": 100.0, "value": 1000.0, "holders": 2,
                                          "new_holders": None, "exited_holders": None,
                                          "top10_pct": 100.0, "hhi": 5000.0,
                                          "buy_flow": None, "sell_flow": None},
                          "2025-06-30": {"shares": 150.0, "value": 1500.0, "holders": 2,
                                          "new_holders": 1, "exited_holders": 1,
                                          "top10_pct": 90.0, "hhi": 4000.0,
                                          "buy_flow": 60.0, "sell_flow": 10.0}}}
        meta = {"RKT": {"name": "Rocket Companies Inc", "sector": "Financial Services"}}
        enrich = {"RKT": {"price": {"2025-03-31": 10.0, "2025-06-30": 12.0},
                          "shares_outstanding": 2000.0, "short_pct": 5.2, "insider_pct": 1.4}}
        h = render_sec13f_dashboard(totals, meta, enrich)
        assert "SEC 13F" in h
        assert "Value ($)" in h
        assert "% Out" in h
        assert "New/Exit" in h
        assert "Top10%" in h
        assert "Net flow" in h
        assert "Insider%" not in h                                   # hidden since #732 (owner, 12 Nov 2026)
        assert "RKT" not in h                                        # the row lives in the payload (#429)
        cells = dict(zip(board_payload(totals, meta, enrich)["cols"],
                         board_payload(totals, meta, enrich)["rows"][0][3]))
        assert "insider" not in cells
        assert [row[0] for row in board_payload(totals, meta, enrich)["rows"]] == ["RKT"]

    def test_render_suppresses_delta_for_missing_quarter(self):
        """A quarter with no SEC data must not produce a misleading QoQ delta."""
        from revenuechaser.module_sec_13f.report import board_payload, render_sec13f_dashboard
        totals = {"RKT": {
            "2026-03-31": {"shares": 100.0, "value": 1000.0, "holders": 5,
                           "new_holders": None, "exited_holders": None,
                           "top10_pct": 100.0, "hhi": 5000.0,
                           "buy_flow": None, "sell_flow": None},
            "2026-06-30": {"shares": 60.0, "value": 600.0, "holders": 3,
                           "new_holders": None, "exited_holders": None,
                           "top10_pct": 100.0, "hhi": 5000.0,
                           "buy_flow": None, "sell_flow": None},
        }}
        meta = {"RKT": {"name": "Rocket", "sector": "Financial Services"}}
        render_sec13f_dashboard(totals, meta, {})                    # renders without error
        payload = board_payload(totals, meta, {})
        cells = dict(zip(payload["cols"], payload["rows"][0][3]))
        # Full-SEC quarter keeps its Δ% vs prior quarter.
        assert cells["ch_2026-06-30"] == ["-40.0%", -40.0, "neg"]

    def test_render_shows_sec_to_sec_deltas(self):
        """Full-SEC consecutive quarters keep their QoQ metrics."""
        from revenuechaser.module_sec_13f.report import board_payload, render_sec13f_dashboard
        totals = {"RKT": {
            "2026-03-31": {"shares": 100.0, "value": 1000.0, "holders": 5,
                           "new_holders": None, "exited_holders": None,
                           "top10_pct": 100.0, "hhi": 5000.0,
                           "buy_flow": None, "sell_flow": None},
            "2026-06-30": {"shares": 150.0, "value": 1500.0, "holders": 6,
                           "new_holders": 2, "exited_holders": 1,
                           "top10_pct": 90.0, "hhi": 4000.0,
                           "buy_flow": 60.0, "sell_flow": 10.0},
        }}
        meta = {"RKT": {"name": "Rocket", "sector": "Financial Services"}}
        render_sec13f_dashboard(totals, meta, {})
        payload = board_payload(totals, meta, {})
        cells = dict(zip(payload["cols"], payload["rows"][0][3]))
        assert cells["ch_2026-06-30"] == ["+50.0%", 50.0, "pos"]
        assert cells["streak"] == ["1", 1, "zero"]
        assert cells["netflow"] == ["50", 50.0, "pos", "as of 2026 Q2"]
        assert cells["new_exit"] == ["+2/−1", 1, "zero", "as of 2026 Q2"]             # +2/−1


