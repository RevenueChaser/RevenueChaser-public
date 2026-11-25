"""#446 steps 3 and 4: ``prices`` builds on a copy of the live file and reloads only what changed.

The main proof is metamorphic, as for ``fundamentals`` (``test_fund_incremental``): whatever changed in Parquet or in
the spine, the build on the live copy must serve exactly what a whole build of the same tree serves, table by table
and view by view, and leave the same build issues open (``_same_as_whole``). The one table it does not rebuild is the
WRDS difference report, which a build on the live copy keeps as it was (``incremental.KEPT``).

The fixture is ``test_prices_wrds``'s, through ``prices_incremental_world`` (#1153): AAPL (``001690:01``) with a
2-for-1 split ex 4 Jun 2025 and Compustat bars to 27 Oct 2026, a delisted OLDCO (``099999:01``, 2024) the spine does
not hold, Alpaca's bars and a dividend in October. The share classes, the aliases and the forced whole builds are
``test_prices_incremental_classes.py``.
"""

from __future__ import annotations

from datetime import date

import pytest

from revenuechaser.rcdata import serving
from revenuechaser.rcdata.build import base, dirty
from revenuechaser.rcdata.build.prices import stage, wrds_history
from revenuechaser.rcdata.build.prices import serving as prices_serving

from .prices_incremental_world import (
    AAPL, OLDCO, SPINE, _aapl_day, _clock, _note, _q, _report, _respine, _same_as_whole, _secd_rows, _serve,
    _snapshot, _write_secd, env, fake, live
)  # noqa: F401 (the shared world: its helpers, and every fixture a test's own fixtures ask for -- `env` is
#  autouse and runs only where it is in the namespace, `fake` is what `live` is built on)


def _shrunk_build(where: str):
    """A build connection whose ``price_bar_daily`` is the live file's without the rows ``where`` names."""
    import duckdb
    con = duckdb.connect()
    con.execute(f"ATTACH '{serving.live_path('prices')}' AS l (READ_ONLY)")
    con.execute(f"CREATE TABLE price_bar_daily AS SELECT * FROM l.price_bar_daily WHERE NOT ({where})")
    con.execute("DETACH l")
    con.execute("CREATE TABLE _gvkey_alias (gid TEXT, security_id TEXT)")
    con.execute("CREATE TABLE stg_spine (security_id TEXT, cik TEXT, ticker TEXT)")      # the re-key rule reads it
    return con


GONE = "099000:01"
JOINED = "099001:01"


def test_nothing_changed_serves_the_same_file(live, monkeypatch):
    before = _snapshot()
    report = _report()
    row = _serve()
    assert "0 Parquet file(s) changed" in _note(row), _note(row)
    assert _snapshot() == before and _report() == report
    _same_as_whole(monkeypatch, row)


def test_a_new_compustat_day_is_added(live, monkeypatch):
    day = date(2026, 10, 28)
    _write_secd(2026, _secd_rows(2026) + [_aapl_day(day, 203.0)])
    _clock(day)
    row = _serve()
    assert [r["close"] for r in _q("SELECT close FROM price_bar_daily WHERE security_id = ? AND session_date = ?",
                                   [AAPL, day])] == [203.0]
    assert "rebuilt from 2026-" in _note(row) and "0 securities whole" in _note(row), _note(row)
    _same_as_whole(monkeypatch, row)


def test_a_split_that_goes_ex_today_restates_the_factors_and_the_caps(live, monkeypatch):
    day = date(2026, 10, 28)
    rows = [{**r, "ajexdi": 2.0} if r["gvkey"] == "001690" else r for r in _secd_rows(2026)]
    _write_secd(2026, rows + [_aapl_day(day, 101.0, ajexdi=1.0, cshoc=30e9)])
    _clock(day)
    row = _serve()
    assert _q("SELECT 1 FROM corporate_action WHERE security_id = ? AND ex_date = ? AND action = 'split'",
              [AAPL, day])
    _same_as_whole(monkeypatch, row)


def test_an_older_year_rewritten_by_a_refresh_is_reloaded(live, monkeypatch):
    rows = _secd_rows(2025)
    rows = [{**r, "prccd": r["prccd"] + 1.0} if r["datadate"] == date(2025, 6, 3) else r for r in rows]
    _write_secd(2025, rows)
    row = _serve()
    assert _q("SELECT close FROM price_bar_daily WHERE security_id = ? AND session_date = '2025-06-03'",
              [AAPL])[0]["close"] == 203.0
    _same_as_whole(monkeypatch, row)


