"""The SEC reader tool: one place that asks a model a question about a filing, for every board.

Plan: claude-coordinator ``plans/2026-11-15_1119_sec-reader-tool-plan.md`` (PR 715; avo's decisions in PRs 717, 718
and 725). The **cutting** of a filing is ``sec/forms``; this layer is the **asking**. A question is declared once,
by the service (:mod:`questions`; no board registers anything), the one asker sends it with one pool per provider
(:mod:`asker`), and the answers are the served table ``read_answer`` of ``sec_reads.duckdb`` (:mod:`reads`), read
through ``rcdata.read.sec_reads``.

Each question is its own PR. Registered: ``debt.note`` (#737, :mod:`debt_note`), imported at the end of this file so
every process that reads answers knows its prompt version. ``company.profile`` and ``business.locate`` are declared
in :mod:`company_profile` and not registered (their cutover is the owner's word).
"""
from __future__ import annotations

#: The serving kind this layer builds (``sec_reads.duckdb``).
KIND = "sec_reads"

from . import debt_note  # noqa: E402,F401 - registers debt.note; after KIND, which reads.py imports from here
