"""The old-ticker map read from the spine's ``security_history`` (K-E step 2, PR 1).

Compustat's ``tic`` periods (``source = 'wrds/sec_idhist'``) carry the current ticker of the linked security in
``ticker``, so a closed period whose ticker reads differently is an old symbol of that security. The rows here are
the live spine's own (measured 24 Nov 2026, plan ``2026-11-24_1735_revenuechaser_ticker-translation-plan``).
"""
from __future__ import annotations

from datetime import date

import duckdb

from revenuechaser.rcdata.build import ticker_history as th
from revenuechaser.rcdata.build.spine.security import HISTORY

D = date
SRC = "wrds/sec_idhist"
# (ticker, gvkey, iid, value, valid_from, valid_to): field 'tic', source SRC.
ROWS = [
    ("BNY", "002019", "01", "BK", D(1986, 12, 14), D(2026, 5, 21)),
    ("BNY", "002019", "01", "BNY", D(2026, 5, 21), None),
    (None, "002019", "04", "BKYKL", D(2012, 9, 17), D(2012, 9, 20)),      # unlinked iid: no current ticker
    ("IFLN", "178901", "01", "PHB", D(2007, 11, 15), D(2026, 2, 23)),
    ("SPYM", "165574", "01", "SPLG", D(2017, 10, 16), D(2025, 10, 31)),
    # Barrick: GOLD from 2019 to 2025, B since; Gold.com (A-Mark) took GOLD on 2025-12-02.
    ("B", "002055", "01", "ABX", D(1987, 3, 31), D(2019, 1, 2)),
    ("B", "002055", "01", "GOLD", D(2019, 1, 2), D(2025, 5, 9)),
    ("B", "002055", "01", "B", D(2025, 5, 9), None),
    ("GOLD", "019172", "01", "AMRK", D(2013, 11, 12), D(2025, 12, 2)),
    ("GOLD", "019172", "01", "GOLD", D(2025, 12, 2), None),
    # Teva: the ADR iid 90 (unlinked now) held TEVA until the listing moved to iid 03 on 2026-09-14.
    (None, "014538", "90", "TEVA", D(1999, 8, 23), D(2026, 9, 14)),
    (None, "014538", "90", "TEVA.1", D(2026, 9, 14), None),
    ("TEVA", "014538", "03", "TEVJF", D(2023, 10, 10), D(2026, 9, 14)),
    ("TEVA", "014538", "03", "TEVA", D(2026, 9, 14), None),
    # Noise: a numbered or .H suffix, a trailing dot, an iid ending C or W.
    ("NSE", "900001", "01", "OLD.1", D(2001, 1, 1), D(2002, 1, 1)),
    ("NSE", "900001", "01", "OLD.H", D(2002, 1, 1), D(2003, 1, 1)),
    ("NSE", "900001", "01", "OLD.", D(2003, 1, 1), D(2004, 1, 1)),
    ("NSE", "900001", "01C", "CAN", D(2004, 1, 1), D(2005, 1, 1)),
    ("NSE", "900001", "01W", "WAR", D(2004, 1, 1), D(2005, 1, 1)),
    ("NSE", "900001", "01", "NSE", D(2005, 1, 1), None),
    # Spelling: Compustat writes the class with a dot and may pad; BIO.A is BIO-A, ' bio ' is the ticker itself.
    ("BIO", "900002", "01", "BIO.A", D(1990, 1, 1), D(2000, 1, 1)),
    ("BIO", "900002", "01", " bio ", D(2000, 1, 1), D(2001, 1, 1)),
    # One old symbol on two current tickers at once: ambiguous, so neither period counts.
    ("AAA", "900003", "01", "XX", D(2010, 1, 1), D(2015, 1, 1)),
    ("BBB", "900004", "01", "XX", D(2014, 1, 1), D(2016, 1, 1)),
]
OTHER = [  # rows the map must not read: another field, another source
    ("ZZZ", "900005", "01", "cik", "OLDCIK", D(2000, 1, 1), D(2001, 1, 1), SRC),
    ("ZZZ", None, None, "tic", "OLDZ", D(2000, 1, 1), D(2001, 1, 1), "sec/company_tickers"),
]


def _con(rows=ROWS, other=OTHER) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE security_history (" + ", ".join(f"{c} {t}" for c, t in HISTORY) + ")")
    con.executemany("INSERT INTO security_history VALUES (?, NULL, ?, ?, 'tic', ?, ?, ?, ?)",
                    [r + (SRC,) for r in rows])
    con.executemany("INSERT INTO security_history VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)", other)
    return con


def _by_symbol() -> dict[str, list[th.Period]]:
    out: dict[str, list[th.Period]] = {}
    for p in th.periods(_con()):
        out.setdefault(p.symbol, []).append(p)
    return out


def test_renames_map_the_old_symbol_to_the_current_ticker():
    got = _by_symbol()
    assert got["BK"] == [th.Period("BK", D(1986, 12, 14), D(2026, 5, 21), "BNY", "002019", "01")]
    assert got["PHB"] == [th.Period("PHB", D(2007, 11, 15), D(2026, 2, 23), "IFLN", "178901", "01")]
    assert got["SPLG"] == [th.Period("SPLG", D(2017, 10, 16), D(2025, 10, 31), "SPYM", "165574", "01")]


def test_an_open_period_or_an_unlinked_iid_is_no_old_symbol():
    got = _by_symbol()
    assert "BNY" not in got and "BKYKL" not in got and "TEVA" not in got


def test_noise_rows_are_dropped():
    got = _by_symbol()
    assert not {"OLD-1", "OLD-H", "OLD-", "OLD", "CAN", "WAR"} & set(got)


def test_symbols_are_spelled_as_the_sec_writes_them():
    got = _by_symbol()
    assert [p.ticker for p in got["BIO-A"]] == ["BIO"]
    assert "BIO" not in got


def test_a_reused_ticker_is_credited_by_date():
    assert _by_symbol()["GOLD"] == [th.Period("GOLD", D(2019, 1, 2), D(2025, 5, 9), "B", "002055", "01")]
    got = th.starts(_con())
    assert got["GOLD"] == D(2025, 12, 2)
    assert got["B"] == D(2025, 5, 9)


def test_an_iid_move_keeps_the_ticker_continuous():
    assert th.starts(_con())["TEVA"] == D(1999, 8, 23)
    assert [p.symbol for p in th.periods(_con()) if p.ticker == "TEVA"] == ["TEVJF"]


def test_overlapping_periods_onto_two_tickers_give_nothing():
    assert "XX" not in _by_symbol()


def test_the_same_symbol_on_two_tickers_at_different_times_is_kept():
    rows = ROWS + [("GFI", "017947", "90", "GOLD", D(1999, 5, 10), D(2002, 5, 9))]
    got = [p.ticker for p in th.periods(_con(rows)) if p.symbol == "GOLD"]
    assert got == ["GFI", "B"]


def test_other_fields_and_sources_are_not_read():
    got = _by_symbol()
    assert "OLDCIK" not in got and "OLDZ" not in got
    assert "ZZZ" not in th.starts(_con())


def test_a_spine_without_history_gives_nothing():
    con = duckdb.connect(":memory:")
    assert th.periods(con) == [] and th.starts(con) == {}


def test_no_spine_file_gives_nothing():
    assert th.periods() == [] and th.starts() == {}