def test_a_name_that_joins_the_universe_gets_its_whole_history(live, monkeypatch):
    """OLDCO's bars are from 2024, long before anything changed in Parquet: only the spine says it joined."""
    _respine(SPINE + [{"ticker": "OLD-A", "cik": "5550001", "name": "OLD CO", "exchange": "NYSE", "tier": "A",
                          "security_type": "common", "gvkey": "099999", "iid": "01", "composite_figi": None,
                          "cusip": "680000101"}])
    row = _serve()
    assert len(_q("SELECT 1 FROM price_bar_daily WHERE security_id = ?", [OLDCO])) == 2
    _same_as_whole(monkeypatch, row)


def test_a_name_that_leaves_the_universe_keeps_its_bars(live, monkeypatch):
    """avo's rule (DECISIONS S18): the store is never narrowed. #1079 dropped 20 securities when names left
    ``my_universe``; a name that leaves keeps every bar it had, with no ``allow_shrink``, whole build or not."""
    before = _q("SELECT * FROM price_bar_daily WHERE security_id = ? ORDER BY session_date", [AAPL])
    assert before
    _respine([r for r in SPINE if r["ticker"] != "AAPL"])
    row = _serve()
    assert "built on the live file" in _note(row), _note(row)
    assert " 0 ids the live file serves outside it kept" not in _note(row), _note(row)
    assert _q("SELECT * FROM price_bar_daily WHERE security_id = ? ORDER BY session_date", [AAPL]) == before
    got = _snapshot()
    monkeypatch.setenv(dirty.WHOLE_ENV, "1")
    assert _serve()["result"] != "failed"
    assert _snapshot() == got


@pytest.mark.parametrize("where", [f"security_id = '{AAPL}' AND session_date = (SELECT min(session_date) "
                                   f"FROM l.price_bar_daily WHERE security_id = '{AAPL}')"],
                         ids=["one row"])
def test_the_build_refuses_to_lose_a_security_or_a_row_unless_asked(live, where):
    """#1079's 20 lost securities were 0.13 % of the rows, under the swap's 1 % guard: this one counts rows. A whole
    security no source returns is carried over instead (``test_a_security_no_source_returns_keeps_its_stored_bars``)."""
    con = _shrunk_build(where)
    try:
        with pytest.raises(ValueError, match="price_bar_daily would lose"):
            prices_serving._refuse_shrink(base.RunContext(run_id="t", dataset=prices_serving.NAME), con)
        prices_serving._refuse_shrink(base.RunContext(run_id="t", dataset=prices_serving.NAME, allow_shrink=True),
                                      con)
    finally:
        con.close()


def test_a_security_no_source_returns_keeps_its_stored_bars(live):
    """19 Nov 2026: the whole build after #1089 found no bar of VBNK, KPTI, KNRXF and PLCE in any source (gone from
    Compustat's and Alpaca's files); their stored bars are carried over from the live file, not lost."""
    want = sorted(tuple(r.values()) for r in _q("SELECT * FROM price_bar_daily WHERE security_id = ?", [AAPL]))
    assert want
    con = _shrunk_build(f"security_id = '{AAPL}'")
    try:
        ctx = base.RunContext(run_id="t", dataset=prices_serving.NAME)
        prices_serving._refuse_shrink(ctx, con)
        got = sorted(con.execute("SELECT * FROM price_bar_daily WHERE security_id = ?", [AAPL]).fetchall())
        assert got == want
        assert any(AAPL in n and "kept with their" in n for n in ctx.notes), ctx.notes
    finally:
        con.close()


