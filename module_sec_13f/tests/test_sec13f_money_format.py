"""Plan step 6 (16 Nov 2026): a value of a trillion or more reads in T, not as thousands of B (NVDA "$3355.32B")."""
from RevenueChaser.module_sec_13f import report


def test_trillions_read_in_t():
    assert report._fmt_money(3_355_320_000_000) == "$3.36T"
    assert report._fmt_money(999_990_000_000) == "$999.99B"
    assert report._fmt_money(None) == "—"
