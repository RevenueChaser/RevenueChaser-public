"""``etf``: the rule that settles a row whose series N-CEN and the SEC fund file disagree on (avo's option A,
24 Nov 2026; evidence: claude-coordinator ``reviews/2026-11-24_1732_revenuechaser_etf-series-file-disagrees-17.md``).

1. Both series have N-PORT reports: the newer newest ``report_date`` wins; a series with none loses to one with some.
2. The fund file's series has none yet: it wins when the Compustat CUSIP issuer code of the row's series changed
   after N-CEN's report period end and the file's series sits under another CIK (ARB, EVNT, MAGA).
3. N-CEN's series has filed no N-PORT for over 150 days and the row has no Compustat series: the fund is dead
   (QUP, QDWN). Its row stays, with no AUM, so it cannot enter ``my_universe``.

What the rule cannot settle stays one ``etf_series_file_disagrees`` issue (CONI); each settled row is named in a note.
"""
from __future__ import annotations

from datetime import date

import duckdb

from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.spine import etf, security

from .test_spine_etf import _nport
from .test_spine_etf_adv import put_secd, series
from .test_spine_etf_sources import DAY, _con


def _reports(*reports: tuple[str, str, date], quarter: str = "2026q3") -> None:
    """``sec/nport`` ``fund.parquet`` of one quarter: ``(series_id, series_name, report_date)`` per report."""
    folder = base.parquet_root() / "sec" / "nport" / f"quarter={quarter}"
    folder.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    base.rows_table(con, "f", [("accession", "TEXT"), ("series_id", "TEXT"), ("series_name", "TEXT"),
                               ("report_date", "DATE"), ("filed", "DATE")],
                    [{"accession": f"{s}-{d}", "series_id": s, "series_name": n, "report_date": d, "filed": d}
                     for s, n, d in reports])
    con.execute(f"COPY f TO {base.sql_path(folder / 'fund.parquet')} (FORMAT PARQUET)")
    con.close()


def _disagree(con, ticker: str, ours: tuple[str, str, date], theirs: tuple[str, str]) -> None:
    """N-CEN files ``ticker`` under ``ours`` (series, CIK, report period end), the fund file under ``theirs``
    (series, CIK)."""
    con.execute(f"INSERT INTO {etf.NCEN} (ticker, cik, series_id, fund_name, is_etf, filing_date, report_end, "
                "accession, daily_avg_net_assets) VALUES (?, ?, ?, ?, TRUE, DATE '2026-03-01', ?, 'a-' || ?, 5e8)",
                [ticker, ours[1], ours[0], f"{ticker} ETF", ours[2], ours[0]])
    con.execute("INSERT INTO stg_sec_mf (ticker, cik, series_id, class_id, is_etf) VALUES (?, ?, ?, ?, TRUE)",
                [ticker, theirs[1], theirs[0], "C-" + ticker])


def _build(con) -> tuple[dict[str, dict], list, list[str]]:
    ctx = base.RunContext(run_id="r", dataset=security.NAME, as_of=DAY)
    issues: list = []
    rows = {r["ticker"]: r for r in etf.rows(ctx, con, issues)}
    return rows, [key for kind, key, _ in issues if kind == "etf_series_file_disagrees"], ctx.notes


def test_the_series_whose_newest_nport_is_newer_wins_and_one_with_none_loses():
    """Rule 1. AESR moved to Horizon Funds (S2 reports in July, its old S1 last in April): the file's series wins,
    with its CIK. CPII's file series S4 last reported in 2025, ours in July: ours. PLTD's file series S6 never
    reported, ours did: ours. Each settled row is named in a note, and none is an issue."""
    _reports(("S1", "Anfield Sector Rotation", date(2026, 4, 30)), ("S2", "Anfield Sector Rotation", date(2026, 7, 31)),
             ("S3", "Ionic Inflation", date(2026, 7, 31)), ("S5", "Direxion PLTR Bear", date(2026, 7, 31)))
    _reports(("S4", "Ionic Inflation", date(2025, 1, 31)), quarter="2025q1")
    con = _con()
    _disagree(con, "AESR", ("S1", "1552947", date(2025, 10, 31)), ("S2", "1643174"))
    _disagree(con, "CPII", ("S3", "1096012", date(2026, 1, 31)), ("S4", "1742912"))
    _disagree(con, "PLTD", ("S5", "1424958", date(2025, 10, 31)), ("S6", "1771146"))
    rows, open_, notes = _build(con)
    assert {t: (r["series_id"], r["cik"]) for t, r in rows.items()} == {
        "AESR": ("S2", "1643174"), "CPII": ("S3", "1096012"), "PLTD": ("S5", "1424958")}
    assert open_ == []
    note, = [n for n in notes if n.startswith("etf series vs the SEC fund file")]
    assert "AESR S1->S2" in note and "CPII kept S3" in note and "PLTD kept S5" in note


