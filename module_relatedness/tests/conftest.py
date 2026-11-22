from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_embedder(monkeypatch):
    """No test loads the fastembed model (#669): its first use downloads it. A test that wants vectors sets its own
    ``embeddings._embed``; every other one scores on the tag cosine, the board's fallback."""
    from revenuechaser.module_relatedness import embeddings

    def _refuse(texts):
        raise RuntimeError("the embedding model is not loaded in tests")
    monkeypatch.setattr(embeddings, "_embed", _refuse)


@pytest.fixture(autouse=True)
def _spine_file():
    """A spine with an empty ``security`` table, so a profile run can start (#642 D3: no spine stops it). A test that
    names companies or sectors writes its rows with ``spine_fixture.write_security``; one that builds the real spine
    swaps this file out."""
    from revenuechaser.rcdata.tests import spine_fixture
    spine_fixture.write_security([])


@pytest.fixture(autouse=True)
def _own_writer(monkeypatch):
    """The tests of this folder drive the board's own writer (``config.PROFILES_FROM = "own"``), which stays until
    the clean-up. A test of the mirror sets ``service`` itself."""
    from revenuechaser.module_relatedness import config
    monkeypatch.setattr(config, "PROFILES_FROM", "own")


@pytest.fixture(autouse=True)
def _deepseek_default(monkeypatch):
    """The tests of this folder drive the **DeepSeek** writer: most of them patch ``profiles.deepseek.complete``
    and read the calls it recorded, and that was the board's default until 20 Nov 2026.

    Since then the default is the registry's, which has no fee (``config.default_writer``, avo: "Fetch ve build
    sirasinda deepseek api kullanilan islem kalmasin hepsi evren deepseek olmali"), so a call here that names no
    writer would reach EVREN's HTTP client instead of the patched module. The writer is read at call time and in
    one place, so this folder's intent is one fixture rather than ``provider="deepseek"`` at 81 call sites. A test
    of the real default (``test_writer_selection_360.py``) undoes it.
    """
    from revenuechaser.module_relatedness import config
    monkeypatch.setattr(config, "default_writer", lambda: "deepseek")
