"""Text settings in ``board_settings.value_text`` (#360, avo 2 Nov 2026: "evet ekle")."""
from __future__ import annotations

import pytest

from RevenueChaser.core import board_settings, rawstore
from RevenueChaser.core.board_settings import Setting

BOARD = "test_text_board"


@pytest.fixture
def text_board(rawstore_tmp_db, monkeypatch):
    specs = {"PICK": Setting("PICK", "text", lambda: "alpha", choices=lambda: ("alpha", "beta", "gamma")),
             "N": Setting("N", "int", lambda: 5, lo=1, hi=9)}
    monkeypatch.setitem(board_settings.SPEC, BOARD, (lambda: specs, lambda v: []))
    return specs












def test_describe_names_the_text_kind(text_board):
    row = {r["key"]: r for r in board_settings.describe(BOARD)}["PICK"]
    assert row["kind"] == "text" and row["choices"] == ["alpha", "beta", "gamma"] and row["value"] == "alpha"
