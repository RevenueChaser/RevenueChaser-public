"""The one asker: every question's calls go out here, with one pool per provider.

**Caps.** EVREN 1 request at a time (``evren.MAX_WORKERS``, avo 15 Nov 2026 11:22 and 11:32), the DeepSeek API 8
(avo 10:44; coordinator PR #716). On homesrv LiteLLM keeps the same limits for every caller together (plan §3.4);
these pools keep them without the gate too, so a run behaves the same either way. The gate is a unit setting, not
code: both clients read their base URL from the environment (``RC_EVREN_BASE``, ``RC_DEEPSEEK_BASE``).

**The HTTP clients** are ``core/providers``' own, called with ``use_cache=False``: the tool keeps the answer itself
(``read_answer``), so ``llm_cache`` gets no rows from it. DeepSeek's off-peak gate is in its client
(``deepseek.peak_blocked``) and is read here once before the first call.

**One model job at a time** (plan §4, risk R2): while the Relatedness board's own model job holds its lock, the tool
refuses to start, because two askers against EVREN's cap of 1 is the HTTP 429 seen on 15 Nov 10:41 and 11:15.

**The builder lock** (plan risk R1). A run asks for at most :data:`SLICE_S` seconds and leaves the rest stale for the
next run, so a queued pass never holds the builder lock for hours. A long read runs fetch-only instead
(``python -m RevenueChaser.rcdata.build run --dataset sec/reads --no-duckdb``): that takes only its own
``rcdata_fetch_sec_reads`` lock, and the build proper is then seconds long.
"""
from __future__ import annotations

import importlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from ....core import job_lock, offpeak
from ....core.providers import deepseek, evren
from .. import base
from .questions import Input, Question

#: Requests at a time, per provider.
POOLS = {"evren": evren.MAX_WORKERS, "deepseek": 8}
MODULES = {"evren": "RevenueChaser.core.providers.evren", "deepseek": "RevenueChaser.core.providers.deepseek"}
#: The longest a run asks before it stops and leaves the rest for the next run (R1).
SLICE_S = 15 * 60.0
#: The Relatedness board's own model job (``module_relatedness.engine``); one model job at a time until it moves here.
RELATEDNESS_LOCK = "relatedness"
OK, PARTIAL, EMPTY, NO_TEXT = "ok", "partial", "empty", "no_text"
#: The errors that stop the whole run: the next call cannot do better.
_STOP = (deepseek.PeakHoursError, deepseek.DeepSeekAuthError, deepseek.DeepSeekTransientError)


@dataclass
class Job:
    question: Question
    cik: str
    input: Input
    input_hash: str


@dataclass
class Reply:
    job: Job
    status: str
    answer: dict | None
    raws: list[str] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)


def busy_problem() -> str | None:
    """Why no model read may start now (another model job runs), or None."""
    held = [pid for name, pid in job_lock.holders() if name == RELATEDNESS_LOCK]
    if held:
        return f"a Relatedness model job runs (pid {held[0]}): one model job at a time"
    return None


def _parse(q: Question, reply: str) -> dict | None:
    try:
        return q.parse(reply)
    except Exception:  # noqa: BLE001 - a reply the parser cannot read is an unusable reply, not a failed run
        return None


def _ask_one(ctx: base.RunContext, job: Job, started: float, lock: threading.Lock) -> Reply | None:
    """One company's chunks, in order; None when the run's slice ran out before it started."""
    if ctx.clock() - started > SLICE_S:
        return None
    q = job.question
    with lock:
        ctx.check_cap(q.provider)
    client = importlib.import_module(MODULES[q.provider])
    parts: list[dict] = []
    raws: list[str] = []
    missing: list[int] = []
    for i, chunk in enumerate(q.chunks(job.input.text)):
        failed = 0
        try:
            reply = client.complete(q.system, chunk, model=q.writer_model, max_tokens=q.max_tokens,
                                    use_cache=False, cik=job.cik, prompt_version=q.prompt_version)
        except _STOP:
            with lock:
                ctx.count(q.provider, calls=1, failures=1)
            raise
        except deepseek.DeepSeekError:          # EVREN's errors are its subclasses: no content, a bad status
            reply, failed = "", 1
        with lock:
            ctx.count(q.provider, calls=1, failures=failed)
        raws.append(reply)
        parsed = _parse(q, reply) if reply else None
        if parsed is None:
            missing.append(i)
        else:
            parts.append(parsed)
    if not parts:
        return Reply(job, EMPTY, None, raws, missing)
    return Reply(job, PARTIAL if missing else OK, q.merge(parts), raws, missing)


def ask(ctx: base.RunContext, jobs: list[Job]) -> tuple[list[Reply], BaseException | None, int]:
    """Ask every job: ``(replies, the error that stopped the run or None, jobs left unasked)``.

    The replies that came back before a stop are returned with it, so the caller stores them before it raises: a
    paid answer is never thrown away.
    """
    if not jobs:
        return [], None, 0
    busy = busy_problem()
    if busy:
        raise base.SourceError(busy)
    if any(j.question.provider == "deepseek" for j in jobs) and deepseek.peak_blocked():
        raise base.SourceError(f"DeepSeek is off-peak only: next window {offpeak.next_off_peak():%Y-%m-%d %H:%M} UTC")
    started = ctx.clock()
    lock = threading.Lock()
    replies: list[Reply] = []
    stop: BaseException | None = None
    by_provider: dict[str, list[Job]] = {}
    for j in jobs:
        by_provider.setdefault(j.question.provider, []).append(j)
    pools = {p: ThreadPoolExecutor(max_workers=POOLS[p]) for p in by_provider}
    try:
        futs = [pools[p].submit(_ask_one, ctx, j, started, lock) for p, js in by_provider.items() for j in js]
        for f in as_completed(futs):
            try:
                r = f.result()
            except BaseException as e:  # noqa: BLE001 - Paused, CapReached and the provider stops end the run
                stop = stop or e
                for g in futs:
                    g.cancel()
                continue
            if r is not None:
                replies.append(r)
    finally:
        for pool in pools.values():
            pool.shutdown(wait=True, cancel_futures=True)
    return replies, stop, len(jobs) - len(replies)
