"""What a paid model's answer costs, in one place (#166 item 3).

The money half of the spend record needs a figure per answer, and this module is the only place that holds one.
Two sources, in this order, because only the first is the provider's own number:

1. **A published per-token price**, when the box has been told one: ``RC_LLM_PRICES`` is a JSON object
   ``{"<model>": [usd per million input tokens, usd per million output tokens]}``. The table in this file is
   **empty on purpose** -- the names in :mod:`core.llm_writers` are the aliases of our own LiteLLM gate
   (``deepseek-v4-flash``), not a provider's published model, so no published price can be attached to one here
   without inventing it. Where avo knows the gate's mapping, the variable states it and the ledger's USD becomes
   the provider's unit.
2. **The measured cost of a call**, :data:`MEASURED_USD_PER_CALL`, which is what the repository already knows.
   DeepSeek Flash: the 10 Nov 2026 pilot wrote 400 names in 668 calls for about 1 USD, so 0.0018 USD a call
   (review of PR #557 replaced the guessed 0.006 with it). ``module_relatedness.config.EST_USD_PER_CALL`` reads
   this number, so the per-run cap and the day ledger cannot drift apart.

**So the ledger's USD is a measured estimate until a per-token price is set, and never the provider's invoice.**
That is said here, on the day cap's refusal, and in ``docs/llm_spend.md``; a number this honest is worth more than
a precise-looking one that was guessed (``rcdata/caps.py``: each number names its source).

Tokens are recorded whatever the price is, so a later price can re-cost a day from the ledger's own rows.

A paid writer with no figure at all would spend money the day cap could never see, so
``core/tests/test_llm_prices.py`` fails one: every paid model in :mod:`core.llm_writers` has a row here.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

#: ``{"<model>": [usd/Mtok in, usd/Mtok out]}``, the gate's models priced as their provider publishes them.
PRICES_ENV = "RC_LLM_PRICES"

#: Per-million-token prices known in the code. Empty: see the module docstring (the names are our gate's aliases).
PER_MTOK: dict[str, tuple[float, float]] = {}

#: USD a call, measured on our own prompts. Each entry names what measured it.
MEASURED_USD_PER_CALL: dict[str, float] = {
    # 400 names in 668 calls for about 1 USD, the 10 Nov 2026 pilot (#712, review of PR #557). A chunked filing is
    # several calls, each counted.
    "deepseek-v4-flash": 0.0018,
}

#: A millionth of a USD: the ledger's unit (``rcdata.ops.provider_spend_daily``).
MICROS = 1_000_000


def per_mtok(model: str) -> tuple[float, float] | None:
    """``(usd per million input tokens, output tokens)`` of ``model``, from ``RC_LLM_PRICES`` or the table.

    Read at call time, so setting the variable needs no restart. Anything that is not a pair of non-negative
    numbers is ignored with a warning and the measured figure is used instead: money must never be counted
    against a half-read price.
    """
    table = _loaded(os.getenv(PRICES_ENV) or "")
    if table is not None:
        if not isinstance(table, dict):
            logger.warning("%s is not a JSON object of {model: [in, out]}; the measured figures are used instead",
                           PRICES_ENV)
        elif model in table:
            pair = table[model]
            try:
                got = (float(pair[0]), float(pair[1]))
            except (TypeError, ValueError, IndexError, KeyError):
                got = None
            if got is not None and got[0] >= 0 and got[1] >= 0:
                return got
            logger.warning("%s does not price %s as two non-negative numbers; the measured figure is used instead",
                           PRICES_ENV, model)
    return PER_MTOK.get(model)


def _loaded(raw: str):
    """``raw`` as JSON, or None when it is empty or not JSON at all (then the table in this file is the answer)."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        logger.warning("%s is not JSON; the measured figures are used instead", PRICES_ENV)
        return None


def measured_usd_per_call(model: str) -> float | None:
    """The measured USD a call of ``model`` costs, or None when nothing measured it."""
    return MEASURED_USD_PER_CALL.get(model)


def micros(model: str, *, calls: int = 1, tokens_in: int = 0, tokens_out: int = 0) -> int | None:
    """What this much of ``model`` cost, in millionths of a USD, or None when the model has no figure.

    The token price wins when there is one **and** the answer reported its tokens; otherwise the measured cost of
    a call. Rounded to the nearest micro-USD, so a day's sum is exact in the ledger's unit.
    """
    price = per_mtok(model)
    if price is not None and (tokens_in or tokens_out):
        usd = (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000
        return round(usd * MICROS)
    per_call = measured_usd_per_call(model)
    if per_call is None:
        return None
    return round(per_call * calls * MICROS)


def unit(model: str) -> str:
    """How the figure of ``model`` was arrived at, for a page, a log line or a refusal message."""
    if per_mtok(model) is not None:
        return "published per-token price"
    return "measured cost a call" if measured_usd_per_call(model) is not None else "no price"