def test_a_carried_security_swaps_through_with_its_bars(live, monkeypatch):
    """The 19 Nov 2026 whole build carried the 4 securities no source returns a bar for, and the swap then refused
    the file over exactly those rows: ``price_bar_daily has 30905400 rows, expected 30893210``, the 12,190 carried
    bars, because the expected count was taken before the carry. The build names its own count after the carry."""
    import duckdb
    con = duckdb.connect(str(serving.live_path("prices")))
    try:
        con.execute(f"INSERT INTO price_bar_daily BY NAME SELECT * REPLACE ('{GONE}' AS security_id) "
                    "FROM price_bar_daily WHERE security_id = ?", [AAPL])
        carried = con.execute("SELECT count(*) FROM price_bar_daily WHERE security_id = ?", [GONE]).fetchone()[0]
    finally:
        con.close()
    assert carried
    monkeypatch.setenv(dirty.WHOLE_ENV, "1")
    row = _serve()
    assert "built whole" in _note(row), _note(row)
    assert "kept with their" in _note(row), _note(row)
    assert len(_q("SELECT 1 FROM price_bar_daily WHERE security_id = ?", [GONE])) == carried


def test_the_build_lets_the_same_or_more_through(live):
    con = _shrunk_build("false")
    try:
        prices_serving._refuse_shrink(base.RunContext(run_id="t", dataset=prices_serving.NAME), con)
    finally:
        con.close()


def _grown_build(bars: int):
    """A build whose ``price_bar_daily`` is ``bars`` AAPL bars short of the live file and whose **total** is larger
    than the live file's, because a name the live file does not serve joined with a whole AAPL history beside it --
    the shape of the 19 Nov 2026 build: the file was 765,616 rows up and 10 served securities were still short."""
    con = _shrunk_build(f"security_id = '{AAPL}' AND session_date IN (SELECT session_date FROM l.price_bar_daily "
                        f"WHERE security_id = '{AAPL}' ORDER BY session_date LIMIT {bars})")
    con.execute(f"INSERT INTO price_bar_daily BY NAME SELECT * REPLACE ('{JOINED}' AS security_id) "
                "FROM price_bar_daily WHERE security_id = ?", [AAPL])
    live_rows = stage.live_served(con)
    assert con.execute("SELECT count(*) FROM price_bar_daily").fetchone()[0] > sum(live_rows.values())
    assert live_rows[AAPL] > bars
    return con, live_rows


def test_a_served_security_may_not_lose_more_bars_than_the_tolerance_although_the_file_grows(live):
    """#1096: the whole build of 19 Nov 2026 (request #800) grew ``price_bar_daily`` 30,140,389 -> 30,906,005 rows
    and still came out 32 bars short over 10 securities it went on serving, and it swapped in, because the guard
    compared the file total and the swap's own guard compares a table's row count. The rows are compared per security
    id as well: an id more than ``PER_ID_SHRINK_BARS`` bars short of the live file refuses the build, named with its
    counts, and only ``allow_shrink`` lets it through."""
    bars = prices_serving.PER_ID_SHRINK_BARS + 1
    con, live_rows = _grown_build(bars)
    try:
        ctx = base.RunContext(run_id="t", dataset=prices_serving.NAME)
        with pytest.raises(ValueError) as caught:
            prices_serving._refuse_shrink(ctx, con)
        assert f"{AAPL} {live_rows[AAPL]:,} -> {live_rows[AAPL] - bars:,}" in str(caught.value), str(caught.value)
        assert f"{bars} bars inside 1 securities it still serves over the " \
               f"{prices_serving.PER_ID_SHRINK_BARS}-bar" in str(caught.value), str(caught.value)
        prices_serving._refuse_shrink(base.RunContext(run_id="t", dataset=prices_serving.NAME, allow_shrink=True),
                                      con)
    finally:
        con.close()


def test_a_shortfall_within_the_tolerance_is_named_in_the_note_and_not_refused(live):
    """avo's word of 19 Nov 2026: a served security may come out up to ``PER_ID_SHRINK_BARS`` bars short -- what a
    source restating the last days of one name costs -- and the build goes on, with the shortfall and its counts in
    the build note so it is read and not silent."""
    bars = prices_serving.PER_ID_SHRINK_BARS
    con, live_rows = _grown_build(bars)
    try:
        ctx = base.RunContext(run_id="t", dataset=prices_serving.NAME)
        prices_serving._refuse_shrink(ctx, con)
        note = " ".join(ctx.notes)
        assert f"{bars} bars short inside 1 securities" in note, ctx.notes
        assert f"{prices_serving.PER_ID_SHRINK_BARS}-bar tolerance" in note, ctx.notes
        assert f"{AAPL} {live_rows[AAPL]:,} -> {live_rows[AAPL] - bars:,}" in note, ctx.notes
    finally:
        con.close()


