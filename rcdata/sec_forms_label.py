"""Which label ``sec/forms`` writes now, for the readers that pin the cut they read (#754).

Its own module because it reads the environment and :mod:`.sec_sections` stays standard-library-minimal
(``re``, ``dataclasses``, ``html``); a board can still import it without the build package.
"""
from __future__ import annotations

import os

from .sec_sections import FORMS_ROWS_VERSION, OURS_2


def forms_rows_version() -> str:
    """:data:`~.sec_sections.FORMS_ROWS_VERSION`, or ``ours-2`` on the ``header`` rollback (``RC_SEC_FORMS_CUTTER``,
    read and checked by ``rcdata/build/sec_forms/cutter.mode``)."""
    return OURS_2 if (os.getenv("RC_SEC_FORMS_CUTTER") or "").strip().lower() == "header" else FORMS_ROWS_VERSION
