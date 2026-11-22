"""The paid providers' money: the record of what was spent, and the day cap that refuses a call past it (#166).

Two halves, and they are one module because the gate reads exactly what the record writes.

**The record.** After a paid answer, :func:`record` adds its calls, its tokens and its cost to
``rcdata.ops.provider_spend_daily`` -- the paid twin of ``provider_calls_daily``, which counts the metered
providers' requests (``core/providers/spend.py``) and knows nothing about money. The cost comes from
:mod:`core.llm_prices`, so one file says what an answer costs. Until a per-token price is set there the USD is a
**measured estimate, not the provider's invoice**, and every place that shows or refuses on it says so.

Writes go straight through, unlike the metered counter's buffer: a paid answer takes seconds and there are
hundreds of them in a run, not thousands a minute, so one small write each costs nothing and the day's figure is
true the instant the call ends -- which is what a gate reading it in the next breath needs.

**The gate.** :func:`refusal` is asked before a paid request leaves the machine (``core/providers/deepseek.py``,
after its cache and its off-peak gate), and the caller stops with ``BudgetSpentError`` when it answers. It is the
money twin of the builder's day caps (``rcdata/caps.at_cap``) and of the off-peak gate: nothing is queued and
nothing sleeps, because what is spent is spent until the New York day turns.

The cap is the **box's** money for the whole New York day, over every paid job and every run, which is what the
per-run ceiling the Relatedness board already had (``module_relatedness.config.USD_CAP``) cannot see: six runs of
25 USD each are 150 USD and no run was over its own cap. The default is that same 25 USD a day, so a full
profile round (~14 USD, #712) fits in one day and a second round waits for the next.

``RC_LLM_USD_DAY_CAP`` sets it: a number is the cap in USD, ``0`` refuses every paid call, and ``off`` (or
``none``, or a negative number) is no cap at all.

**Fail closed.** When the ledger cannot be read, the paid call is refused: a cap that cannot be checked is not a
cap, and every job's default writer is EVREN, which costs nothing (``core.llm_jobs``). So an unreachable
``ops.sqlite`` stops the money, not the work.

**Rollback without a revert:** ``RC_LLM_SPEND=0``. It stops the writes, and with them the gate -- a gate reading a
counter nobody writes would pass every call once and refuse for the rest of the day, or refuse nothing, depending
on what was already written, which is worse than no gate. One switch, both halves, as the record-and-gate pair
should be.
"""
from __future__ import annotations

import logging
import os

from revenuechaser.core import llm_prices

logger = logging.getLogger(__name__)

#: ``RC_LLM_SPEND=0``: write nothing and refuse nothing (the rollback). Any other value, or unset, is on.
ENV = "RC_LLM_SPEND"
#: The day cap in USD; ``off`` / ``none`` / a negative number is no cap, ``0`` refuses every paid call.
CAP_ENV = "RC_LLM_USD_DAY_CAP"
#: The default day cap: the ceiling avo already set for one Relatedness run (``RC_RELATEDNESS_USD_CAP``), now
#: over the day and every paid job. Stated in ``docs/llm_spend.md`` and checked against it by
#: ``core/tests/test_doc_constants.py``.
DEFAULT_DAY_CAP_USD = 25.0
_OFF_WORDS = {"off", "none", "no", ""}


def on() -> bool:
    """Whether the record is written and the gate holds, read at call time (so the switch needs no restart)."""
    return (os.getenv(ENV) or "").strip() != "0"


def day_cap_usd() -> float | None:
    """The day cap in USD, or None for no cap. An unreadable value falls back to the default, not to no cap."""
    raw = (os.getenv(CAP_ENV) or "").strip()
    if not raw:
        return DEFAULT_DAY_CAP_USD
    if raw.lower() in _OFF_WORDS:
        return None
    try:
        cap = float(raw)
    except ValueError:
        logger.warning("%s is not a number or %s; the default %.2f USD a day holds",
                       CAP_ENV, "/".join(sorted(w for w in _OFF_WORDS if w)), DEFAULT_DAY_CAP_USD)
        return DEFAULT_DAY_CAP_USD
    return None if cap < 0 else cap


