"""One registry of the LLM jobs (#404): which provider and model runs each of them.

**Decision (b), one writer per job** (avo, 4 Nov 2026 19:45): every job that calls a model has its own
``(provider, model)`` pair, chosen on the Settings page. The pair can change at any time; the next run of that
job uses the new pair and a running job is not affected.

The writers themselves are :mod:`core.llm_writers` — that stays the one registry of providers, models,
credential names and the paid flag. This module adds the second half: the list of jobs and, per job, the two
settings that name its pair.

A job's default is EVREN, the owner's own gate, with no fee (avo: "Varsayılan her işte EVREN kalır"). A move to a
paid writer is only ever avo's own choice on the Settings page; nothing here picks one. A job may name an
``env`` switch that still sets its default on a box (the SEC reading service's ``RC_SEC_READS_PROVIDER``,
avo 16 Nov 2026); an unknown value there is ignored and the job stays on EVREN.

The exceptions a job's code catches are re-exported here, so a job module names no provider: EVREN's errors
subclass DeepSeek's (``core.providers.evren``), so one ``except`` covers both writers.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from revenuechaser.core import llm_writers, settings_store

#: The shared exception surface of a writer call. EVREN's classes subclass these, so a job catches these names
#: and names no provider. ``PeakHours`` is raised by the paid writer's off-peak gate only, and
#: ``BudgetSpent`` by its money gate (``core.llm_spend``, #166); both mean nothing was sent. They are resolved on
#: first use (PEP 562), so reading the registry — the Settings card does, on every page — never imports a chat
#: client and its HTTP stack.
_ERRORS = {"Error": "DeepSeekError", "AuthError": "DeepSeekAuthError",
           "TransientError": "DeepSeekTransientError", "PeakHours": "PeakHoursError",
           "BudgetSpent": "BudgetSpentError"}


def __getattr__(name: str):
    if name in _ERRORS:
        from revenuechaser.core.providers import deepseek
        return getattr(deepseek, _ERRORS[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

#: The settings board the pairs live on.
BOARD = "llm_writers"


@dataclass(frozen=True)
class Job:
    """One job that calls a model."""

    id: str                 #: ``relatedness.profiles``; the settings keys are built from it
    label: str              #: what the Settings card calls it
    where: str              #: the module that makes the call, for the card's second line
    env: str = ""           #: an environment switch that still sets this job's default provider

    @property
    def key(self) -> str:
        """The settings key prefix: ``relatedness.profiles`` -> ``RELATEDNESS_PROFILES``."""
        return self.id.replace(".", "_").upper()

    @property
    def writer_key(self) -> str:
        return f"{self.key}_WRITER"

    @property
    def model_key(self) -> str:
        return f"{self.key}_MODEL"


JOBS: dict[str, Job] = {
    j.id: j for j in (
        Job("relatedness.profiles", "Relatedness · company profiles", "module_relatedness/profiles.py"),
        # Theme naming had no picker and a fixed paid import until #404 (``module_relatedness/naming.py``).
        Job("relatedness.naming", "Relatedness · theme naming", "module_relatedness/naming.py"),
        # The SEC reading service's three questions. One switch set all three before #404; it still sets their
        # default, so a box that exports it keeps running the way it did.
        Job("sec_reads.business.locate", "SEC reads · business.locate",
            "rcdata/build/sec_reads/company_profile.py", env="RC_SEC_READS_PROVIDER"),
        Job("sec_reads.company.profile", "SEC reads · company.profile",
            "rcdata/build/sec_reads/company_profile.py", env="RC_SEC_READS_PROVIDER"),
        Job("sec_reads.debt.note", "SEC reads · debt.note",
            "rcdata/build/sec_reads/debt_note.py", env="RC_SEC_READS_PROVIDER"),
        # The News board's hourly reading of the headline flow (#1234, avo 21 Nov 2026). EVREN by default like
        # every job here; the pass itself refuses to run on a paid writer unless it is started with
        # ``allow_paid``, because an hourly pass is a standing cost and a paid run needs avo's own word.
        Job("news.reading", "News · hourly headline reading", "module_news/reading.py"),
    )
}


def get(job_id: str) -> Job:
    if job_id not in JOBS:
        raise ValueError(f"unknown LLM job {job_id!r}; one of {', '.join(JOBS)}")
    return JOBS[job_id]


def default_provider(job_id: str) -> str:
    """EVREN, or the job's own environment switch when it names a writer the registry knows."""
    job = get(job_id)
    if job.env:
        chosen = os.environ.get(job.env, "").strip().lower()
        if chosen in llm_writers.WRITERS:
            return chosen
    return llm_writers.DEFAULT


