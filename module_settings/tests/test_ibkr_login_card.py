"""The IBKR gateway login shortcut on the Settings / Data health page.

avo asked for a shortcut that opens the gateway's login screen. The address is not in the code: it
comes from ``RC_IBKR_LOGIN_URL``, so an unset variable shows nothing and no host is pinned here.
Only an absolute http/https address is accepted, so a mistyped or hostile value cannot become a
live link.
"""
from __future__ import annotations

import pytest

from RevenueChaser.module_settings import report

# #527: the link moved from its own card into the top bar's IBKR gateway box
SECTION = 'id="ibkr-login-link"'
URL = "https://gateway.example.ts.net:6080/vnc.html?autoconnect=1&resize=scale"




















def test_the_payload_carries_the_variables_value(monkeypatch):
    """``inventory.build_payload`` reads the variable, so the page itself pins no address."""
    from RevenueChaser.module_settings import inventory
    monkeypatch.setenv("RC_IBKR_LOGIN_URL", URL)
    assert inventory._ibkr_login_url() == URL
    monkeypatch.delenv("RC_IBKR_LOGIN_URL")
    assert inventory._ibkr_login_url() == ""