def test_the_file_series_with_no_nport_wins_when_the_issuer_code_changed_after_ncens_period():
    """Rule 2. ARB's Compustat CUSIP (``comp.sec_idhist``) moved from AltShares' 02210T to 03875R on 28 Sep, after
    N-CEN's period end of 31 May, and the file's series sits under another CIK: the file's series wins. TGLR's
    moved on 13 Apr, before its N-CEN period end of 30 Apr: rule 2 does not fire, and rule 1 keeps ours (it
    reported, S13 not). ``comp.secd`` carries today's CUSIP on every day, so only the history table says when.
    Until ARB's new series reports, its class is read on its old series' N-PORT."""
    put_secd(series("070001", "01", "ARB", 3, 1e6, cusip="03875R791")
             + series("070002", "01", "TGLR", 3, 1e6, cusip="947913307"))
    _nport([("A10", "S10", date(2026, 5, 31)), ("A12", "S12", date(2026, 7, 31))],
           [("A10", 95.0, "EC", "CORP"), ("A12", 95.0, "EC", "CORP")])
    con = _con()
    con.execute("CREATE TABLE stg_wrds_idhist (gvkey TEXT, iid TEXT, item TEXT, itemvalue TEXT, efffrom DATE, "
                "effthru DATE)")
    con.execute("""INSERT INTO stg_wrds_idhist VALUES
        ('070001', '01', 'CUSIP', '02210T108', DATE '2020-05-07', DATE '2026-09-27'),
        ('070001', '01', 'CUSIP', '03875R791', DATE '2026-09-28', NULL),
        ('070002', '01', 'CUSIP', '26923N769', DATE '2023-01-01', DATE '2026-04-12'),
        ('070002', '01', 'CUSIP', '947913307', DATE '2026-04-13', NULL)""")
    _disagree(con, "ARB", ("S10", "1779306", date(2026, 5, 31)), ("S11", "1105076"))
    _disagree(con, "TGLR", ("S12", "2055464", date(2026, 4, 30)), ("S13", "1771146"))
    rows, open_, _ = _build(con)
    assert (rows["ARB"]["series_id"], rows["ARB"]["cik"], rows["ARB"]["asset_class"]) == ("S11", "1105076", "equity")
    assert rows["TGLR"]["series_id"] == "S12"
    assert open_ == []


def test_a_series_silent_for_150_days_with_no_compustat_series_is_dead_and_takes_no_aum():
    """Rule 3. QUP's series last reported on 30 Nov 2025 and Compustat prices no QUP: the fund was liquidated and
    the ticker is being reused. The row stays on its own series with no AUM (so ``my_universe`` cannot take it on
    N-CEN's 2025 figure), the file's series is only named in the note, and no issue is left."""
    _reports(("S20", "DailyDelta Q100 Upside", date(2025, 11, 30)), quarter="2025q4")
    con = _con()
    _disagree(con, "QUP", ("S20", "1873280", date(2025, 8, 31)), ("S21", "2043390"))
    rows, open_, notes = _build(con)
    assert (rows["QUP"]["series_id"], rows["QUP"]["aum"], rows["QUP"]["aum_source"]) == ("S20", None, None)
    assert open_ == []
    note, = [n for n in notes if n.startswith("etf series vs the SEC fund file")]
    assert "QUP dead" in note and "S21" in note


def test_a_sibling_series_of_the_same_trust_stays_open_where_our_series_reported_two_funds():
    """CONI and NVYY: in both the file's series is an unstarted sibling under the same GraniteShares CIK. NVYY's
    series reported one fund throughout: ours (rule 1). CONI's reported "1x Short COIN" and later "2x Short COIN",
    while EDGAR ties the ticker to the sibling: the rule cannot say which, so CONI stays an issue on ours."""
    _reports(("S30", "GraniteShares 1x Short COIN Daily ETF", date(2025, 3, 31)), quarter="2025q2")
    _reports(("S30", "GraniteShares 2x Short COIN Daily ETF", date(2026, 6, 30)),
             ("S32", "GraniteShares YieldBOOST NVDA ETF", date(2026, 6, 30)))
    con = _con()
    _disagree(con, "CONI", ("S30", "1689873", date(2026, 6, 30)), ("S31", "1689873"))
    _disagree(con, "NVYY", ("S32", "1689873", date(2026, 6, 30)), ("S33", "1689873"))
    rows, open_, _ = _build(con)
    assert (rows["CONI"]["series_id"], rows["NVYY"]["series_id"]) == ("S30", "S32")
    assert open_ == ["CONI"]
