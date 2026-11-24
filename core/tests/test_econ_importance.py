"""The economic calendar's importance rule (News board plan §4): one tested table, three levels.

3 = the releases that move the whole market, 2 = the second tier and Fed speakers other than the chair, 1 = the rest.
"""
from __future__ import annotations

import pytest

from revenuechaser.core import econ_importance as ei


@pytest.mark.parametrize("event, kind", [
    ("CPI, Y/Y%", "report"),
    ("Core CPI, M/M%", "report"),
    ("PCE price index", "report"),
    ("Core PCE price index, Y/Y%", "report"),
    ("Employment Report", "report"),
    ("Nonfarm payrolls", "report"),
    ("Employment Situation", "report"),
    ("GDP (advance)", "report"),
    ("Retail sales", "report"),
    ("ISM manufacturing PMI", "report"),
    ("FOMC rate decision", "fomc"),
    ("Fed interest rate decision", "report"),
    ("Fed Chair speaks", "fed-speaker"),
    # TradingView's and the Fed's own names (#1433): payrolls is "Non Farm Payrolls", the chair a Board speech.
    ("Non Farm Payrolls", "report"),
    ("Speech - Chair Jerome H. Powell", "fed-speaker"),
    ("FOMC Meeting", "fomc"),
    # TradingView's own high rows (live, 24 Nov 2026): the jobless rate, CPI as "Inflation Rate", the FOMC decision.
    ("Unemployment Rate", "report"),
    ("Inflation Rate YoY", "report"),
    ("Core Inflation Rate MoM", "report"),
    ("Interest Rate", "report"),
])
def test_high(event, kind):
    assert ei.importance(event, kind) == 3


@pytest.mark.parametrize("event, kind", [
    ("PPI, M/M%", "report"),
    ("JOLTS job openings", "report"),
    ("Weekly Jobless Claims", "report"),
    ("Consumer sentiment", "report"),
    ("NY Fed consumer inflation expectations", "report"),
    ("Housing starts", "report"),
    ("Fed President Musalem speaks", "fed-speaker"),
    ("Fed Vice Chair speaks", "fed-speaker"),
])
def test_medium(event, kind):
    assert ei.importance(event, kind) == 2


@pytest.mark.parametrize("event, kind", [
    ("Wholesale inventories", "report"),
    ("Baker Hughes rig count", "report"),
    ("Interest Rate on Reserve Balances", "report"),       # "Interest Rate" is high only as the whole name
    ("Interest Rate Projection - Current", "report"),
    ("", "report"),
    (None, None),
])
def test_low(event, kind):
    assert ei.importance(event, kind) == 1


def test_case_and_spacing_do_not_matter():
    assert ei.importance("  core   cpi ", "REPORT") == 3


def test_ppi_is_not_read_as_cpi():
    """'ppi' and 'cpi' share letters; the match is on words, so PPI stays medium."""
    assert ei.importance("PPI ex food and energy", "report") == 2


def test_dots_render_the_level():
    assert ei.dots(3) == "●●●" and ei.dots(2) == "●●○" and ei.dots(1) == "●○○"