def test_a_moved_gvkey_series_is_not_read_as_short(live):
    """The alias path past the per-id check of #1096: a Compustat series that became a served fund's alias loses its
    id and its sessions to the fund, and is moved, not short."""
    import duckdb
    con = duckdb.connect(str(serving.live_path("prices")))
    try:
        con.execute(f"INSERT INTO price_bar_daily BY NAME SELECT * REPLACE ('{GONE}' AS security_id) "
                    "FROM price_bar_daily WHERE security_id = ?", [AAPL])
    finally:
        con.close()
    con = _shrunk_build(f"security_id = '{GONE}'")
    try:
        con.execute("INSERT INTO _gvkey_alias VALUES (?, ?)", [GONE, AAPL])
        ctx = base.RunContext(run_id="t", dataset=prices_serving.NAME)
        prices_serving._refuse_shrink(ctx, con)
        assert not ctx.notes, ctx.notes
    finally:
        con.close()


def test_a_late_cover_restates_the_caps_from_its_day(live, monkeypatch):
    """A cover whose as-of is long before anything else changed: the caps after it change, and only after it."""
    from revenuechaser.rcdata.build.prices import cover_shares
    path = cover_shares.partition_path(2026)
    rows = stage.read_rows(path) + [{
        "cik": "320193", "accession": "0000320193-25-000001", "form": "10-Q", "filed": date(2026, 10, 27),
        "period_end": date(2025, 3, 29), "class_member": "", "symbol": "AAPL", "shares": 15_100_000_000.0,
        "as_of": date(2025, 4, 18), "source_as_of": date(2026, 10, 27), "fetched_at": 9.0, "run_id": "c-late"}]
    stage.write_rows(rows, cover_shares.SCHEMA, path)
    row = _serve()
    _same_as_whole(monkeypatch, row)


def test_a_new_dividend_in_sec_divid_is_applied(live, monkeypatch):
    rows = stage.read_rows(wrds_history.partition_path("sec_divid", 2026))
    assert rows
    rows.append({**rows[-1], "datadate": date(2026, 10, 26), "divd": 0.3, "div": None, "divsp": None})
    schema = wrds_history.DIVID + wrds_history.PROVENANCE
    stage.write_rows(rows, schema, wrds_history.partition_path("sec_divid", 2026))
    row = _serve()
    assert _q("SELECT 1 FROM corporate_action WHERE security_id = ? AND ex_date = '2026-10-26'", [AAPL])
    _same_as_whole(monkeypatch, row)


def test_the_wrds_difference_report_is_kept_on_the_live_copy(live, monkeypatch):
    report = _report()
    day = date(2026, 10, 28)
    _write_secd(2026, _secd_rows(2026) + [_aapl_day(day, 203.0)])
    _clock(day)
    row = _serve()
    assert _report() == report
    assert "wrds_price_diff kept" in _note(row), _note(row)


def test_a_changed_alpaca_action_replaces_the_one_served(live, monkeypatch):
    from revenuechaser.rcdata.build.prices import actions
    path = actions.partition_path(2026)
    rows = stage.read_rows(path)
    assert rows
    stage.write_rows([{**r, "rate": 0.27} for r in rows], actions.SCHEMA, path)
    row = _serve()
    assert [r["amount"] for r in _q("SELECT amount FROM corporate_action WHERE source = ?",
                                    [prices_serving.ALPACA_ACTIONS])] == [0.27]
    _same_as_whole(monkeypatch, row)


OLD_AAPL = "cik:320193:AAPL"


