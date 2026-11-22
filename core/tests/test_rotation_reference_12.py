"""#12 (and the first half of #13): the rotation reference data has a neutral home.

``ROTATION_ETFS`` and ``MACRO_SERIES`` were defined by the Sector Rotation board, so ``core/``,
``module_relatedness/`` and ``module_earnings_radar/`` imported a board module to read two reference dicts. They
live in ``core/rotation_reference.py``. Since plan v5 step 7b the ETFs are avo's ``map`` watch list, read through
``rotation_reference.rotation_etfs()``; the dict is ``SEED_ROTATION_ETFS``, what the list is first made from.

What this file pins:

- **The board re-exports the macro table.** ``universe.MACRO_SERIES is rotation_reference.MACRO_SERIES``.
- **The edges are gone.** No non-test source under ``core/``, ``module_relatedness/`` or
  ``module_earnings_radar/`` reaches into the board module for the reference data.
- **No reader keeps a copy.** No non-test source names the seed dicts but the reference module and the seeding
  store: a reader that imported the seed would be the code-dict fallback 7b removes.
- **Content parity.** The seed's key sequence is the one ``universe.py`` held at the base commit (plus the symbols
  added on purpose since, each named), and the list reads back as its seed.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# The key sequences as they stood in ``module_sector_rotation/universe.py`` before the move.
_ROTATION_KEYS = (
    "XLC", "XLE", "XLF", "XLI", "XLB", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    "AIQ", "ARKQ", "IGV", "ROBO", "SKYY", "SMH", "SOXX", "WCLD", "AIRR", "ITA", "PAVE",
    "GLD", "LIT", "NLR", "SLV", "URA", "USO", "XME", "XOP", "IBB", "XBI", "JETS", "KRE",
    # added 17 Nov 2026 (Sector Rotation review, D1 and avo's watch lists)
    "IHI", "HACK", "XHB", "XRT", "REMX",
    "CIBR", "ICLN", "TAN", "GDX", "CLOU", "DTCR", "QTUM", "FINX", "GRID", "DRIV", "BLOK", "ESPO", "COPX",
    "QQQ", "RSP", "VUG", "VTV", "MAGS",
    "IYT", "PEJ", "KBE", "KCE", "KIE", "XTL", "VNQ",
    "EEM", "IWM", "HYG", "LQD", "TLT",
    "EWZ", "EWY", "FXI", "INDA", "EWT", "EWC", "EWA", "EWJ", "EWU", "MCHI", "EWG", "EWW",
    "VNM", "EWS", "EIDO", "ECH", "EWP", "KSA", "EWM", "EPOL", "THD", "EEMV", "EZA", "TUR",
    "ARGT", "EPHE", "IDX", "EPU",
    "US02Y", "US05Y", "US10Y", "US20Y", "US30Y", "US10Y-US02Y", "USIRYY", "CL1!", "MOVE",
    "VVIX", "WHEATF",
)
_MACRO_KEYS = ("US02Y", "US05Y", "US10Y", "US20Y", "US30Y", "US10Y-US02Y", "USIRYY",
               "CL1!", "MOVE", "VVIX", "WHEATF", "HY_OAS", "IG_OAS")   # the credit spreads: macro table, 17 Nov 2026

# The packages that used to import the board module for these two names. ``app/`` is the
# composition root and may name any area by design (#12), so it is not scanned.
_READER_PACKAGES = ("core", "module_relatedness", "module_earnings_radar")
_NAMES = ("ROTATION_ETFS", "MACRO_SERIES")
# The reference module itself: its docstring names the board module the data moved out of.
_HOME = _ROOT / "core" / "rotation_reference.py"


def _reader_sources():
    for package in _READER_PACKAGES:
        for path in sorted((_ROOT / package).rglob("*.py")):
            parts = path.relative_to(_ROOT).parts[:-1]
            # A test imports the board's ``universe`` on purpose: it patches the attribute that
            # lives there (``test_macro_watch.py``, ``test_cleanup_199.py``).
            if "tests" in parts or "__pycache__" in parts or path == _HOME:
                continue
            yield path


def test_the_board_reexports_the_macro_table():
    from revenuechaser.core import rotation_reference
    from revenuechaser.module_sector_rotation import universe

    assert universe.MACRO_SERIES is rotation_reference.MACRO_SERIES
    assert not hasattr(universe, "ROTATION_ETFS") and not hasattr(rotation_reference, "ROTATION_ETFS")


def test_no_reader_package_imports_the_board_for_the_reference_data():
    offenders = {}
    for path in _reader_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "module_sector_rotation" not in text:
            continue
        hits = [name for name in _NAMES if name in text]
        if hits:
            offenders[path.relative_to(_ROOT).as_posix()] = hits
    assert not offenders, (
        "these files read rotation reference data through the board module; import "
        f"revenuechaser.core.rotation_reference instead: {offenders}")


def test_no_run_reads_the_seed():
    """Plan v5 step 7b: the seed makes the lists once and feeds the tests. A source file that names it would be a
    code-dict fallback beside the watch list."""
    from revenuechaser.core import rotation_reference
    assert rotation_reference.SEED_ROTATION_ETFS and rotation_reference.SEED_INDUSTRY_GROUPS
    allowed = {"core/rotation_reference.py"}
    offenders = []
    for path in sorted(_ROOT.rglob("*.py")):
        rel = path.relative_to(_ROOT).as_posix()
        if "/tests/" in rel or rel.startswith((".", "module_testing/")) or rel == "conftest.py" or rel in allowed:
            continue
        if "SEED_ROTATION_ETFS" in path.read_text(encoding="utf-8", errors="replace") \
                or "SEED_INDUSTRY_GROUPS" in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(rel)
    assert not offenders, offenders


def test_the_seed_keeps_every_symbol_the_board_defined_and_the_list_reads_back_as_it():
    from revenuechaser.core import rotation_reference

    assert tuple(rotation_reference.SEED_ROTATION_ETFS) == _ROTATION_KEYS
    assert tuple(rotation_reference.MACRO_SERIES) == _MACRO_KEYS
    assert rotation_reference.rotation_etfs() == rotation_reference.SEED_ROTATION_ETFS
    assert list(rotation_reference.rotation_etfs()) == list(_ROTATION_KEYS)
