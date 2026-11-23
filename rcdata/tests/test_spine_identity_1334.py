"""Spine identity, #1334 (plan v4 step 6 and the spine part of step 7): K-B notes are Tier B, K-G delisted names
leave Tier A, K-C links a name whose Compustat company has no CIK, each behind the fresh-snapshot guard (X6)."""
from __future__ import annotations

import pytest

from revenuechaser.rcdata.build.spine import etf, tier


# ── K-B: a baby bond or a note is an exchange-traded product, so Tier B ──────────────────────────────────────

@pytest.mark.parametrize("name, operating", [
    ("Saratoga Investment Corp 8.125% Notes due 2027", "NOTEWORTHY CORP"),
    ("XYZ Corp 6.5% Senior Notes", "Notes Holdings Inc"),
    ("Some Bank Note due 2031", "SENIOR HOUSING PROPERTIES TRUST")])
def test_a_note_by_its_sec_name_is_an_etp_and_tier_b(name, operating):
    """The pattern is the one ``etf.ETN_NAME`` already reads (notes due, senior notes), so the two cannot drift.
    An operating name with the word note in it stays untyped."""
    assert etf.is_etn(name)
    assert tier.product_type("SAXX", name, "NYSE") == ("etp", "name_rule(note)")
    typ, _ = tier.security_type("SAXX", name, None, exchange="NYSE")
    assert typ == "etp" and tier.tier("NYSE", typ) == "B"
    assert tier.product_type("XYZ", operating, "NYSE") is None


# ── The fresh-snapshot guard (X6) and K-G: a security Compustat has delisted leaves Tier A ───────────────────

from datetime import date  # noqa: E402

from revenuechaser.core.providers import sec_edgar  # noqa: E402
from revenuechaser.rcdata import ops, serving  # noqa: E402
from revenuechaser.rcdata.build import base  # noqa: E402
from revenuechaser.rcdata.build.spine import funds, openfigi_map, sec_tickers, sec_tickers_mf  # noqa: E402
from revenuechaser.rcdata.build.spine import security, wrds  # noqa: E402

from . import spine_fixture as fx  # noqa: E402

ARMED_DAY = "2026-11-22"          # the first day FRESH_SNAPSHOT_FROM accepts: tonight's fresh full fetch
OLD_DAY = "2026-11-18"


@pytest.fixture
def built(monkeypatch, http_mock):
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setenv("RC_OPENFIGI_BASE", "https://figi.test")
    monkeypatch.setenv("OPENFIGI_API_KEY", "k")
    monkeypatch.setattr(funds, "FLOOR", {"sp500": 4, "sp400": 2, "sp600": 2, "ndx": 1})
    monkeypatch.setattr(wrds, "_factory", lambda: fx.FakeWrds())
    wrds.reset()
    http_mock.add("company_tickers_exchange.json", fx.SEC_FILE)
    http_mock.add("company_tickers_mf.json", fx.SEC_MF_FILE)
    http_mock.add("figi.test/v3/mapping", fx.figi_answer)
    fx.add_fund_routes(http_mock)
    for name in (sec_tickers.NAME, sec_tickers_mf.NAME, wrds.SEC_IDHIST.name, wrds.CO_HGIC.name,
                 wrds.IDXCST_HIS.name, openfigi_map.NAME, funds.NAME, security.NAME):
        attended = name.startswith("wrds/")
        params = {"mode": "backfill", "to": "2026-10-27"} if attended else {"as_of": "2026-10-27"}
        base.run_request({"dataset": name, "requested_by": "cli", "params": params})
    yield http_mock
    wrds.reset()


def _wrds_snapshot(day: str) -> None:
    """A new full ``wrds/sec_idhist`` snapshot as of ``day`` (the old one removed), which rebuilds the spine."""
    for p in wrds.parquet_dir(wrds.SEC_IDHIST.name).glob("snapshot=*"):
        for f in p.iterdir():
            f.unlink()
        p.rmdir()
    for p in wrds.raw_dir(wrds.SEC_IDHIST.name).glob("*"):
        for f in p.iterdir():
            f.unlink()
    base.run_request({"dataset": wrds.SEC_IDHIST.name, "requested_by": "cli",
                      "params": {"mode": "backfill", "to": day}})


def _sec(ticker: str) -> dict:
    with serving.open_read("spine") as con:
        cur = con.execute("SELECT * FROM security WHERE ticker = ?", [ticker])
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, cur.fetchone()))


def _issues() -> set[tuple[str, str]]:
    return {(i["kind"], i["key"]) for i in ops.open_issues(security.NAME, limit=500)[1]}


