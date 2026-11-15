"""The SEC reader tool: one place that asks a model a question about a filing, for every board.

Plan: claude-coordinator ``plans/2026-11-15_1119_sec-reader-tool-plan.md`` (PR 715; avo's decisions in PRs 717, 718
and 725). The **cutting** of a filing is ``sec/forms``; this layer is the **asking**. A board declares a question
once (:mod:`questions`), the one asker sends it with one pool per provider (:mod:`asker`), and the answers are the
served table ``read_answer`` of ``sec_reads.duckdb`` (:mod:`reads`), read through ``rcdata.read.sec_reads``.

Step 1 of the plan: the tool with no real question. A board's question is its own PR (#737 first).
"""
from __future__ import annotations

#: The serving kind this layer builds (``sec_reads.duckdb``).
KIND = "sec_reads"
