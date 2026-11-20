"""One record of every dataset: tables, store file, source, writer, freshness, coverage (#124).

Claim rule, applied to ``rawstore.MANIFEST``:

- A ``*_changes`` table (MANIFEST ``changes_of``) is listed on the dataset that owns its base table.
- Every other MANIFEST table is listed on exactly one dataset.
- ``UNCLAIMED_ALLOWLIST`` holds only ``store_schema``, the version stamp every board file carries.

The MANIFEST holds only the board files' tables since #860 removed the old raw, edgar, prices and history files,
so ``db`` is a board file (MANIFEST ``db``). ``writer`` is an ``automations.REGISTRY`` name, or None with
``writer_note``. A freshness pair is a ``(table, column)`` the board file holds. ``source`` is a provider named in
``core/providers`` or ``docs/data_architecture.md``; ``unknown`` means a single enum value would be a guess.

Does not read the store.

``gap_kind`` and ``next_step`` (G11) are the written half of coverage: the measurement says how many
names are missing, these two say what would close the hole. ``gap_kind`` is one of ``GapKind``'s six
values, and a kind that closes only through work (``fixable``, ``in_build``, ``needs_decision``) or
through a fact about the source (``ceiling``, which carries its REASON) requires a ``next_step``.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum

from RevenueChaser.core.datahealth import Health

DBS = ("news", "welcome", "relatedness", "comovement", "asymmetric_growth", "swing_potential", "fundamentals",
       "sector_rotation", "oipd", "forecast", "spx_gamma", "sec_13f", "watchlists", "value_chain")
# the board files (S9, S16); the old raw, edgar, prices and history files are gone (#860)

FROM_RUN_LOG = "from_run_log"
NO_CLAIM = "no_claim"
# Derived rows say this until the run log is trustworthy. S5b part 3.
FROM_RUN_LOG_CAVEAT = (
    "from the run log; not trustworthy until alsanvolkan/RevenueChaser-public#82 and alsanvolkan/RevenueChaser-public#83 are fixed (run_registry / result_runs)"
)

class Source(str, Enum):
    """Provider of a dataset's rows. ``unknown`` is a refusal to pick one value, not a provider."""

    uw = "uw"
    yfinance = "yfinance"
    sec = "sec"
    finra_cftc = "finra/cftc"
    cboe = "cboe"
    fred = "fred"
    openfigi = "openfigi"
    ibkr = "ibkr"
    derived = "derived"
    manual = "manual"
    store = "store"
    unknown = "unknown"


@dataclass(frozen=True)
class CoverageSpec:
    """Two SQL queries: who should have a row, and who does. S4 may fill these; S3 does not invent them."""

    population: str
    presence: str

    def __post_init__(self) -> None:
        if not (self.population and self.presence):
            raise ValueError("CoverageSpec needs a population query and a presence query")


class GapKind(str, Enum):
    """What stands between a dataset and its full population (#124 G11).

    ``fixable`` we can close now, ``in_build`` something already being built closes, ``needs_decision``
    waits on a choice, ``ceiling`` cannot be closed on the route we use (its ``next_step`` says why, as
    a fact about the source), ``self_heals`` fills in over time, ``none`` means there is no hole.
    """

    fixable = "fixable"
    in_build = "in_build"
    needs_decision = "needs_decision"
    ceiling = "ceiling"
    self_heals = "self_heals"
    none = "none"


# The kinds whose gap only closes through written words. ``ceiling`` is here because it must carry
# its REASON (why the source cannot give us the rest), not a schedule.
_GAP_KINDS_WITH_STEP = (
    GapKind.fixable, GapKind.in_build, GapKind.needs_decision, GapKind.ceiling,
)

Freshness = tuple[str, str] | tuple[tuple[str, str], ...] | str | None


