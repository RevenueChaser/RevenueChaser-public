"""#108 S0 (#388, CL-A): the Value Chain CLI takes a floor (USD millions) or a ticker list.

Without either, ``--sync-filings`` and ``--fetch`` select exactly today's names (``tickers=None``: the $300M
classification universe, and for the sync the submissions sweep of every universe CIK, #299). Offline.
"""
from __future__ import annotations

import pytest

from revenuechaser.rcdata.tests import universe_store
from revenuechaser.module_value_chain import __main__ as cli














def test_the_help_warns_about_sec_requests(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "Makes SEC requests for these names" in " ".join(capsys.readouterr().out.split())