def test_a_re_keyed_id_moves_to_its_spine_id_and_is_not_served_twice(live):
    """#1413 / C3 option (a): the spine's night run of 22 Nov 2026 gave five names that had bars under
    ``cik:<CIK>:<T>`` a ``gvkey:iid`` (BRRR, IBIT, NCIQ, XRPC, GBUG). The build fetched under the new id, found no bar
    of the old one, and carried the old id back from the live file: the name served twice, two rows a session. Now
    the old id is moved: the new id takes every live session it has none of, and the old id is not carried back."""
    import duckdb
    con = duckdb.connect(str(serving.live_path("prices")))
    try:                                        # the live file serves AAPL under its old id too, a session earlier
        con.execute(f"INSERT INTO price_bar_daily BY NAME SELECT * REPLACE ('{OLD_AAPL}' AS security_id) "
                    "FROM price_bar_daily WHERE security_id = ?", [AAPL])
        old_days = sorted(r[0] for r in con.execute(
            "SELECT session_date FROM price_bar_daily WHERE security_id = ?", [OLD_AAPL]).fetchall())
        # and a cik: id with no spine row of its CIK and ticker: a security no source returns, carried as before
        con.execute("INSERT INTO price_bar_daily BY NAME SELECT * REPLACE ('cik:1:GONECO' AS security_id) "
                    "FROM price_bar_daily WHERE security_id = ?", [AAPL])
    finally:
        con.close()
    first = old_days[0]
    # The build: the new id has every session but the oldest, the old id none (no source keys it any more).
    build = _shrunk_build(f"security_id IN ('{OLD_AAPL}', 'cik:1:GONECO') "
                          f"OR (security_id = '{AAPL}' AND session_date = '{first}')")
    try:
        build.execute("INSERT INTO stg_spine VALUES (?, '320193', 'AAPL')", [AAPL])
        ctx = base.RunContext(run_id="t", dataset=prices_serving.NAME)
        prices_serving._refuse_shrink(ctx, build)
        assert build.execute("SELECT count(*) FROM price_bar_daily WHERE security_id = ?",
                             [OLD_AAPL]).fetchone()[0] == 0, "the old id came back: served twice"
        new_days = sorted(r[0] for r in build.execute(
            "SELECT session_date FROM price_bar_daily WHERE security_id = ?", [AAPL]).fetchall())
        assert new_days == old_days                                         # the oldest session moved over
        assert any("re-keyed" in n and f"{OLD_AAPL} -> {AAPL}" in n for n in ctx.notes), ctx.notes
        assert build.execute("SELECT count(*) FROM price_bar_daily WHERE security_id = 'cik:1:GONECO'"
                             ).fetchone()[0] > 0                            # the un-re-keyed id is carried
    finally:
        build.close()


NEWF_FIGI = "figi:BBG00NEWF0X1"


def test_a_yahoo_name_the_spine_picks_up_moves_to_its_new_id(live, monkeypatch):
    """Review N2, avo's D1 (24 Nov 2026, "Yeni id'ye taşı"): NEWF, a fund only Yahoo prices, is served under the id
    the fetch saw (``sym:NEWF``). The spine then gives it its own id: Yahoo's rows are served under that id, nothing
    keys the old one any more, and the build carried ``sym:NEWF`` back frozen, one fund under two ids. Now the old id's
    bars move to the new id, as C3 moves a re-keyed ``cik:`` id."""
    from revenuechaser.rcdata.build.prices import yahoo_bars

    from .test_prices_wrds import _spine_etf_table
    days = ["2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27"]
    answer = [{"date": d, "open": 8.0, "high": 8.0, "low": 8.0, "close": 8.0, "volume": 1000.0, "split": 0}
              for d in days]
    monkeypatch.setattr(yahoo_bars, "_lookup", lambda t: [dict(r) for r in answer])
    _spine_etf_table([("NEWF", 5e9)])
    row = base.run_request({"dataset": yahoo_bars.NAME, "params": {"as_of": "2026-10-27", "names": ["NEWF"]}})
    assert row["result"] != "failed", row
    assert len(_q("SELECT 1 FROM price_bar_daily WHERE security_id = 'sym:NEWF'")) == len(days)
    _respine(SPINE + [{"ticker": "NEWF", "cik": None, "name": "NEW FUND", "exchange": "NYSE", "tier": "B",
                       "security_type": "etf", "gvkey": None, "iid": None, "composite_figi": NEWF_FIGI[5:]}])
    _spine_etf_table([("NEWF", 5e9)])
    row = _serve()
    assert not _q("SELECT 1 FROM price_bar_daily WHERE security_id = 'sym:NEWF'"), "the old id is still served"
    assert len(_q("SELECT 1 FROM price_bar_daily WHERE security_id = ?", [NEWF_FIGI])) == len(days)
    assert f"sym:NEWF -> {NEWF_FIGI}" in _note(row), _note(row)
    _same_as_whole(monkeypatch, row)