@dataclass(frozen=True)
class DatasetSpec:
    """One dataset. ``coverage`` is None, a ``CoverageSpec`` of two SQL queries, or a callable returning ``Health``."""

    key: str
    label: str
    tables: tuple[str, ...]
    db: str
    source: Source
    writer: str | None
    freshness: Freshness
    writer_note: str | None = None
    freshness_note: str | None = None
    coverage: CoverageSpec | Callable[..., Health] | None = None
    coverage_note: str | None = None
    gap_kind: GapKind | None = None
    next_step: str | None = None

    def __post_init__(self) -> None:
        if not self.key or not self.label:
            raise ValueError("a dataset needs a key and a label")
        if not self.tables or len(set(self.tables)) != len(self.tables):
            raise ValueError(f"{self.key}: tables must be a non-empty tuple of unique names")
        if self.db not in DBS:
            raise ValueError(f"{self.key}: db {self.db!r} is not one of {DBS}")
        if not isinstance(self.source, Source):
            raise ValueError(f"{self.key}: source must be a Source, not {self.source!r}")
        if self.writer is None:
            if not (self.writer_note and self.writer_note.strip()):
                raise ValueError(f"{self.key}: writer None needs a non-empty writer_note")
        elif not str(self.writer).strip():
            raise ValueError(f"{self.key}: writer is blank")
        if self.freshness == FROM_RUN_LOG:
            note = self.freshness_note or FROM_RUN_LOG_CAVEAT
            if "#82" not in note or "#83" not in note:
                raise ValueError(f"{self.key}: from_run_log must carry the #82/#83 caveat")
            object.__setattr__(self, "freshness_note", note)
        pairs = self.freshness_pairs()
        for table, column in pairs:
            if table not in self.tables or not column:
                raise ValueError(f"{self.key}: freshness {table}.{column} is not one of its tables")
        if self.coverage is not None and not (
            isinstance(self.coverage, CoverageSpec) or callable(self.coverage)
        ):
            raise ValueError(f"{self.key}: coverage must be None, a CoverageSpec, or a callable")
        if self.gap_kind is not None and not isinstance(self.gap_kind, GapKind):
            raise ValueError(
                f"{self.key}: gap_kind must be a GapKind or None, not {self.gap_kind!r}; "
                f"one of {[kind.value for kind in GapKind]}")
        if self.next_step is not None and not (
            isinstance(self.next_step, str) and self.next_step.strip()
        ):
            raise ValueError(f"{self.key}: next_step must be None or non-empty text")
        if self.gap_kind in _GAP_KINDS_WITH_STEP and not (self.next_step or "").strip():
            needs = ("its reason, a fact about the source" if self.gap_kind is GapKind.ceiling
                     else "a next_step that says what would close it")
            raise ValueError(f"{self.key}: gap_kind {self.gap_kind.value!r} needs {needs} in next_step")

    def freshness_pairs(self) -> tuple[tuple[str, str], ...]:
        """``(table, column)`` pairs ``_max_date`` can read. Empty for None, from_run_log, no_claim."""
        f = self.freshness
        if f is None or f == FROM_RUN_LOG or f == NO_CLAIM:
            return ()
        if (
            isinstance(f, tuple) and len(f) == 2
            and isinstance(f[0], str) and isinstance(f[1], str)
        ):
            return (f,)
        if (
            isinstance(f, tuple) and f
            and all(isinstance(p, tuple) and len(p) == 2 and isinstance(p[0], str) for p in f)
        ):
            return f
        raise ValueError(
            f"{self.key}: freshness {f!r} is not a (table, column) pair, {FROM_RUN_LOG}, or {NO_CLAIM}"
        )


def _runlog(key: str, label: str, tables: tuple[str, ...], db: str, source: Source,
            writer: str | None, writer_note: str | None = None) -> DatasetSpec:
    """A derived dataset whose freshness is the producing run, not a row timestamp."""
    return DatasetSpec(
        key=key, label=label, tables=tables, db=db, source=source,
        writer=writer, writer_note=writer_note, freshness=FROM_RUN_LOG,
        freshness_note=FROM_RUN_LOG_CAVEAT,
    )


