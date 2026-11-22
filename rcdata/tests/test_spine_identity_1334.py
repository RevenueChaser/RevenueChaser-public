"""Spine identity, #1334 (plan v4 step 6 and the spine part of step 7): K-B notes are Tier B, K-G delisted names
leave Tier A, K-C links a name whose Compustat company has no CIK, each behind the fresh-snapshot guard (X6)."""
from __future__ import annotations

import pytest

from revenuechaser.rcdata.build.spine import etf, tier


# ── K-B: a baby bond or a note is an exchange-traded product, so Tier B ──────────────────────────────────────

@pytest.mark.parametrize("name", ["Saratoga Investment Corp 8.125% Notes due 2027", "XYZ Corp 6.5% Senior Notes",
                                  "Some Bank Note due 2031"])
def test_a_note_by_its_sec_name_is_an_etp_and_tier_b(name):
    """The pattern is the one ``etf.ETN_NAME`` already reads (notes due, senior notes), so the two cannot drift."""
    assert etf.is_etn(name)
    assert tier.product_type("SAXX", name, "NYSE") == ("etp", "name_rule(note)")
    typ, _ = tier.security_type("SAXX", name, None, exchange="NYSE")
    assert typ == "etp" and tier.tier("NYSE", typ) == "B"


@pytest.mark.parametrize("name", ["NOTEWORTHY CORP", "Notes Holdings Inc", "SENIOR HOUSING PROPERTIES TRUST"])
def test_an_operating_name_with_the_word_note_stays_untyped(name):
    assert tier.product_type("XYZ", name, "NYSE") is None


# ── The fresh-snapshot guard (X6) and K-G: a security Compustat has delisted leaves Tier A ───────────────────

from datetime import date  # noqa: E402

from revenuechaser.core.providers import sec_edgar  # noqa: E402
from revenuechaser.rcdata import ops, serving  # noqa: E402
from revenuechaser.rcdata.build import base  # noqa: E402
from revenuechaser.rcdata.build.spine import funds, openfigi_map, sec_tickers, sec_tickers_mf  # noqa: E402
from revenuechaser.rcdata.build.spine import security, wrds  # noqa: E402

from . import spine_fixture as fx  # noqa: E402

ARMED_DAY = "2026-11-23"          # the first day FRESH_SNAPSHOT_FROM accepts: tonight's fresh full fetch
OLD_DAY = "2026-11-22"


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
    assert security.FRESH_SNAPSHOT_FROM == date(2026, 11, 23)
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
    _wrds_snapshot(ARMED_DAY)
    assert (_sec("FDX")["exchange"], _sec("FDX")["tier"]) == ("NYSE", "C")
    assert ("tier_a_compustat_inactive", "FDX") in _issues()
    assert ("wrds_snapshot_not_armed", wrds.SEC_IDHIST.name) not in _issues()
    assert _sec("MSFT")["tier"] == "A"


def test_a_deletion_after_the_sec_files_day_changes_nothing(built, monkeypatch):
    _delist(monkeypatch, "FDX", "2026-11-20")                         # after the SEC row's source_as_of
    _wrds_snapshot(ARMED_DAY)
    assert _sec("FDX")["tier"] == "A" and ("tier_a_compustat_inactive", "FDX") not in _issues()


def test_an_old_snapshot_demotes_nothing_and_says_so_once(built, monkeypatch):
    _delist(monkeypatch, "FDX", "2026-10-20")
    _wrds_snapshot(OLD_DAY)
    assert _sec("FDX")["tier"] == "A"
    assert ("wrds_snapshot_not_armed", wrds.SEC_IDHIST.name) in _issues()
    assert len([k for k in _issues() if k[0] == "wrds_snapshot_not_armed"]) == 1
