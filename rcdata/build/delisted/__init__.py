"""The delisted serving layer (#1219; avo, 20 Nov 2026: "Delistedler icin ayri katman.").

``prices.duckdb`` holds **today's** universe and nothing else (``prices.universe``, avo's rule of 4 Nov 2026), so no
company that delisted is in it. That is a survivorship bias the boards do not feel -- they show what is listed now --
and that anything measuring the past does: a backtest, AG-score validation or a forecast-ledger hit rate comes out
better than reality with nothing warning about it (``docs/data_architecture.md``, issue #441).

This kind is the reversal, in a file of its own: ``delisted.duckdb``, built from the CRSP history the ``wrds/prices``
fetch already wrote to disk (``parquet/wrds/prices/dsf`` and ``.../stkdelists``). **No new provider call, no new WRDS
login.** Nothing is merged into ``price_bar_daily``: a widened served universe would change what every board reads,
so a reader unions the two deliberately.

**Keyed on PERMNO.** Every row's ``security_id`` is ``permno:<PERMNO>``, never a ticker and never a live security id:
a dead company's ticker and a live one's are two securities (ticker reuse), so no reader may join on ticker alone.
``delisted_security`` carries the Compustat ``gvkey:iid`` and the CIK where the link exists, and
``delisted_security_symbol`` carries each ticker with the session range it was in use.

**Append-only.** The history only grows, so the ordinary shrink guard (``serving.MAX_SHRINK``) is the whole rule and
no table of this kind is ever in ``SHRINKS_BY_CHOICE``.
"""
from __future__ import annotations

#: The serving kind this layer builds (``delisted.duckdb``).
KIND = "delisted"
