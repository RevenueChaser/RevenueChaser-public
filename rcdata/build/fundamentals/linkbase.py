"""The definition linkbase of an annual report (``<ticker>-<date>_def.xml``, or embedded in the filing's schema
file, ``<ticker>-<date>.xsd``): which members stand on an axis in which table of the report.

The inline XBRL (``ixbrl.py``) gives a revenue fact its axis and member, but not whether two members belong
together: Amazon tags {Product, Service} on the income statement and seven finer members in the segment note, all
on ``ProductOrServiceAxis``, so the flat list sums to twice the revenue. The filing's definition linkbase says it:
each table of the report is one ``definitionLink`` (an XBRL "role"), and under it the axis reaches its domain and
members through ``definitionArc`` elements. Read here, per role: every locator below one of ``ixbrl.AXES``.

A member is matched to the inline XBRL's by its label (``ixbrl.label`` of the local name: the linkbase writes
``...xsd#amzn_OnlineStoresMember``, the document ``amzn:OnlineStoresMember``). A table is named by its role id, the
last path part of the role URI.
"""
from __future__ import annotations

from xml.etree import ElementTree

from . import ixbrl

SUFFIX = "_def.xml"
SCHEMA_SUFFIX = ".xsd"
#: What every XML schema declares: tells a schema file with no linkbase in it from an error page.
SCHEMA_NS = b"http://www.w3.org/2001/XMLSchema"
_LINK = "{http://www.xbrl.org/2003/linkbase}"
_XLINK = "{http://www.w3.org/1999/xlink}"


def name(listing: dict) -> str | None:
    """The file of a filing's ``index.json`` that holds its definition linkbase: the ``_def.xml`` when it lists
    one, else the largest ``.xsd`` it lists (#1066: some filers embed the linkbases in the schema file; Microsoft's
    FY2026 10-K lists no ``_def.xml`` and its ``.xsd`` holds 57 ``definitionLink``); None when it lists neither.

    Measured 18 Nov 2026 on the 5,130 stored indexes: 4,281 list a ``_def.xml``, 819 none but exactly one
    ``.xsd``, 30 neither; "the largest" only says which one when a filing ever lists two."""
    items = ((listing or {}).get("directory") or {}).get("item") or []
    names = [str(i.get("name") or "") for i in items]
    found = next((n for n in names if n.endswith(SUFFIX)), None)
    if found is not None:
        return found
    sizes = [str(i.get("size") or "") for i in items]
    schemas = [(int(size) if size.isdigit() else 0, n) for n, size in zip(names, sizes) if n.endswith(SCHEMA_SUFFIX)]
    return max(schemas, key=lambda s: s[0])[1] if schemas else None


def _local(fragment: str | None) -> str:
    """``us-gaap_ProductMember`` -> ``ProductMember``: the part after the prefix."""
    return str(fragment or "").split("_", 1)[-1]


def parse(xml: bytes | str) -> dict[tuple[str, str], list[str]]:
    """``{(axis, member label): [role id, ...]}`` of one definition linkbase: the tables in which the member stands
    on the axis (``axis`` as ``ixbrl.AXES`` names it), sorted. A file that is not XML gives {}."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return {}
    found: dict[tuple[str, str], set[str]] = {}
    for link in root.iter(_LINK + "definitionLink"):
        role = str(link.get(_XLINK + "role") or "").rstrip("/").rsplit("/", 1)[-1]
        locs = {loc.get(_XLINK + "label"): str(loc.get(_XLINK + "href") or "").rsplit("#", 1)[-1]
                for loc in link.iter(_LINK + "loc")}
        kids: dict[str, list[str]] = {}
        for arc in link.iter(_LINK + "definitionArc"):
            parent, child = locs.get(arc.get(_XLINK + "from")), locs.get(arc.get(_XLINK + "to"))
            if parent and child:
                kids.setdefault(parent, []).append(child)
        for node in kids:
            axis = ixbrl.AXES.get(_local(node))
            if not role or axis is None:
                continue
            stack, seen = list(kids[node]), set()
            while stack:
                member = stack.pop()
                if member in seen:
                    continue
                seen.add(member)
                stack += kids.get(member, [])
                found.setdefault((axis, ixbrl.label(_local(member))), set()).add(role)
    return {key: sorted(roles) for key, roles in found.items()}
