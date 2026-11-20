"""Index membership for the boards — the one place a board asks ``ticker -> index``.

The badges on the cards (``annotate_cards``, ``index_for``), the index list of the shared filter
(``filter_labels``) and ``load_index`` read the identity spine through ``rcdata.read`` (build plan PR 6):

  - ``sp500``, ``sp400``, ``sp600``, ``ndx``  the spine's current members, voted from the index funds' daily
    holdings files (``funds/index_holdings``; ``rcdata.read.membership``)
  - ``nasdaq``                               the spine's listed names (Tier A and B) on Nasdaq, as the spine's
    ``index_constituents`` bridge view has it

No source the spine reads carries the Dow Jones, so on the spine no card carries it and the filter does not offer
it. Each slug with a label in ``LABELS`` shows under that label; a slug without one (``sp400``, ``ndx`` today) is
read by ``load_index`` but shows no badge, so the filter is unchanged by the move.

The old store's ``index_constituents`` path (the weekly Unusual Whales lists) is no longer read here (#642 PR 6): no
spine file reads as no membership. This module only reads.
"""
from __future__ import annotations

# slug -> display label for every stored slug (#214). Display order matters: the badge shows the first match,
# and the filter lists the labels in this order. A SmallCap 600 member listed on Nasdaq reads "S&P SmallCap 600".
LABELS: dict[str, str] = {
    "sp500": "S&P 500",
    "dow": "Dow Jones",
    "sp600": "S&P SmallCap 600",
    "nasdaq": "Nasdaq Composite",
}
# The filter's short text for a label whose full name misleads (Nasdaq Composite ~ listed on the exchange).
SHORT_LABELS: dict[str, str] = {"Nasdaq Composite": "Nasdaq-listed"}

# The slug of the listed-on-Nasdaq names, which the spine derives from the exchange rather than reads from a fund file.
NASDAQ = "nasdaq"


def _spine_members(listed: list[dict] | None = None) -> dict[str, set[str]]:
    """``{slug: tickers}`` on the spine: each index's current members, and ``nasdaq`` from the listed names."""
    from . import spine_reads
    out: dict[str, set[str]] = {}
    for m in spine_reads.membership():
        out.setdefault(m["index_slug"], set()).add(str(m["ticker"]).upper())
    nasdaq = _listed_on_nasdaq(spine_reads.universe(("A", "B")) if listed is None else listed)
    if nasdaq:
        out.setdefault(NASDAQ, set()).update(nasdaq)    # adds to a fund-file ``nasdaq``, never replaces it (review N1)
    return out


def _listed_on_nasdaq(listed: list[dict]) -> set[str]:
    return {str(r["ticker"]).upper() for r in listed if r.get("exchange") == "Nasdaq"}


def load_index(slug: str) -> set[str] | None:
    """The current members of ``slug`` (upper-cased tickers), or None when it has none.

    The spine's fund files' current members (``nasdaq``: the listed Nasdaq names); ``dow`` is always None."""
    from . import spine_reads
    if slug == NASDAQ:
        tickers = _listed_on_nasdaq(spine_reads.universe(("A", "B")))
    else:
        tickers = {str(m["ticker"]).upper() for m in spine_reads.membership(slug)}
    return tickers or None


def _index_memberships(indexes: dict[str, set[str]]) -> dict[str, list[str]]:
    """Invert ``{slug -> tickers}`` into ``{ticker -> [labels]}`` (display order)."""
    memberships: dict[str, list[str]] = {}
    for slug, label in LABELS.items():
        for t in indexes.get(slug, set()):
            memberships.setdefault(t, []).append(label)
    return memberships


def load_registry() -> dict | None:
    """``{ticker: {index: [labels], name, sector}}`` of every ticker with at least one labelled index, the labels in
    ``LABELS`` order; None when there is none. The name and sector are the spine's."""
    from . import spine_reads
    listed = spine_reads.universe(("A", "B"))
    by = {str(r["ticker"]).upper(): r for r in listed}
    members = _spine_members(listed)
    out: dict[str, dict] = {}
    for slug, label in LABELS.items():
        for t in sorted(members.get(slug, ())):
            row = by.get(t) or {}
            out.setdefault(t, {"index": [], "name": row.get("name") or "",
                               "sector": row.get("sector") or ""})["index"].append(label)
    return out or None


def offered_slugs() -> list[str]:
    """The slugs the shared filter offers, in ``LABELS`` display order: those some stored name carries."""
    have = set(_spine_members())
    return [slug for slug in LABELS if slug in have]