def _delist(monkeypatch, tic: str, dldtei: str) -> None:
    row = [s for s in fx.SECURITY if s["tic"] == tic][0]
    monkeypatch.setitem(row, "secstat", "I")
    monkeypatch.setitem(row, "dldtei", dldtei)


def test_compustat_inactive_is_tier_c_whatever_the_sec_file_says():
    assert tier.tier("NYSE", "common", 11, compustat_inactive=True) == "C"
    assert tier.tier("NYSE", "common", 11, compustat_inactive=False) == "A"
    assert tier.tier(None, "common", None, compustat_inactive=True) == "C"
    assert tier.tier("NYSE", "common", 11) == "A"                     # the default changes nothing


def test_the_guard_wants_a_whole_snapshot_from_the_fresh_day_on():
    assert security.FRESH_SNAPSHOT_FROM == date(2026, 11, 22)
    folder = wrds.parquet_dir(wrds.SEC_IDHIST.name)
    assert not security.wrds_armed()                                  # no snapshot at all
    (folder / f"snapshot={ARMED_DAY}").mkdir(parents=True)
    (folder / f"snapshot={ARMED_DAY}" / "company.parquet").write_bytes(b"")
    assert not security.wrds_armed(), "a snapshot without its security file is no whole snapshot"
    (folder / f"snapshot={ARMED_DAY}" / "security.parquet").write_bytes(b"")
    assert security.wrds_armed()
    (folder / "snapshot=2026-11-24").mkdir()                          # the newest snapshot is the one read
    assert not security.wrds_armed()
    (folder / "delta=2026-11-25").mkdir()                             # a delta never arms it
    assert not security.wrds_armed()


def test_a_name_compustat_delisted_leaves_tier_a_on_a_fresh_snapshot(built, monkeypatch):
    """ARI, BWMN and ROKU's case (#1334 K-G): inactive in Compustat with a deletion date on or before the SEC
    file's day, while the weekly SEC file still lists the name."""
    _delist(monkeypatch, "FDX", "2026-10-20")
    _delist(monkeypatch, "NVR", "2026-11-20")                         # after the SEC row's source_as_of
    _wrds_snapshot(ARMED_DAY)
    assert (_sec("FDX")["exchange"], _sec("FDX")["tier"]) == ("NYSE", "C")
    assert ("tier_a_compustat_inactive", "FDX") in _issues()
    assert ("wrds_snapshot_not_armed", wrds.SEC_IDHIST.name) not in _issues()
    assert _sec("MSFT")["tier"] == "A"
    # a deletion after the SEC file's day changes nothing
    assert _sec("NVR")["tier"] == "A" and ("tier_a_compustat_inactive", "NVR") not in _issues()


def test_an_old_snapshot_demotes_nothing_links_nothing_by_ticker_and_says_so_once(built, monkeypatch):
    _delist(monkeypatch, "FDX", "2026-10-20")
    sec, co, s = NOCK
    _with(monkeypatch, [sec], [co], [s])
    _wrds_snapshot(OLD_DAY)
    assert _sec("FDX")["tier"] == "A"
    assert _sec("NOCK")["gvkey"] is None and ("linked_by_ticker", "NOCK") not in _issues()
    assert ("wrds_snapshot_not_armed", wrds.SEC_IDHIST.name) in _issues()
    assert len([k for k in _issues() if k[0] == "wrds_snapshot_not_armed"]) == 1


# ── K-C: a name whose Compustat company has no CIK is linked by its ticker ───────────────────────────────────

def _with(monkeypatch, sec=(), company=(), securities=()) -> None:
    """Extra SEC rows and Compustat rows, then the SEC file read again (as of 2026-10-28)."""
    monkeypatch.setitem(fx.SEC_FILE, "data", fx.SEC_FILE["data"] + [list(r) for r in sec])
    monkeypatch.setattr(fx, "COMPANY", fx.COMPANY + list(company))
    monkeypatch.setattr(fx, "SECURITY", fx.SECURITY + list(securities))
    base.run_request({"dataset": sec_tickers.NAME, "requested_by": "cli", "params": {"as_of": "2026-10-28"}})


def _co(gvkey, conm, cik):
    return {"gvkey": gvkey, "conm": conm, "cik": cik}


def _security(gvkey, tic, cusip, exchg=14, secstat="A"):
    return {"gvkey": gvkey, "iid": "01", "tic": tic, "cusip": cusip, "exchg": exchg, "excntry": "USA",
            "secstat": secstat, "tpci": "0", "dldtei": None}


