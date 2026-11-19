"""``shrink_scope`` reads what each dataset declares it feeds (#293, #326).

Until #326 the scope of a request's ``allow_shrink`` was inferred: the asking dataset's own tables plus every table
of the kind that belonged to a dataset with no provider. That let a run on one feeder relax tables its rows never
reach (#293), and left a table a source owned relaxable by that source alone whatever fed it (#326, ``fund``).

These tests hold the declarations to their kind. They are the reason a new source dataset cannot be added to a
serving kind without saying which served tables its rows reach.
"""
from __future__ import annotations

import pytest

from RevenueChaser.rcdata.build import DATASETS, base
from RevenueChaser.rcdata.build import ownership, spine
from RevenueChaser.rcdata.build.ownership import serve as ownership_serve
from RevenueChaser.rcdata.build.spine import security as spine_security


def _kinds() -> list[str]:
    return sorted({d.kind for d in DATASETS.values()})


def _of(kind: str) -> list:
    return [d for d in DATASETS.values() if d.kind == kind]


def _served(kind: str) -> set[str]:
    return {t for d in _of(kind) for t in d.tables}


def _derived(kind: str) -> set[str]:
    """The served tables of ``kind`` built by a dataset that fetches nothing (``prices/serving`` and its kin)."""
    return {t for d in _of(kind) if not tuple(d.providers) for t in d.tables}


DERIVING_KINDS = sorted(k for k in _kinds() if _derived(k))


@pytest.mark.parametrize("kind", DERIVING_KINDS)
def test_every_dataset_of_a_deriving_kind_declares_what_it_feeds(kind):
    """A kind whose file holds a table built from another dataset's rows: every dataset of it declares ``feeds``,
    the empty tuple included, so a new source cannot inherit a scope nobody chose."""
    missing = sorted(d.name for d in _of(kind) if not hasattr(d, "feeds"))
    assert missing == [], f"{kind}: these datasets declare no feeds: {missing}"


@pytest.mark.parametrize("kind", DERIVING_KINDS)
def test_a_declaration_names_served_tables_of_its_own_kind_only(kind):
    served = _served(kind)
    for d in _of(kind):
        feeds = base.feeds(d)
        assert len(set(feeds)) == len(feeds), f"{d.name} names a table twice"
        assert set(feeds) <= served, f"{d.name} feeds {sorted(set(feeds) - served)}, not tables of {kind}"
        assert not set(feeds) & set(d.tables), f"{d.name} feeds {sorted(set(feeds) & set(d.tables))}, which it builds"


@pytest.mark.parametrize("kind", DERIVING_KINDS)
def test_every_derived_table_is_fed_by_at_least_one_source(kind):
    """The safety net against a declaration that is too narrow: a table no source feeds could never be relaxed,
    so an outage of the source behind it would have no way out but a code change."""
    fed = {t for d in _of(kind) if tuple(d.providers) for t in (*d.tables, *base.feeds(d))}
    orphans = sorted(_derived(kind) - fed)
    assert orphans == [], f"{kind}: no dataset says it feeds {orphans}"


def test_the_named_derived_sets_are_the_ones_their_dataset_builds():
    """``spine.DERIVED`` and ``ownership.SERVED_13F`` exist so a source can name them without importing the dataset
    that is built after it; they are the same tables."""
    assert set(spine.DERIVED) == set(spine_security.TABLES)
    assert set(ownership.SERVED_13F) == set(ownership_serve.TABLES)


def test_293_a_feeder_no_longer_relaxes_every_derived_table_of_its_kind():
    """The #293 case: ``--allow-shrink`` on one fundamentals source used to relax ``fundamental_revision``, which
    the internal-data-API plan lists as not refetchable after a purge, and which only the WRDS tables feed."""
    scope = base.shrink_scope(DATASETS["yfinance/estimates"])
    assert scope == ("estimate_latest",)
    assert "fundamental_revision" in base.shrink_scope(DATASETS["wrds/funda"])


def test_326_only_the_fund_file_relaxes_fund_and_it_relaxes_nothing_else():
    """The #326 case, now declared rather than inferred: ``fund`` is fed by ``sec/company_tickers_mf`` alone, and
    that dataset's rows reach no other spine table, so its ``allow_shrink`` cannot touch one."""
    assert base.shrink_scope(DATASETS["sec/company_tickers_mf"]) == ("fund",)
    assert all("fund" not in base.shrink_scope(d) for d in _of("spine") if d.name != "sec/company_tickers_mf")


def test_a_dataset_that_declares_nothing_relaxes_its_own_tables_only():
    class Feeder:
        kind, providers, tables = "spine", ("test",), ("security",)

    assert base.feeds(Feeder()) == ()
    assert base.shrink_scope(Feeder()) == ("security",)
