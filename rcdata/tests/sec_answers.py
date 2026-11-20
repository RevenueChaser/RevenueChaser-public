"""How sec.gov answers, for the fixtures that stand in for it.

An object the ``/Archives/`` bucket does not hold answers 403 with S3's XML error, not 404 (measured 2026-10-30;
``base.is_missing`` reads that body). The SEC's own refusal — an undeclared User-Agent, or the fair-access rate —
is also a 403, but Akamai's HTML page. A test that means "this is not there" uses the first; one that means "the
SEC is refusing" uses the second.
"""
from __future__ import annotations

MISSING_OBJECT = (b'<?xml version="1.0" encoding="UTF-8"?>\n<Error><Code>AccessDenied</Code>'
                  b'<Message>Access Denied</Message><RequestId>D28HDAKJRS9CRPRG</RequestId></Error>')
MISSING_HEADERS = {"content-type": "application/xml", "server": "Apache"}

REFUSED_PAGE = (b"<!DOCTYPE html><html><head><title>SEC.gov | Your Request Originates from an Undeclared "
                b"Automated Tool</title></head><body>Your Request Originates from an Undeclared Automated Tool"
                b"</body></html>")
REFUSED_HEADERS = {"content-type": "text/html", "server": "AkamaiGHost"}

# EDGAR's edge under load: an HTML error page with a 5xx, which says nothing about whether the object is there.
# Measured in RC-Build.log on 19 Nov 2026 (#1123): 504 at 17:06 and 20:08, 502 at 19:07, all for one document.
GATEWAY_PAGE = b"<html><head><title>502 Bad Gateway</title></head><body>Bad Gateway</body></html>"
GATEWAY_HEADERS = {"content-type": "text/html", "server": "AkamaiGHost"}