NOCK = ([4000001, "NOCIK THERAPEUTICS INC", "NOCK", "Nasdaq"], _co("050001", "NOCIK THERAPEUTICS", None),
        _security("050001", "NOCK", "65500X101"))


#: Names beside NOCK that must not link by their ticker: (SEC row, company rows, security rows). Each is its own
#: ticker, gvkey and CIK, and the ticker scan is per ticker, so they share NOCK's build.
NO_TICKER_LINK = [
    # two candidates link neither
    ([4000004, "TWOX CO", "TWOX", "Nasdaq"], [_co("050004", "TWOX ONE", None), _co("050005", "TWOX TWO", None)],
     [_security("050004", "TWOX", "00300X101"), _security("050005", "TWOX", "00300X102", exchg=11)]),
    # an inactive or non-US candidate is no candidate
    ([4000011, "NOCI CO", "NOCI", "Nasdaq"], [_co("050011", "NOCI CO", None)],
     [_security("050011", "NOCI", "65500X111", secstat="I")]),
    ([4000012, "NOCJ CO", "NOCJ", "Nasdaq"], [_co("050012", "NOCJ CO", None)],
     [_security("050012", "NOCJ", "65500X112", exchg=19)]),
    ([4000013, "NOCL CO", "NOCL", "Nasdaq"], [_co("050013", "NOCL CO", None)],
     [_security("050013", "NOCL", "65500X113", exchg=90)]),
    # a candidate with no company row is no candidate
    ([4000014, "NOCR CO", "NOCR", "Nasdaq"], [], [_security("050014", "NOCR", "65500X114")]),
]


def test_a_name_whose_compustat_company_has_no_cik_is_linked_by_its_ticker(built, monkeypatch):
    sec, co, s = NOCK
    _with(monkeypatch, [sec, [4000003, "PADX CO", "PADX", "Nasdaq"]] + [r[0] for r in NO_TICKER_LINK],
          [co, _co("050003", "PADX CO", "0004000003")] + [c for r in NO_TICKER_LINK for c in r[1]],
          [s, _security("050003", "PADX", "00200X101")] + [x for r in NO_TICKER_LINK for x in r[2]])
    _wrds_snapshot(ARMED_DAY)
    row = _sec("NOCK")
    assert (row["gvkey"], row["iid"], row["link_source"], row["cusip"]) == ("050001", "01", "tic_nocik", "65500X101")
    assert row["tier"] == "A" and ("linked_by_ticker", "NOCK") in _issues()
    assert ("tier_a_no_wrds_link", "NOCK") not in _issues()
    assert _sec("MSFT")["link_source"] == "tic"                     # the CIK link is unchanged
    # a padded equal CIK is no conflict, and the CIK link takes it
    assert _sec("PADX")["link_source"] == "tic" and ("ticker_link_cik_differs", "PADX") not in _issues()
    for r in NO_TICKER_LINK:
        t = r[0][2]
        assert _sec(t)["gvkey"] is None and ("linked_by_ticker", t) not in _issues(), t


def test_a_zero_padded_empty_or_blank_compustat_cik_is_empty_too(built, monkeypatch):
    """``norm_cik`` reads Compustat's text (``0000789019``), so a blank one is empty, not a CIK."""
    sec, co, s = NOCK
    _with(monkeypatch, [sec], [{**co, "cik": "   "}], [s])
    _wrds_snapshot(ARMED_DAY)
    assert _sec("NOCK")["link_source"] == "tic_nocik"


def test_a_ticker_hit_whose_compustat_cik_differs_is_refused(built, monkeypatch):
    """AGLT and XTLB's case (13 names on 21 Nov 2026): Compustat's company has a CIK, and it is another one, so
    the security is another issuer's that carries the ticker. Compared with ``norm_cik`` on both sides."""
    _with(monkeypatch, [[4000002, "AGLX CO", "AGLX", "Nasdaq"]], [_co("050002", "AGLX OTHER", "0004999999")],
          [_security("050002", "AGLX", "00100X101")])
    _wrds_snapshot(ARMED_DAY)
    assert _sec("AGLX")["gvkey"] is None
    assert ("ticker_link_cik_differs", "AGLX") in _issues() and ("linked_by_ticker", "AGLX") not in _issues()


def test_the_rule_is_version_6_and_every_row_says_so(built):
    """K-B, K-C and K-G change what a row's ``tier`` says, so its version is stamped anew on every row."""
    assert tier.VERSION == 6 and _sec("MSFT")["tier_rule"] == 6