# Seeded from module_settings/inventory.py ``_collect`` (the 19 rows that builder returns), then
# extended so every base MANIFEST table has one owner. ``*_changes`` companions are on the base's dataset.
REGISTRY: tuple[DatasetSpec, ...] = (
    # #860 stage 1: the corpus slice and the stored-document metadata no longer share a file, so they are two
    # rows. A spec's ``db`` is one file and every table it owns has to live there (test_datasets).
    DatasetSpec(
        key="corpus", label="10-K / 20-F corpus",
        tables=("chain_filings",),
        db="value_chain", source=Source.sec, writer="RC-Relatedness-OffPeak",
        freshness=("chain_filings", "filed"),
        writer_note="the Value Chain board's Fetch (module_value_chain --fetch) writes it too",
    ),
    DatasetSpec(
        key="oipd", label="Implied Probability chain (retired)",
        tables=("oipd_chain", "oipd_meta"),
        db="oipd", source=Source.uw, writer=None,
        writer_note=("nothing writes it since #1059: the board fits option_eod from the nightly options build; "
                     "the tables go in plan step 6 (avo's 'sil')"),
        freshness=NO_CLAIM,
    ),
    DatasetSpec(
        key="relatedness", label="Relatedness profiles",
        tables=("relatedness_profiles", "relatedness_scores", "relatedness_attributes", "relatedness_embeddings"),
        db="relatedness", source=Source.derived, writer="RC-Relatedness-OffPeak",
        freshness=("relatedness_profiles", "fetched_at"),
    ),

    # Watch lists (#786, avo 12 Nov 2026): his own named lists in boards/watchlists.duckdb, typed by hand. Its own
    # row and not part of "Your inputs" above, because those four tables are the retired raw ones.
    DatasetSpec(
        key="watchlists", label="Watch lists",
        tables=("wl_list", "wl_section", "wl_item", "wl_change"),
        db="watchlists", source=Source.manual, writer=None,
        writer_note=("avo types them, through the board or the import command "
                     "(module_watchlists/store.py is the one writer); nothing fetches them"),
        freshness=("wl_change", "changed_at"),
    ),

    # --- extended: base tables the 19 rows do not own ---
    DatasetSpec(
        key="value_chain", label="Value Chain edges",
        tables=("chain_mentions", "chain_meta"),
        db="value_chain", source=Source.sec, writer="RC-ValueChain-Sync",
        freshness=("chain_mentions", "filed"),
    ),
    DatasetSpec(
        key="swing_info", label="Swing info cache",
        tables=("swing_info",),
        db="swing_potential", source=Source.yfinance, writer=None,
        writer_note="the board's own Fetch on the dashboard; not an automations.REGISTRY entry",
        freshness=("swing_info", "cached_at"),
    ),
    _runlog(
        "ag_scores", "Asymmetric Growth scores", ("ticker_scores",),
        "asymmetric_growth", Source.derived, None,
        writer_note="the board's own Fetch on the dashboard; not an automations.REGISTRY entry",
    ),
    _runlog(
        "swing_scores", "Swing scores", ("swing_scores", "swing_gates"),
        "swing_potential", Source.derived, None,
        writer_note="the board's own Fetch on the dashboard; not an automations.REGISTRY entry",
    ),
    _runlog(
        "fundamentals_scores", "Fundamentals scores", ("fundamentals_scores", "fundamentals_gates"),
        "fundamentals", Source.derived, None,
        writer_note="the board's own Fetch on the dashboard; not an automations.REGISTRY entry",
    ),
    DatasetSpec(
        key="forecast_ledger", label="Forecast ledger",
        tables=("forecast_ledger",),
        db="forecast", source=Source.derived, writer=None,
        writer_note="the board's own Fetch on the dashboard; not an automations.REGISTRY entry",
        freshness=("forecast_ledger", "forecast_date"),
    ),
    _runlog(
        "forecast_outcomes", "Forecast outcomes", ("forecast_outcomes",),
        "forecast", Source.derived, "RC-Forecast-Outcomes",
    ),
    _runlog(
        "forecast_baselines", "Forecast baselines", ("forecast_baselines",),
        "forecast", Source.derived, "RC-Forecast-Baselines",
    ),
    DatasetSpec(
        key="comovement", label="Co-movement runs",
        tables=("comov_runs", "comov_nodes", "comov_members", "comov_lag"),
        db="comovement", source=Source.derived, writer=None,
        writer_note="dashboard job POST /run/module_comovement; not an automations.REGISTRY entry",
        freshness=("comov_runs", "as_of"),
    ),
    DatasetSpec(
        key="rotation", label="Sector rotation",
        tables=("rotation_snapshots", "rotation_holdings"),
        db="sector_rotation", source=Source.derived, writer=None,
        writer_note="dashboard job Sector Rotation Fetch (module_sector_rotation/store.py); not a REGISTRY entry",
        freshness=(("rotation_snapshots", "as_of_date"), ("rotation_holdings", "date")),
    ),
    DatasetSpec(
        key="themes", label="Fitted themes",
        tables=("relatedness_themes", "relatedness_theme_tags", "relatedness_theme_members",
                "relatedness_theme_etfs", "theme_runs", "ticker_themes"),
        db="relatedness", source=Source.derived, writer=None,
        writer_note="module_relatedness/themes.py; not listed on RC-Relatedness-OffPeak",
        freshness=("theme_runs", "session_date"),
    ),
    # source unknown: DeepSeek and Grok are not in the provider enum.
    DatasetSpec(
        key="llm_cache", label="Language-model prompt cache",
        tables=("llm_cache",),
        db="relatedness", source=Source.unknown, writer="RC-Relatedness-OffPeak",
        freshness=("llm_cache", "fetched_at"),
    ),
    DatasetSpec(
        key="news_calendar", label="News: economic calendar and the day's highlight",
        tables=("news_events", "news_highlight", "news_meta"),
        db="news", source=Source.derived, writer=None,
        writer_note=("built incrementally from market.economic_event by module_news/calendar.py on the News board's "
                     "Refresh; the hourly job comes in its own pull request"),
        freshness=("news_events", "run_at"),
    ),
    DatasetSpec(
        key="news_headlines", label="News: market headlines",
        tables=("news_headlines",),
        db="news", source=Source.ibkr, writer=None,
        writer_note=("Dow Jones headlines from the IBKR Gateway (module_news/headlines.py) on the News board's Fetch; "
                     "the hourly job comes in its own pull request"),
        freshness=("news_headlines", "fetched_at"),
    ),
    DatasetSpec(
        key="welcome", label="Welcome: market closes, earnings and builder-file freshness",
        tables=("welcome_snapshot", "welcome_earnings", "welcome_freshness", "welcome_meta"),
        db="welcome", source=Source.derived, writer=None,
        writer_note=("built incrementally by module_welcome/build.py on the Welcome board's Fetch, from the "
                     "builder's market series, its options screener and its run ledger in ops (#643 PR 5b, PR 6); "
                     "the hourly job comes in its own pull request"),
        freshness=("welcome_snapshot", "session_date"),
    ),
    DatasetSpec(
        key="spx_gamma_raw", label="SPX Gamma: stored Unusual Whales days",
        tables=("spx_raw_days", "spx_raw_files"),
        db="spx_gamma", source=Source.uw, writer=None,
        writer_note=("every Unusual Whales answer of a stored day, byte-exact, by module_spx_gamma/store.py on the SPX Gamma "
                     "Fetch (the nightly RC-SPX-Gamma-Fetch queues it) and the history pull; Unusual Whales serves no history"),
        freshness=("spx_raw_days", "session_date"),
    ),
    DatasetSpec(
        key="spx_gamma_records", label="SPX Gamma: Brier and GEX records, latest pointer",
        tables=("spx_brier", "spx_gex_daily", "spx_meta"),
        db="spx_gamma", source=Source.derived, writer=None,
        writer_note=("derived from the stored days by module_spx_gamma/store.py on the SPX Gamma Fetch; "
                     "Refresh moves only spx_meta.latest"),
        freshness=("spx_gex_daily", "session_date"),
    ),
    DatasetSpec(
        key="sec13f_board_file", label="13F board: its own file (cells as filed, filer breaks, source stamp)",
        tables=("sec13f_board_cells", "sec13f_board_breaks", "sec13f_board_meta"),
        db="sec_13f", source=Source.derived, writer=None,
        writer_note=("written by module_sec_13f/store.py on the 13F Refresh and Fetch, from the ownership build, "
                     "once per build or New York day; a closed quarter is never rewritten"),
        freshness=("sec13f_board_cells", "period"),
    ),
)

