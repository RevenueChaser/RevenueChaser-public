"""#1142: the five names of the census that resolved to the wrong listed company.

The census of 20 Nov 2026 (``notes/revenuechaser/2026-11-20_0110_value-chain-profile-edge-census.md`` in
claude-coordinator) found 28 wrong profile edges; five of them were a right answer matched to the wrong ticker,
which is this module's work and not the profile writer's:

* a word that names a kind of counterparty ("employers" -> EIG, because Employers Holdings Inc is listed);
* a name whose own words say it is another company ("Rafael Technologies" -> Rafael Holdings,
  "STEMCELL Technologies" -> International Stem Cell);
* a registrant reachable only after two of its name's words are dropped ("Orion Corporation", a Finnish
  pharmaceutical company, -> Orion Group Holdings);
* an alias followed by a word that makes it a different listed company ("Samsung SDI" -> Samsung).

The second half holds the short names that must keep resolving: dropping them would cost coverage for nothing.
"""
from __future__ import annotations

import pytest

from revenuechaser.module_value_chain import aliases

SPINE = aliases.spine_names([
    {"ticker": "ORN", "name": "Orion Group Holdings, Inc."},
    {"ticker": "RFL", "name": "Rafael Holdings, Inc."},
    {"ticker": "ISCO", "name": "International Stem Cell Corp"},
    {"ticker": "EIG", "name": "Employers Holdings, Inc."},
    {"ticker": "PFE", "name": "Pfizer Inc."},
    {"ticker": "HON", "name": "Honeywell International Inc."},
    {"ticker": "EXPE", "name": "Expedia Group, Inc."},
    {"ticker": "UPST", "name": "Upstart Holdings, Inc."},
    {"ticker": "AMKR", "name": "Amkor Technology Inc"},
    {"ticker": "MCK", "name": "McKesson Corporation"},
    {"ticker": "BTOC", "name": "Armlogi Holding Corp"},
])


@pytest.mark.parametrize("name", ["employers", "government agencies", "consumers"])
def test_a_kind_of_counterparty_is_no_company(name):
    assert aliases.resolve(name, SPINE) is None


@pytest.mark.parametrize("name", ["Rafael Technologies", "STEMCELL Technologies"])
def test_a_name_whose_own_words_differ_is_another_company(name):
    assert aliases.resolve(name, SPINE) is None


def test_a_registrant_two_name_words_away_is_reachable_by_its_full_name_only():
    assert aliases.resolve("Orion Corporation", SPINE) is None
    assert aliases.resolve("Orion Group Holdings", SPINE) == {"name": "Orion Group Holdings", "ticker": "ORN"}


def test_an_alias_followed_by_another_company_s_word_is_not_that_alias():
    assert aliases.resolve("Samsung SDI") is None
    assert aliases.resolve("Samsung SDI Co., Ltd.") is None
    assert (aliases.resolve("Samsung Electronics") or {}).get("ticker") == "SSNLF"      # the same company
    assert (aliases.resolve("Amazon Web Services") or {}).get("ticker") == "AMZN"
    assert (aliases.resolve("Super Micro Computer") or {}).get("ticker") == "SMCI"


@pytest.mark.parametrize("name,ticker", [("Pfizer", "PFE"), ("Pfizer Inc.", "PFE"), ("Honeywell", "HON"),
                                         ("Expedia", "EXPE"), ("Upstart", "UPST"), ("Amkor Technology", "AMKR"),
                                         ("Mc Kesson Corporation", "MCK"), ("Armlogi Holding Corp", "BTOC")])
def test_a_short_name_the_registrant_agrees_with_still_resolves(name, ticker):
    assert (aliases.resolve(name, SPINE) or {}).get("ticker") == ticker


def test_strict_keeps_the_name_s_own_words():
    assert aliases.strict("Rafael Technologies, Inc.") == "RAFAEL TECHNOLOGIES"
    assert aliases.normalize("Rafael Technologies, Inc.") == "RAFAEL"