def filter_labels(slugs: list[str] | None = None) -> list[str]:
    """The index labels the shared filter offers, in display order (K1, #214).

    A label is listed only while some name carries it, so the filter never offers an index no card can carry (the Dow
    Jones, which the spine has no source for). ``slugs`` is for a caller that has already read
    ``offered_slugs()`` and must not read the spine twice."""
    return [LABELS[slug] for slug in (offered_slugs() if slugs is None else slugs) if slug in LABELS]


# --- the filter's "Index" explanation (#266) ----------------------------------
#
# The text lived in ``core/static/rc_filters.js``'s ``explain()`` defaults, and the spine cutover (#245) made it
# wrong in three places at once: it named the Dow Jones, credited Unusual Whales, and said the lists were cached in
# ``index_constituents``. A hard-coded sentence cannot follow the registry, so the text is built here from the slugs
# the filter actually offers and passed to the component as ``meta.explain.index``
# (``reporting_common.filters_meta``). A label the filter does not offer therefore cannot be described, which
# ``core/tests/test_index_explain.py`` pins.

#: Slugs whose membership the spine votes from the index funds' own daily holdings files (``funds/index_holdings``).
FUND_FILE_SLUGS = ("sp500", "sp400", "sp600", "ndx")
#: The sentence after the labels: where the membership comes from, and why an index may be absent.
EXPLAIN_SOURCE = ("Source: the identity spine; an index shows here once some name carries it.")
#: The note the component styles as its "now" line, about what the per-label counts mean.
EXPLAIN_COUNTS = ("Counts are names <b>on this board</b> that pass your other filters, not the size of the index.")


def _esc(text: str) -> str:
    """The display labels are our own constants, but they carry ``&`` (S&P): escape as the page needs."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bold_list(labels: list[str]) -> str:
    """``<b>a</b>``, ``<b>a</b> and <b>b</b>``, ``<b>a</b>, <b>b</b> and <b>c</b>``."""
    bold = [f"<b>{_esc(l)}</b>" for l in labels]
    if len(bold) <= 1:
        return "".join(bold)
    return ", ".join(bold[:-1]) + " and " + bold[-1]


def index_explain(slugs: list[str] | None = None) -> str:
    """The shared filter's "Index" explanation, as HTML, for the slugs the filter offers.

    Each offered slug is described once: a fund-file index as a constituent list, ``nasdaq`` as the exchange it
    means (its short label reads "Nasdaq-listed", because "Nasdaq Composite" would read as the index). A slug the
    filter does not offer is named nowhere, so the Dow Jones leaves the text on its own as soon as it leaves the
    filter. Empty of labels when the spine holds no membership at all — the counts note still stands.
    """
    offered = list(offered_slugs() if slugs is None else slugs)
    display = {slug: SHORT_LABELS.get(LABELS[slug], LABELS[slug]) for slug in offered if slug in LABELS}
    parts: list[str] = []
    funds = [display[slug] for slug in offered if slug in FUND_FILE_SLUGS and slug in display]
    if funds:
        parts.append(_bold_list(funds) + (" are index constituents" if len(funds) > 1 else " is an index constituent")
                     + ", read from the index funds' daily holdings files")
    if NASDAQ in display:
        parts.append(f"{_bold_list([display[NASDAQ]])} means listed on the Nasdaq exchange (not the Nasdaq-100)")
    head = ("; ".join(parts) + ". ") if parts else ""
    return f"{head}{EXPLAIN_SOURCE}<div class='rcf-now'>{EXPLAIN_COUNTS}</div>"


def index_for(ticker: str, registry: dict | None = None) -> list[str]:
    reg = registry if registry is not None else (load_registry() or {})
    return list(reg.get((ticker or "").upper(), {}).get("index", []))


def annotate_cards(cards: list[dict], registry: dict | None = None) -> list[dict]:
    """Set ``card["index"]`` (list of labels) for each card, cache-first."""
    reg = registry if registry is not None else (load_registry() or {})
    for c in cards:
        c["index"] = list(reg.get((c.get("ticker") or "").upper(), {}).get("index", []))
    return cards


def _main(argv: list[str]) -> int:
    """Read the registry and print its size (the weekly ``--refresh`` step went with raw.duckdb, #860)."""
    reg = load_registry() or {}
    print(f"registry: {len(reg)} tickers (the identity spine)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