def _ops():
    """``rcdata.ops``, imported on demand (reading this module may not pull the store's stack), or None."""
    try:
        from revenuechaser.rcdata import ops
        return ops
    except Exception:                                   # noqa: BLE001 - never the reason a job dies
        logger.warning("the spend ledger is not reachable", exc_info=True)
        return None


def spent_today_micros(provider: str | None = None) -> int | None:
    """Today's paid spend in millionths of a USD, or **None when the ledger could not be read** (the gate's
    fail-closed case). ``provider`` is None for the box's whole paid spend, which is what the cap is about."""
    ops = _ops()
    if ops is None:
        return None
    try:
        return int(ops.spend_micros_today(provider))
    except Exception:                                   # noqa: BLE001 - a locked store is not a job's failure
        logger.warning("today's paid spend could not be read from the ledger", exc_info=True)
        return None


def spent_today_usd(provider: str | None = None) -> float | None:
    micros = spent_today_micros(provider)
    return None if micros is None else micros / llm_prices.MICROS


def refusal(model: str | None = None) -> str | None:
    """Why a paid call must not be made now, or None when it may be. The one gate every paid caller asks.

    ``model`` only sharpens the message with how its figure is arrived at; the cap itself is the box's.
    """
    if not on():
        return None
    cap = day_cap_usd()
    if cap is None:
        return None
    spent = spent_today_micros()
    if spent is None:
        return (f"the paid-call day cap of {cap:.2f} USD cannot be checked: the spend ledger could not be read, "
                f"so the call is refused ({ENV}=0 turns the record and this gate off)")
    cap_micros = round(cap * llm_prices.MICROS)
    if cap_micros <= 0:
        return f"the paid-call day cap is 0 USD ({CAP_ENV}=0): no paid call is made"
    if spent >= cap_micros:
        how = f", {llm_prices.unit(model)}" if model else ""
        return (f"the paid-call day cap is spent: {spent / llm_prices.MICROS:.2f} of {cap:.2f} USD today"
                f"{how}. It frees at the turn of the New York day; {CAP_ENV} raises it, off removes it")
    return None


def at_cap(model: str | None = None) -> bool:
    """Whether :func:`refusal` would refuse, for a caller that wants the fact and not the sentence."""
    return refusal(model) is not None


def record(provider: str, model: str, *, calls: int = 1, tokens_in: int = 0, tokens_out: int = 0) -> None:
    """Add a paid answer to the ledger. Never raises: a record may not be the reason an answer is lost.

    A model with no figure in :mod:`core.llm_prices` is still recorded, with its tokens and ``usd_micros`` 0, and
    warned about: the call happened, and a row with the tokens can be re-costed once a price is known, while no
    row at all cannot. ``core/tests/test_llm_prices.py`` keeps a paid model from reaching that state.
    """
    if not on() or not (calls or tokens_in or tokens_out):
        return
    micros = llm_prices.micros(model, calls=calls, tokens_in=tokens_in, tokens_out=tokens_out)
    if micros is None:
        logger.warning("no price for the paid model %r: its tokens are recorded and its cost is not (#166)", model)
        micros = 0
    ops = _ops()
    if ops is None:
        return
    try:
        ops.count_spend(provider, model, calls=calls, tokens_in=tokens_in, tokens_out=tokens_out,
                        usd_micros=micros)
    except Exception:                                   # noqa: BLE001 - as above
        logger.warning("the paid spend of %s/%s was not recorded", provider, model, exc_info=True)


def tokens_of(usage) -> tuple[int, int]:
    """``(prompt tokens, completion tokens)`` of an OpenAI-shaped ``usage`` object, zeros for anything else."""
    if not isinstance(usage, dict):
        return 0, 0
    def n(key: str) -> int:
        try:
            return max(0, int(usage.get(key) or 0))
        except (TypeError, ValueError):
            return 0
    return n("prompt_tokens"), n("completion_tokens")
