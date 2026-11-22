"""Two theme methods side by side (avo, 16 Nov 2026): the tag NMF and k-means on the stored vectors."""
from __future__ import annotations

import numpy as np
import pytest

from revenuechaser.module_relatedness import embeddings, themes
from revenuechaser.module_relatedness.tests.test_themes import _profiles


def _two_groups(pjs, write=True):
    a, b = np.eye(4, dtype="float32")[0], np.eye(4, dtype="float32")[1]
    return {t: (a if t.startswith("G") else b) for t in pjs}


def test_the_embedding_method_clusters_the_stored_vectors(rawstore_tmp_db, monkeypatch):
    monkeypatch.setattr(embeddings, "company_vectors", _two_groups)
    monkeypatch.setattr(themes.rel_store, "load_profile_json", lambda tickers: {t: {} for t in tickers})
    out = themes.build_shadow(candidates=(2,), k_medium=1, k_coarse=1, profiles=_profiles(), method="embedding")
    assert out["method"] == "embedding" and out["run_id"].startswith("emb-") and out["unthemed"] == 0
    groups = {}
    for m in themes.run_rows("relatedness_theme_members", out["run_id"]):
        groups.setdefault(m["theme_id"], set()).add(m["ticker"][0])
    assert sorted(map(sorted, groups.values())) == [["B"], ["G"]]       # one theme per vector group
    tags = {r["tag"] for r in themes.run_rows("relatedness_theme_tags", out["run_id"])}
    assert {"gpu", "loans"} <= tags                                       # the namer still reads the tags


def test_a_company_without_a_vector_is_unthemed(rawstore_tmp_db, monkeypatch):
    monkeypatch.setattr(embeddings, "company_vectors",
                        lambda pjs, write=True: {t: v for t, v in _two_groups(pjs).items() if t != "G0"})
    monkeypatch.setattr(themes.rel_store, "load_profile_json", lambda tickers: {t: {} for t in tickers})
    out = themes.build_shadow(candidates=(2,), k_medium=1, k_coarse=1, profiles=_profiles(), method="embedding")
    assert out["unthemed"] == 1 and out["n"] == 59


def test_an_unknown_method_is_refused(rawstore_tmp_db):
    with pytest.raises(ValueError):
        themes.build_shadow(profiles=_profiles(), method="leiden")


def test_compare_runs_reads_one_grouping_as_identical(rawstore_tmp_db, monkeypatch):
    monkeypatch.setattr(embeddings, "company_vectors", _two_groups)
    monkeypatch.setattr(themes.rel_store, "load_profile_json", lambda tickers: {t: {} for t in tickers})
    a = themes.build_shadow(candidates=(2,), k_medium=1, k_coarse=1, run_id="a", profiles=_profiles())
    b = themes.build_shadow(candidates=(2,), k_medium=1, k_coarse=1, run_id="b", profiles=_profiles(),
                            method="embedding")
    got = themes.compare_runs(a["run_id"], b["run_id"])
    assert got["companies"] == {"a": 60, "b": 60, "both": 60}
    assert got["fine"] == {"a": 2, "b": 2, "ari": 1.0}


def test_a_rebuild_that_leaves_too_many_unthemed_is_not_cut_over(rawstore_tmp_db, monkeypatch, capsys):
    from revenuechaser.module_relatedness import __main__ as cli
    monkeypatch.setattr(themes, "build_shadow", lambda **k: {"run_id": "r", "n": 80, "unthemed": 20})
    monkeypatch.setattr(themes, "finalize_run", lambda *a, **k: pytest.fail("cut over"))
    assert cli.main(["--rebuild-themes", "--method", "embedding"]) == 1
    assert "not cut over" in capsys.readouterr().out
