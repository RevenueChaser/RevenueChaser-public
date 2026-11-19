"""Every word a board shows is English (avo, 19 Nov 2026: "Ever herseyi ingilizceye cevir").

The boards were written with Turkish chrome in places — the News lanes ("Piyasa", "Hisseler"), the whole Welcome
page, the X verification chips. They are English now, and this guard keeps them there: each board in
``core/tests/board_fixtures.py`` is rendered and the text the page shows is read for Turkish.

Two checks:

- the letters only Turkish writes (``ş ğ ı İ Ş Ğ``), and the three it shares with German and French
  (``ö ü ç``), none of which the boards' own words need;
- a short list of Turkish words that carry no such letter, so "Piyasa" or "Hepsi" cannot come back unnoticed.

What is read is what a reader can see: the markup, its attributes (``title``, ``aria-label``) and the strings in
the board's own scripts. What is not: HTML comments, the inlined stylesheets, and the comments inside the inlined
scripts. Those carry the boards' provenance — avo's own words, quoted in Turkish by design (CLAUDE.md: code and
comments are English, his quotes inside them are not) — and no reader ever sees them.

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

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)
_SCRIPT = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)", re.S | re.I)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"^[ \t]*//.*$", re.M)        # only a whole comment line, so https:// survives


def shown_text(html: str) -> str:
    """The page without what no reader sees: HTML comments, the stylesheets, and the scripts' own comments."""
    html = _HTML_COMMENT.sub(" ", html)
    html = _STYLE.sub(" ", html)

    def _clean(m: re.Match) -> str:
        body = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub(" ", m.group(2)))
        return m.group(1) + body + m.group(3)

    return _SCRIPT.sub(_clean, html)


def _offenders(html: str, key: str) -> list[str]:
    text = shown_text(html)
    for allowed in _ALLOWED.get(key, ()):
        text = text.replace(allowed, "")
    out = []
    for pat, what in ((_LETTERS, "letter"), (_WORDS, "word")):
        for m in pat.finditer(text):
            out.append(f"{what} {m.group(0)!r} in ...{text[max(0, m.start() - 70):m.start() + 70]}...")
    return out[:5]


@pytest.mark.parametrize("key", sorted(BOARDS))
def test_the_board_shows_no_turkish(key, tmp_path, monkeypatch, rawstore_tmp_db):
    bad = _offenders(BOARDS[key].render(tmp_path, monkeypatch), key)
    assert not bad, "the board shows Turkish; every word a board shows is English:\n" + "\n".join(bad)


def test_the_guard_reads_what_the_page_shows_and_not_its_comments():
    page = ("<!-- avo: çok ayrık -->"
            "<style>/* avo, 13 Nov 2026: \"daha küçük kutular\" */ .a{color:red}</style>"
            "<script>/* avo: başlık */\n  // avo: ayrı\n  var u = 'https://x/';var t = 'Market';</script>"
            "<p>Market</p>")
    assert not _offenders(page, "none")
    assert "https://x/" in shown_text(page) and "var t = 'Market'" in shown_text(page)
    assert _offenders(page.replace("<p>Market</p>", "<p>Piyasa</p>"), "none")
    assert _offenders(page.replace("<p>Market</p>", "<p>son kapanış</p>"), "none")
