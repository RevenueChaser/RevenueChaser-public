"""Shared Jinja2 environments for HTML that modules render.

Two modules (``module_spx_gamma``, ``module_financials``) already keep their
markup in ``templates/*.html.j2`` and load it through a Jinja ``Environment``;
the remaining report modules build HTML by string concatenation. This is the
one loader those migrations should share, so markup lives next to the module
that owns it instead of inside f-strings.

Environments are cached per (directory, autoescape) so a template is compiled
once per process. ``auto_reload`` stays on: the dashboard is a local tool that
is expected to pick up an edited template without a restart.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# Repo-level templates (the Flask shell plus small shared pages).
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@lru_cache(maxsize=None)
def environment(directory: str | Path = TEMPLATES_DIR,
                autoescape: bool = True) -> Environment:
    """Cached Jinja environment rooted at ``directory``.

    ``autoescape`` defaults to True — the safe choice for new templates. Pass
    False only for a template that deliberately composes pre-rendered HTML
    fragments (what the existing report builders do).
    """
    from markupsafe import Markup
    from RevenueChaser.core.reporting_common import THEME_CSS, THEME_JS
    env = Environment(
        loader=FileSystemLoader(str(directory)),
        autoescape=autoescape,
        auto_reload=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # The shared design system's palette and theme script (#184), so a small page such as empty_board.html.j2
    # follows the shell's theme switch; both are code constants, not data, hence Markup.
    env.globals.update(theme_css=Markup(THEME_CSS), theme_js=Markup(THEME_JS))
    return env


def render(name: str, directory: str | Path = TEMPLATES_DIR,
           autoescape: bool = True, **context) -> str:
    """Render ``name`` from ``directory`` with ``context``."""
    return environment(str(directory), autoescape).get_template(name).render(**context)
