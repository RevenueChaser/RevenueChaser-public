"""ISO 3166-1 country codes: alpha-3 to alpha-2, from the list in ``iso3166.json``.

Compustat spells a country alpha-3 (``comp.company.loc``, ``USA``); the SEC's submissions header is read alpha-2
(``build/fundamentals/edgar_codes``), and the boards compare against ``US``. One loader for both readers, so a
second copy of the map cannot drift: ``etf_class`` needs the whole dict as a SQL table, ``security`` one code at a
time. The JSON is a published list and is never edited by hand.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).with_name("iso3166.json")


@lru_cache(maxsize=1)
def codes() -> dict[str, str]:
    """``{alpha-3: alpha-2}`` of the published list."""
    return dict(json.loads(FILE.read_text(encoding="utf-8"))["codes"])


def alpha2(code: str | None) -> str | None:
    """The alpha-2 country of an alpha-3 code (``USA`` -> ``US``); None for a blank or unknown one."""
    return codes().get((code or "").strip().upper())
