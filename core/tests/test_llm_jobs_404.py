"""#404 One writer per LLM job (decision (b), avo 4 Nov 2026 19:45), chosen on the Settings page.

- Every LLM job is in one registry (``core.llm_jobs.JOBS``), and the writers stay in one registry
  (``core.llm_writers.WRITERS``) that now lives in ``core`` because every job reads it.
- A job's default writer is EVREN, which has no fee; nothing here moves a job to a paid writer.
- The SEC reading service's own switch still sets its three jobs' default, so a box that exports it is unchanged.
- The pair is two text settings per job on the ``llm_writers`` board, with #360's rules: a model outside the
  chosen provider's list is refused, and a provider whose credential is absent cannot be saved (named by
  variable NAME, never a value).
- A job module names no provider: ``naming.py``'s fixed DeepSeek import is gone and the exceptions it catches
  come from the registry.

Offline: no module is called, only the registry is read.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from RevenueChaser.core import board_settings, llm_jobs, llm_writers, settings_store

REPO = Path(__file__).resolve().parents[2]
KEY = "LITELLM_RC_KEY"


# ── the registry ────────────────────────────────────────────────────────────

def test_every_llm_job_the_repo_runs_is_in_the_registry():
    assert set(llm_jobs.JOBS) == {
        "relatedness.profiles", "relatedness.naming",
        "sec_reads.business.locate", "sec_reads.company.profile", "sec_reads.debt.note",
    }
    for job in llm_jobs.JOBS.values():
        assert (REPO / job.where).exists(), f"{job.id} names a module that is not here: {job.where}"
        assert job.label and job.writer_key.endswith("_WRITER") and job.model_key.endswith("_MODEL")


def test_the_writers_are_one_registry_in_core():
    assert (REPO / "core" / "llm_writers.py").exists()
    assert not (REPO / "module_relatedness" / "writers.py").exists()   # no second copy
    assert llm_writers.DEFAULT == "evren" and set(llm_writers.WRITERS) == {"evren", "deepseek"}


def test_no_module_still_imports_the_writers_registry_from_module_relatedness():
    """The move left two relative imports behind (``from . import engine, writers``), which CI caught as an
    ImportError on every test that loads the Relatedness CLI. One grep keeps the move complete."""
    bad = []
    for path in REPO.rglob("*.py"):
        if {".git", ".store", ".cache"} & set(path.parts):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"^\s*from\s+\.*\s*import\s.*\bwriters\b", line) or \
               re.search(r"module_relatedness\s+import\s.*\bwriters\b", line):
                bad.append(f"{path.relative_to(REPO)}:{n}: {line.strip()}")
    assert bad == []


def test_an_unknown_job_is_named_not_guessed():
    with pytest.raises(ValueError, match="unknown LLM job"):
        llm_jobs.get("relatedness.nope")


# ── the defaults ────────────────────────────────────────────────────────────

def test_every_job_defaults_to_evren_and_no_job_defaults_to_a_paid_writer(monkeypatch):
    monkeypatch.delenv("RC_SEC_READS_PROVIDER", raising=False)
    for job_id in llm_jobs.JOBS:
        provider, model = llm_jobs.pair(job_id)
        assert provider == "evren", job_id
        assert model == "evren-deepseek-v4.1-flash", job_id
        assert llm_writers.get(provider).paid is False, job_id


def test_the_sec_switch_still_sets_its_three_jobs_default(monkeypatch):
    monkeypatch.setenv("RC_SEC_READS_PROVIDER", "deepseek")
    assert llm_jobs.pair("sec_reads.debt.note") == ("deepseek", "deepseek-v4-flash")
    assert llm_jobs.pair("sec_reads.company.profile")[0] == "deepseek"
    # It is the SEC jobs' switch only: the Relatedness jobs are untouched by it.
    assert llm_jobs.pair("relatedness.naming")[0] == "evren"
    assert llm_jobs.pair("relatedness.profiles")[0] == "evren"


def test_an_unreadable_switch_value_leaves_the_job_on_evren(monkeypatch):
    for bad in ("", "  ", "grok", "deepseek-v4-flash"):
        monkeypatch.setenv("RC_SEC_READS_PROVIDER", bad)
        assert llm_jobs.pair("sec_reads.debt.note")[0] == "evren", bad


# ── the settings ────────────────────────────────────────────────────────────

def test_the_board_holds_two_text_settings_for_every_job():
    assert llm_jobs.BOARD in board_settings.boards()
    specs = {f["key"]: f for f in board_settings.describe(llm_jobs.BOARD)}
    for job in llm_jobs.JOBS.values():
        assert specs[job.writer_key]["kind"] == "text"
        assert set(specs[job.writer_key]["choices"]) == set(llm_writers.WRITERS)
        assert specs[job.model_key]["kind"] == "text"
        assert "evren-deepseek-v4.1-flash" in specs[job.model_key]["choices"]


def test_a_model_of_another_provider_is_refused(monkeypatch):
    monkeypatch.setenv(KEY, "sentinel-404-key")
    job = llm_jobs.JOBS["relatedness.naming"]
    msgs = board_settings.validate(llm_jobs.BOARD,
                                   {job.writer_key: "evren", job.model_key: "deepseek-v4-flash"})
    assert any(job.model_key in m and "evren's models" in m for m in msgs)
    assert board_settings.validate(llm_jobs.BOARD,
                                   {job.writer_key: "evren",
                                    job.model_key: "evren-deepseek-v4.1-flash"}) == []


def test_a_writer_without_its_credential_cannot_be_chosen_and_no_value_is_ever_printed(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    job = llm_jobs.JOBS["relatedness.profiles"]
    msgs = board_settings.validate(llm_jobs.BOARD,
                                   {job.writer_key: "deepseek", job.model_key: "deepseek-v4-flash"})
    assert any(KEY in m for m in msgs)
    secret = "sentinel-404-secret"
    monkeypatch.setenv(KEY, secret)
    assert secret not in json.dumps(llm_jobs.options())


def test_a_stored_pair_that_does_not_fit_reads_the_jobs_own_default(monkeypatch):
    """A model saved for another provider, or an unknown provider, never produces an invalid pair (#360 S2)."""
    monkeypatch.setattr(settings_store, "overrides", lambda board: {
        "RELATEDNESS_NAMING_WRITER": "grok", "RELATEDNESS_NAMING_MODEL": "grok-9"})
    assert llm_jobs.pair("relatedness.naming") == ("evren", "evren-deepseek-v4.1-flash")


# ── the card's rows ─────────────────────────────────────────────────────────

def test_the_card_offers_every_writer_per_job_and_marks_the_paid_one(monkeypatch):
    monkeypatch.setenv(KEY, "sentinel-404-key")
    rows = {r["job"]: r for r in llm_jobs.options()}
    assert set(rows) == set(llm_jobs.JOBS)
    row = rows["sec_reads.company.profile"]
    assert row["paid"] is False and row["provider"] == "evren"
    writers = {w["provider"]: w for w in row["writers"]}
    assert writers["deepseek"]["paid"] is True and writers["evren"]["paid"] is False
    assert writers["deepseek"]["available"] is True


def test_the_card_greys_a_writer_whose_credential_is_absent_by_variable_name(monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    row = llm_jobs.options()[0]
    writers = {w["provider"]: w for w in row["writers"]}
    assert writers["deepseek"]["available"] is False and writers["deepseek"]["missing"] == KEY


# ── no job module names a provider ──────────────────────────────────────────

def test_theme_naming_has_no_fixed_provider_import():
    """It imported ``core.providers.deepseek`` — the paid writer — directly until #404."""
    src = (REPO / "module_relatedness" / "naming.py").read_text(encoding="utf-8")
    assert not re.search(r"^from .*providers import|^\s*from .*providers\b", src, re.M)
    assert "deepseek" not in src.replace("evren-deepseek-v4.1-flash", "")
    assert 'JOB = "relatedness.naming"' in src
    assert "llm_jobs.client(JOB)" in src


def test_the_shared_exception_names_cover_both_writers():
    from RevenueChaser.core.providers import evren
    assert issubclass(evren.EvrenError, llm_jobs.Error)
    assert issubclass(evren.EvrenAuthError, llm_jobs.AuthError)
    assert issubclass(evren.EvrenTransientError, llm_jobs.TransientError)


def test_a_job_module_never_names_the_settings_page_registry():
    """``core.board_settings`` reaches every board module to collect that board's specs. An LLM job's module that
    imported it would put every board on the path of the root conftest (which imports the SEC reading service),
    and CI would run the whole suite for any board change (``scripts/select_tests.py`` reads the import graph with
    ast, so a call-local import counts too). The saved pairs come from ``core.settings_store`` instead."""
    tree = ast.parse((REPO / "core" / "llm_jobs.py").read_text(encoding="utf-8"))
    named = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            named += [a.name for a in node.names if "board_settings" in a.name]
        elif isinstance(node, ast.ImportFrom):
            named += [a.name for a in node.names if "board_settings" in a.name]
            if node.module and "board_settings" in node.module:
                named.append(node.module)
    assert named == []


# ── no default spends money (avo, 20 Nov 2026) ──────────────────────────────
# "Fetch ve build sirasinda deepseek api kullanilan islem kalmasin hepsi evren deepseek olmali": every Fetch job
# and every builder step calls EVREN. A paid writer is reachable only when a caller names it, so no function may
# carry one as the default of its writer argument: a caller that forgets the argument would spend money, and that
# is what ``module_relatedness.engine.run`` and ``profiles.llm`` did until this guard landed.

PAID = {slug for slug, w in llm_writers.WRITERS.items() if w.paid}
#: Where the repo's own code lives (a test may default to a paid writer: it calls nothing).
CODE_DIRS = ("app", "core", "rcdata", "scripts", "module_relatedness", "module_value_chain", "module_settings")


def _writer_defaults(path: Path) -> list[str]:
    """``<function>(<arg>=<paid slug>)`` for every argument of ``path`` that defaults to a paid writer."""
    out = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        positional = args.posonlyargs + args.args
        pairs = list(zip(positional[len(positional) - len(args.defaults):], args.defaults))
        pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None]
        for arg, default in pairs:
            if not re.search(r"provider|writer", arg.arg):
                continue
            if isinstance(default, ast.Constant) and default.value in PAID:
                out.append(f"{node.name}({arg.arg}={default.value!r})")
    return out


def test_no_function_in_the_repo_defaults_a_writer_argument_to_a_paid_provider():
    offenders = {}
    for folder in CODE_DIRS:
        for path in sorted((REPO / folder).rglob("*.py")):
            if "tests" in path.parts or path.name.startswith("test_"):
                continue
            found = _writer_defaults(path)
            if found:
                offenders[str(path.relative_to(REPO))] = found
    assert offenders == {}, (
        "a writer argument defaults to a paid provider; the default is a free writer and a paid run names it: "
        + json.dumps(offenders, sort_keys=True))
    # The registry's own half of the rule is
    # ``test_every_job_defaults_to_evren_and_no_job_defaults_to_a_paid_writer`` above.