# ``store_schema`` is in every board file (its version stamp), so no one dataset owns it.
UNCLAIMED_ALLOWLIST: frozenset[str] = frozenset({"store_schema"})


def _index() -> tuple[dict[str, DatasetSpec], dict[str, tuple[str, ...]]]:
    by_key: dict[str, DatasetSpec] = {}
    owners: dict[str, list[str]] = {}
    for spec in REGISTRY:
        if spec.key in by_key:
            raise ValueError(f"dataset key {spec.key!r} is listed twice")
        by_key[spec.key] = spec
        for table in spec.tables:
            owners.setdefault(table, []).append(spec.key)
    return by_key, {table: tuple(keys) for table, keys in owners.items()}


_BY_KEY, _OWNERS = _index()


def by_key(key: str) -> DatasetSpec:
    """The dataset with this key. Raises KeyError if there is none."""
    try:
        return _BY_KEY[key]
    except KeyError:
        raise KeyError(f"unknown dataset {key!r}") from None


def dataset_of_table(table: str) -> DatasetSpec:
    """The one dataset that claims ``table``. Raises KeyError if it is unclaimed or claimed twice."""
    owners = _OWNERS.get(table, ())
    if len(owners) != 1:
        raise KeyError(f"{table!r} is claimed by {owners or 'nobody'}")
    return _BY_KEY[owners[0]]


def tables_claimed() -> frozenset[str]:
    """Every table name listed on a dataset, including a name listed twice."""
    return frozenset(_OWNERS)


def unclaimed(manifest_keys: Iterable[str]) -> frozenset[str]:
    """Keys in ``manifest_keys`` that no dataset claims, minus ``UNCLAIMED_ALLOWLIST``.

    The allowlist holds only ``store_schema``. Any other name here is a MANIFEST table the registry forgot.
    """
    return frozenset(manifest_keys) - tables_claimed() - UNCLAIMED_ALLOWLIST
