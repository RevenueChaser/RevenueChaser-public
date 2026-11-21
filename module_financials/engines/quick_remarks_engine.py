"""Quick Remarks Engine — Momentum-Growth skoru, Asymmetric Growth Hunter ile aynı metodoloji.

3 sinyal (her biri X/3), toplam 0-9 puan — Hunter'ın ``asymmetric_growth_hunter``
ile birebir aynı eşikler/tanımlar. Dilution ve R&D skor kuralı değil, overlay
(uyarı/etiket).

Veri: paylaşılan ``ticker_scores`` ve başka hiçbir şey. Yahoo fallback'i #645 ile kalktı (avo 10 Kas 2026,
B seçeneği): o yol bir ``.info`` ve bir yıllık tarihçe isteği yapıyordu, ve Asymmetric Growth kartı bu skoru
zaten aynı SEC tablolarından üretiyor (#994). Kart yoksa bölüm skoru olmadığını söyler.
"""
from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


def _session(stamp) -> str | None:
    """The New York session ``stamp`` (an ISO instant) belongs to, the day the header names; None when unreadable."""
    from RevenueChaser.core.calendar import to_session_date
    try:
        day = to_session_date(str(stamp).strip()) if stamp else None
    except Exception:  # noqa: BLE001 - a label is never worth an error
        return None
    return day.isoformat() if day else None


def _from_card(ticker: str, card: dict, source: str, as_of: str | None = None, as_of_note: str | None = None) -> dict:
    """The section's fields; ``as_of`` / ``as_of_note`` say when the score was made and by what (review S5)."""
    return {
        "ticker": ticker,
        "company": card.get("name") or ticker,
        "price": card.get("price"),
        "sector": card.get("sector"),
        "source": source,
        "score": card.get("total_points"),
        "max": 9,
        "signals": card.get("signals") or [],
        "dilution_warning": card.get("dilution_warning"),
        "dilution_yoy": card.get("dilution_yoy"),
        "tech_breakthrough": card.get("tech_breakthrough"),
        "rd_intensity": card.get("rd_intensity"),
        "as_of": as_of,
        "as_of_note": as_of_note,
    }


def run_quick_remarks(ticker: str, no_fetch: bool = False, financials: dict | None = None) -> dict:
    """The shared ``ticker_scores`` card for ``ticker``, or an empty section when the scan holds none.

    One store read and no provider call (#645). ``no_fetch`` and ``financials`` are kept for the callers that
    still pass them — there is nothing left for either to switch, because the Yahoo fallback that used to score
    the name a second time is gone (avo 10 Nov 2026, option B).
    """
    ticker = ticker.upper()
    try:
        from RevenueChaser.core import ticker_store
        card = ticker_store.get(ticker)
        if card:
            # A stored scan card: dated by that scan, which may be days older than this report (review S5).
            return _from_card(ticker, card, "ticker_scores", _session(ticker_store.asof()),
                              "the last Asymmetric Growth Fetch")
    except Exception as exc:  # pragma: no cover - a store error is "no card", never a failed run
        logger.debug("ticker_scores %s: %s", ticker, exc)
    # No card: the name has not been scored. Said, not filled in from a vendor (#645).
    return _from_card(ticker, {}, "ticker_scores", None, "not scored by an Asymmetric Growth Fetch yet")
