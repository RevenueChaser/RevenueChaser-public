"""Every board renders in English (avo, 19 Nov 2026: "Ever herseyi ingilizceye cevir").

The boards were written with Turkish chrome in places — the News lanes ("Piyasa", "Hisseler"), the whole Welcome
page, the X verification chips. They are English now, and this guard keeps them there: each board in
``core/tests/board_fixtures.py`` is rendered and its HTML is read for Turkish.

Two checks, both on the rendered page, so a Turkish word in a code comment or in a provider's own text never
trips it:

- the letters only Turkish writes (``ş ğ ı İ Ş Ğ``), and the three it shares with German and French
  (``ö ü ç``), none of which the boards' own words need;
- a short list of Turkish words that carry no such letter, so "Piyasa" or "Hepsi" cannot come back unnoticed.

A provider string that genuinely holds one of those letters (a company or person's name as the provider serves
it) belongs in ``_ALLOWED``, with the reason.
"""
from __future__ import annotations

import re

import pytest

from RevenueChaser.core.tests.board_fixtures import BOARDS

#: The letters Turkish writes that the boards' own words never need.
_LETTERS = re.compile(r"[şğıİŞĞöüçÖÜÇ]")

#: Turkish words that carry none of those letters, so the letter check alone would miss them.
_WORDS = re.compile(
    r"\b(Piyasa|Hisseler|Bugun|Hepsi|Yenile|Kaynak|Haberler|Takvim|Sirket|Fiyat|Beklenti|Onceki|Seans|"
    r"Bilanco|Tamam|Kapanis)\b")

#: Provider or vendor text a board shows as served, with why it is allowed.
_ALLOWED: dict[str, tuple[str, ...]] = {}


def _offenders(html: str, key: str) -> list[str]:
    allowed = _ALLOWED.get(key, ())
    for text in allowed:
        html = html.replace(text, "")
    out = []
    for m in _LETTERS.finditer(html):
        out.append(f"letter {m.group(0)!r} in ...{html[max(0, m.start() - 60):m.start() + 60]}...")
    for m in _WORDS.finditer(html):
        out.append(f"word {m.group(0)!r} in ...{html[max(0, m.start() - 60):m.start() + 60]}...")
    return out[:5]


@pytest.mark.parametrize("key", sorted(BOARDS))
def test_the_board_shows_no_turkish(key, tmp_path, monkeypatch, rawstore_tmp_db):
    html = BOARDS[key].render(tmp_path, monkeypatch)
    bad = _offenders(html, key)
    assert not bad, "the board shows Turkish; every word a board shows is English:\n" + "\n".join(bad)
