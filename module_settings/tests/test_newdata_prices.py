"""PR 7 (G2): the prices store's cards in the "New data system" section of Settings: a label per dataset, the
bars' 99 % coverage target, the WRDS history's attended command, its backfill progress by table and year, and the
monthly WRDS difference report on its card."""
from __future__ import annotations

from datetime import date, datetime, timezone

import duckdb
import pytest

from revenuechaser.core import calendar, config
from revenuechaser.module_settings import newdata
from revenuechaser.rcdata import ops, serving
from revenuechaser.rcdata.build.prices import serving as prices_serving, wrds_history

NOW = datetime(2026, 10, 29, 3, 0, tzinfo=timezone.utc)
PRICES = ("alpaca/bars", "alpaca/corporate_actions", "sec/cover_shares", "yfinance/float", "tradingview/float",
          "wrds/prices", "prices/serving")


@pytest.fixture(autouse=True)
def roots(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MARKET_DIR", tmp_path / "market")
    monkeypatch.setattr(config, "MARKET_RAW_DIR", tmp_path / "market_raw")
    monkeypatch.setattr(config, "RAW_STORE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(ops, "read_log", ops.ReadLog(process="test"))
    monkeypatch.setattr(calendar, "_now", lambda: NOW)
    return tmp_path


def _card(dataset: str) -> dict:
    return next(c for c in newdata.collect(NOW)["datasets"] if c["dataset"] == dataset)


def _prices_file(report=()):
    """A live prices.duckdb with two bars and the given ``wrds_price_diff`` rows."""
    path = serving.live_path("prices")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute(f"CREATE TABLE {serving.VERSION_TABLE} (kind TEXT, version INTEGER, built_at DOUBLE, "
                    "build_id TEXT)")
        con.execute(f"INSERT INTO {serving.VERSION_TABLE} VALUES ('prices', 1, 1761700000, 'test')")
        for table in ("price_bar_daily", "wrds_price_diff"):
            cols = ", ".join(f'"{c}" {t}' for c, t in prices_serving.SCHEMAS[table])
            con.execute(f"CREATE TABLE {table} ({cols})")
        con.execute("INSERT INTO price_bar_daily (security_id, session_date, close, source) VALUES "
                    "('001690:01', DATE '2026-10-27', 202.0, 'alpaca/bars'), "
                    "('001690:01', DATE '2026-10-28', 203.0, 'alpaca/bars')")
        names = [c for c, _ in prices_serving.WRDS_PRICE_DIFF]
        for r in report:
            con.execute(f"INSERT INTO wrds_price_diff ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
                        [r.get(c) for c in names])
    finally:
        con.close()


def test_every_prices_dataset_has_a_card_and_a_label():
    cards = {c["dataset"]: c for c in newdata.collect(NOW)["datasets"]}
    for name in PRICES:
        assert name in cards and cards[name]["label"] != name, name
    assert cards["alpaca/bars"]["coverage_target"] == 0.99


def test_the_wrds_history_card_offers_buttons_now_instead_of_a_command():
    # #1361: the WRDS datasets are no longer ``attended``, so the card stops being the "runs only from a
    # terminal" kind. ``report.py`` renders the copy-paste command only in that branch; every other card gets
    # Fetch and Backfill buttons instead, which is the better affordance and why nothing is lost here.
    card = _card("wrds/prices")
    assert card["attended"] is False
    assert card["attended_command"] is None
    assert card["wrds"]["text"] == "no WRDS run yet"
    assert _card("wrds/sec_idhist")["attended"] is False


def test_the_wrds_history_backfill_counts_its_table_years(monkeypatch):
    monkeypatch.setattr(wrds_history, "START_YEAR", 2024)
    part = wrds_history.partition_path("secd", 2025)
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"PAR1")
    bf = _card("wrds/prices")["backfill"]
    assert (bf["done"], bf["expected"]) == (1, 8)                    # secd 2024-26, dsf 2024-25, sec_divid 2024-26
    assert "secd 2024" in bf["missing"] and "secd 2025" not in bf["missing"] and bf["resumable"]
    assert bf["last_partition"] == "secd 2025" and bf["from_earliest"] == "2024-01-01"


def test_the_bars_card_reads_its_table_and_the_wrds_card_its_difference_report():
    _prices_file(report=[
        {"comparison": "crsp_vs_compustat", "as_of": date(2026, 10, 27), "securities": 1, "sessions": 5,
         "close_differs": 1, "max_close_diff": 0.0005},
        {"comparison": "compustat_returns", "as_of": date(2026, 10, 27), "securities": 2, "sessions": 6,
         "return_differs": 2, "max_return_diff": 0.0003},
        {"comparison": "crsp_vs_alpaca", "as_of": date(2026, 10, 27), "securities": 0, "sessions": 0,
         "close_differs": 0}])
    bars = _card("alpaca/bars")
    assert bars["table_rows"] == 2 and bars["newest"] == "2026-10-28"
    text = _card("wrds/prices")["wrds"]["text"]
    assert text.startswith("as of 2026-10-27")
    assert "CRSP vs Compustat closes: 5 sessions, 1 over 1 bp (max 0.050%)" in text
    assert "Compustat returns vs the store's: 6 sessions, 2 over 1 bp (max 0.030%)" in text
    assert "CRSP vs Alpaca closes: no common session" in text
    assert _card("alpaca/bars")["wrds"]["text"] == "no WRDS run yet"


def test_the_wrds_card_shows_the_newest_report_of_the_kept_series():
    # #1413 P-C: the table keeps a row per comparison and ``as_of``; an older month's numbers stay off the card.
    _prices_file(report=[
        {"comparison": "crsp_vs_compustat", "as_of": date(2026, 9, 27), "securities": 1, "sessions": 4,
         "close_differs": 3, "max_close_diff": 0.0009},
        {"comparison": "crsp_vs_compustat", "as_of": date(2026, 10, 27), "securities": 1, "sessions": 5,
         "close_differs": 1, "max_close_diff": 0.0005}])
    wrds = _card("wrds/prices")["wrds"]
    assert wrds["text"] == "as of 2026-10-27: CRSP vs Compustat closes: 5 sessions, 1 over 1 bp (max 0.050%)"
    assert len(wrds["rows"]) == 1
