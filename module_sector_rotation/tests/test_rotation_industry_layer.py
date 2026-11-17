"""The industry-group layer (avo, 17 Nov 2026: "Endüstri gruplarının ETF'leri var mı? ... bunları da ekleyelim
endüstri katmanlarına").

``core/rotation_reference.INDUSTRY_GROUPS`` holds the 25 GICS industry groups, the same codes and names the spine
classifies a company by, with the ETFs that stand for each. The first ETF of a group is on the map's ``industry``
layer, whatever its own group: SMH stays a theme row and is also the semiconductor group's dot.
"""
from __future__ import annotations

import json
from datetime import date

from RevenueChaser.core.gics_map import MORNINGSTAR_SECTORS
from RevenueChaser.core.rotation_reference import INDUSTRY_GROUPS, INDUSTRY_MAP_ETFS, ROTATION_ETFS, SECTOR_ETF
from RevenueChaser.core.tests.board_js import run_board_js
from RevenueChaser.module_sector_rotation.models import ETFRotationSnapshot
from RevenueChaser.rcdata.build.spine.security import GICS_GROUPS, GICS_SECTORS, sector_names


def test_the_layer_is_the_spines_25_gics_groups_under_their_own_sectors():
    assert [c for c, *_ in INDUSTRY_GROUPS] == sorted(GICS_GROUPS)
    for code, group, sector, _etfs in INDUSTRY_GROUPS:
        assert sector_names(code[:2], code) == (sector, group), code
    assert {s for *_x, s, _e in INDUSTRY_GROUPS} == set(MORNINGSTAR_SECTORS)
    assert len(GICS_SECTORS) == len(SECTOR_ETF) == 11


def test_each_map_etf_is_a_rotation_row_and_an_etf_is_in_one_group_only():
    assert INDUSTRY_MAP_ETFS and all(t in ROTATION_ETFS for t in INDUSTRY_MAP_ETFS)
    every = [t for *_x, etfs in INDUSTRY_GROUPS for t in etfs]
    assert len(every) == len(set(every))
    assert {info["group"] for t, info in ROTATION_ETFS.items() if t in INDUSTRY_MAP_ETFS} <= {
        "sector", "theme", "industry"}
    assert all(t in INDUSTRY_MAP_ETFS for t, info in ROTATION_ETFS.items() if info["group"] == "industry")


def test_a_one_group_sector_is_its_own_spdr():
    firsts = {g: etfs[0] for _c, g, _s, etfs in INDUSTRY_GROUPS if etfs}
    assert (firsts["Energy"], firsts["Materials"], firsts["Utilities"]) == ("XLE", "XLB", "XLU")


def _snap(ticker, group):
    return ETFRotationSnapshot(as_of_date=date(2026, 11, 13), ticker=ticker, group_name=group, close_price=100.0,
                               rs_1w=1.0, rs_1m=2.0, rs_3m=3.0, rs_ratio=101.0, rs_momentum=100.5,
                               rs_ratio_z=1.0, rs_momentum_z=0.5, rrg_quadrant="LEADING")


def test_the_industry_filter_shows_the_layer_whatever_each_etfs_own_group(tmp_path, monkeypatch, rawstore_tmp_db):
    import RevenueChaser.module_sector_rotation.report as rd
    monkeypatch.setattr(rd, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(rd, "coarse_theme_catalog", lambda: {})
    html = rd.export_rotation_dashboard([_snap("XLK", "sector"), _snap("XLE", "sector"), _snap("SMH", "theme"),
                                         _snap("KBE", "industry"), _snap("XBI", "theme")],
                                        filename="ind.html", uw=None).read_text(encoding="utf-8")
    assert 'data-group="industry"' in html                             # the layer's filter button
    tail = """
var out = {};
['sector', 'industry', 'theme'].forEach(function(g){
  ACTIVE_GROUP = g;
  out[g] = RRG.etfs.filter(rrgVisible).map(function(e){ return e.ticker; }).sort();
});
console.log(JSON.stringify(out));
"""
    seen = json.loads(run_board_js(html, tail, tmp_path))
    assert seen["sector"] == ["XLE", "XLK"]
    assert seen["industry"] == ["KBE", "SMH", "XLE"]                   # XLK and XBI stand for no group on the map
    assert seen["theme"] == ["SMH", "XBI"]
