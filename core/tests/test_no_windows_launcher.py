"""#1225: the Windows-era launcher and the Task Scheduler backend are gone, and no code may lead back.

avo chose "Temizlik şimdi, adlar v2'de" (21 Nov 2026): the Windows start scripts, the Task Scheduler
installer and the desktop-launch path went, and the jobs run as systemd units on homesrv. This test
fails a change that brings any of it back:

- no code file starts ``powershell``, ``pythonw`` or ``schtasks``, and none builds a PowerShell
  ``*-ScheduledTask`` cmdlet;
- no launcher script (``*.ps1``, ``*.bat``, ``*.pyw``) is tracked again.

Comments and docstrings may still tell the history; only code is checked. The ``os.name == "nt"``
branches of ``core/procs.py`` and ``core/oom.py`` stay: they are process-name portability, not a
launcher (the issue's own "check first" note).
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

#: What only the Windows launcher or the Task Scheduler backend ever needed.
_WINDOWS_ONLY = re.compile(r"powershell|pythonw|schtasks|-ScheduledTask|ScheduledTask(?:Action|Trigger|SettingsSet"
                           r"|Principal|Info)", re.IGNORECASE)
_LAUNCHER_SUFFIXES = (".ps1", ".bat", ".cmd", ".pyw")


def _tracked(pattern: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", pattern], cwd=_REPO,
                         capture_output=True, text=True, check=True).stdout
    return out.split()


def _code_files():
    """Every tracked Python file that is code, not a test: a test may still name PowerShell to prove it is gone."""
    for rel in _tracked("*.py"):
        parts = rel.split("/")
        if parts[0].startswith(".") or parts[0] == "module_testing" or "tests" in parts or parts[-1] == "conftest.py":
            continue
        path = _REPO / rel
        if path.exists():
            yield rel, path.read_text(encoding="utf-8")


def _code_strings(tree) -> list[str]:
    """Every string constant that is not a docstring or a bare string statement."""
    prose = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in prose]


def test_no_code_file_starts_powershell_or_a_scheduled_task():
    offenders = []
    for rel, src in _code_files():
        for text in _code_strings(ast.parse(src)):
            if _WINDOWS_ONLY.search(text):
                offenders.append(f"{rel}: {text[:80]!r}")
    assert offenders == [], "Windows launcher / Task Scheduler code is back: " + "; ".join(offenders)


def test_no_launcher_script_is_tracked():
    tracked = [rel for rel in _tracked("*") if rel.lower().endswith(_LAUNCHER_SUFFIXES)]
    assert tracked == [], f"launcher scripts are back: {tracked}"


def test_the_automations_module_has_no_windows_backend():
    from revenuechaser.core import automations

    gone = [name for name in ("WindowsScheduler", "_powershell", "_ps_quote", "windowless_python", "parse_status")
            if hasattr(automations, name)]
    assert gone == [], f"the Windows scheduler backend is back: {gone}"
