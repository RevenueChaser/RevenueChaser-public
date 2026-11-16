"""#788 A1/A4 (plan step 12): an investor type's sector exposure as small multiples on one shared scale, and its
dollars bought and sold as two stacked panels with the net, never a dual axis; both None before the tables exist."""
from __future__ import annotations

from RevenueChaser.module_sec_13f import report

Q1, Q2 = "2026-03-31", "2026-06-30"


def test_sector_panels_share_one_scale_and_sort_by_the_newest_quarter():
    rows = [{"period": q, "sector": s, "share": v} for q, s, v in
            [(Q1, "Technology", 30.0), (Q2, "Technology", 35.0), (Q1, "Energy", 5.0), (Q2, "Energy", 4.0)]]
    fig = report.build_sector_fig("All", rows)
    titles = [a["text"] for a in fig["layout"]["annotations"]]
    assert titles[:2] == ["Technology 35.0%", "Energy 4.0%"]
    ranges = {tuple(v["range"]) for k, v in fig["layout"].items() if k.startswith("yaxis") and v.get("range")}
    assert len(ranges) == 1                                        # one scale for every panel
    assert report.build_sector_fig("All", []) is None


def test_flow_panels_show_gross_and_net_without_a_second_axis():
    rows = [{"period": Q2, "bought": 8.10e9, "sold": 7.76e9, "net": 0.34e9}]
    fig = report.build_flow_fig("All", rows)
    by = {t["name"]: t for t in fig["data"]}
    assert by["Bought"]["y"] == [8.10e9] and by["Sold"]["y"] == [-7.76e9] and by["Net"]["y"] == [0.34e9]
    assert not any((v or {}).get("overlaying") for k, v in fig["layout"].items() if k.startswith("yaxis"))
    assert report.build_flow_fig("All", []) is None
