"""The master-row builder (issue #85 Part 2; sector order and raw SIC columns #272): pure, never blank, asof moves only
on confirmation."""
from __future__ import annotations

import copy


T1 = "2026-09-01T00:00:00Z"
T2 = "2026-09-30T00:00:00Z"

COLUMNS = {"ticker", "cik", "cik_source", "exchange", "name", "name_source", "security_type", "type_source",
           "type_asof", "sector", "sector_source", "industry_group", "group_source", "industry", "industry_source",
           "sub_industry", "sub_source", "gics_asof", "updated_at",
           "figi", "composite_figi", "share_class_figi", "exch_code", "security_description", "figi_source",
           "sic", "sic_description", "sic_group2", "sic_source",
           "cusip", "isin", "cusip_source", "isin_source"}


def full(**over):
    d = {"name": "Nvidia Corp", "market_cap": 5e12, "cik": "1045810", "cik_source": "sec_exchange", "exchange": "Nasdaq",
         "sec": {"status": "ok", "name": "NVIDIA CORP", "forms": ["10-K", "10-Q"], "sic": "3674",
                 "sic_description": "Semiconductors & Related Devices", "shell_closed": False},
         "openfigi": {"security_type": "Common Stock", "security_type2": "Common Stock", "name": "NVIDIA CORP",
                      "figi": "BBG000BBJQV0", "composite_figi": "BBG000BBJQV0", "share_class_figi": "BBG001S5TZJ6",
                      "exch_code": "US", "security_description": "NVDA"},
         "nasdaq": {"is_etf": False, "security_name": "NVIDIA Corporation - Common Stock"},
         "uw": {"sector": "Technology", "industry": "Semiconductors", "security_type": "Common Stock",
                "market_cap": 5.1e12},
         "yahoo": None, "fdic": None}
    d.update(over)
    return d






FIGI_COLS = ("figi", "composite_figi", "share_class_figi", "exch_code", "security_description")


def figis(row):
    return tuple(row[c] for c in FIGI_COLS)














def test_columns_match_the_manifest():
    from RevenueChaser.core import rawstore
    cols = {c.split()[0] for c in rawstore.MANIFEST["security_master"]["columns"] if not c.startswith("PRIMARY")}
    assert cols == COLUMNS
















# -- the S&P 1500 list and the SIC fallback in the master (#272) -------------------------------------
LISTED = {"sector": "Industrials", "sub_industry": "Research & Consulting Services", "index": "sp500"}


















# -- the raw SIC columns (#272) ---------------------------------------------------------------------
SIC_COLS = ("sic", "sic_description", "sic_group2", "sic_source")


def sics(row):
    return tuple(row[c] for c in SIC_COLS)






