def default_model(job_id: str) -> str:
    return llm_writers.get(default_provider(job_id)).models[0]


def setting_fields() -> list[dict]:
    """The two settings each job needs, as plain data: ``key``, ``kind``, ``default``, ``choices``, ``label``.

    The Settings page (:mod:`core.board_settings`) turns these into its own ``Setting`` objects. This module
    names that one not at all, not even inside a call: it reaches every board module to collect that board's
    specs, and a job module on that path would make CI run the whole suite for any board change, because the
    root conftest imports the SEC reading service (``scripts/select_tests.py``).
    """
    out: list[dict] = []
    for job in JOBS.values():
        out.append({"key": job.writer_key, "kind": "text",
                    "default": (lambda j=job.id: default_provider(j)),
                    "choices": (lambda: tuple(llm_writers.WRITERS)),
                    "label": f"{job.label} — provider"})
        out.append({"key": job.model_key, "kind": "text",
                    "default": (lambda j=job.id: default_model(j)),
                    "choices": llm_writers.all_models,
                    "label": f"{job.label} — model"})
    return out


def rules(v: dict) -> list[str]:
    """Per job: the model belongs to the chosen provider, and a provider with no credential cannot be chosen.

    The rules run over the merged values of every job (the Settings page's own ``validate``), so the credential check is
    on a provider a job was **moved to**, not on the default it was left at: a box without the key would
    otherwise refuse a save that does not touch that job at all.
    """
    out = []
    for job in JOBS.values():
        slug, model = v.get(job.writer_key), v.get(job.model_key)
        writer = llm_writers.WRITERS.get(slug)
        if writer is None:
            continue
        if model not in writer.models:
            out.append(f"{job.model_key} must be one of {slug}'s models: {', '.join(writer.models)}; got {model}")
        absent = llm_writers.missing_text(slug)
        if absent and slug != default_provider(job.id):
            out.append(f"{job.writer_key} {slug} cannot be chosen: {absent}")
    return out


def pair(job_id: str) -> tuple[str, str]:
    """``(provider, model)`` the job runs with.

    A stored pair that does not fit — an unknown provider, or a model saved for another provider — reads the
    job's own default rather than an invalid pair (#360 review S2). The saved values come from
    :mod:`core.settings_store`, the same place the Settings page reads them from.
    """
    job = get(job_id)
    values = settings_store.overrides(BOARD)
    slug = values.get(job.writer_key)
    if slug not in llm_writers.WRITERS:
        slug = default_provider(job_id)
    models = llm_writers.get(slug).models
    model = values.get(job.model_key)
    return slug, (model if model in models else models[0])


def client(job_id: str):
    """The chat module the job calls: ``complete(system, user, ...)`` and ``MODEL``."""
    return llm_writers.client(pair(job_id)[0])


def options() -> list[dict]:
    """One row per job for the Settings card: the job, its chosen pair, and every writer it could run on.

    ``paid`` marks a fee; ``available``/``missing`` grey a writer whose credential is absent, by variable NAME
    only, never a value.
    """
    writers = llm_writers.options()
    out = []
    for job in JOBS.values():
        slug, model = pair(job.id)
        out.append({
            "job": job.id, "label": job.label, "where": job.where,
            "provider": slug, "model": model,
            "paid": llm_writers.get(slug).paid,
            "writers": [dict(w) for w in writers],
            "writer_key": job.writer_key, "model_key": job.model_key,
        })
    return out
