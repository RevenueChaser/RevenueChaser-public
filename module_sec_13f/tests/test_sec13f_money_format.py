"""Plan step 6 (16 Nov 2026): a value of a trillion or more reads in T, not as thousands of B (NVDA "$3355.32B")."""
from revenuechaser.module_sec_13f import report


def test_trillions_read_in_t():
    assert report._fmt_money(3_355_320_000_000) == "$3.36T"
    assert report._fmt_money(999_990_000_000) == "$999.99B"
    assert report._fmt_money(None) == "—"


def test_the_board_says_why_insider_pct_is_off():
    """avo, 16 Nov 2026 (Q1): the Insider % column stays hidden and the board says why, in one line."""
    page = report.render_sec13f_dashboard({"AAA": {"2026-06-30": {"shares": 1.0, "value": 1.0, "holders": 1}}},
                                          {"AAA": {"name": "A", "sector": "Technology"}})
    assert "Insider % is off: Form 4 data does not give it reliably" in page
