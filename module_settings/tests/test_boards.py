"""Board-inputs cards: read each board's rendered payload, store-only."""
from __future__ import annotations

import json

import pytest

from RevenueChaser.module_comovement import config as cfg
from RevenueChaser.module_settings import boards


def _steps(result=60):
    return [
        {"key": "scanned", "label": "Scanned", "count": 100, "kind": "start", "fix": None},
        {"key": "below_floor", "label": "Below floor", "count": 30, "kind": "drop",
         "by_design": True, "fix": None},
        {"key": "no_prices", "label": "No prices", "count": 10, "kind": "drop",
         "by_design": False, "fix": {"route": "/run/module_comovement",
                                     "label": "Fetch prices"}},
        {"key": "clustered", "label": "Clustered", "count": result, "kind": "result",
         "fix": None},
    ]


def _payload(**over):
    p = {"as_of": "2026-09-25T20:00:00+00:00", "generated_at": "2026-09-25T20:00:00+00:00",
         "window_start": "2025-09-25", "oos_start": "2026-06-25", "prices_through":
         "2026-09-25", "funnel_steps": _steps()}
    p.update(over)
    return p


@pytest.fixture
def payload_file(tmp_path, monkeypatch):
    path = tmp_path / "comovement_latest.json"
    monkeypatch.setattr(cfg, "COMOVEMENT_JSON", path)
    return path


def _card(key="module_comovement"):
    cards = boards.board_cards()
    return next(c for c in cards if c["key"] == key)


def test_ok_card(payload_file):
    payload_file.write_text(json.dumps(_payload()), encoding="utf-8")
    c = _card()
    assert c["state"] == "ok" and c["error"] is None
    assert c["key"] == "module_comovement" and c["label"] == "Co-movement"
    # #126/#642 N1: the bars and the universe are served needs, so the card names no board-file table here.
    assert c["tables"] == [] and "prices.bars" in c["needs"]
    assert "dividend-adjusted" in c["price_basis"] and "yfinance" not in c["price_basis"]
    assert c["as_of"] == "2026-09-25T20:00:00+00:00"
    assert c["window"]["window_start"] == "2025-09-25"
    assert c["window"]["prices_through"] == "2026-09-25"
    assert [s["key"] for s in c["funnel_steps"]][0] == "scanned"


def test_missing_payload_is_not_rendered(payload_file):
    c = _card()
    assert c["state"] == "not_rendered"
    assert c["funnel_steps"] == []


def test_old_payload_without_steps_is_no_funnel(payload_file):
    p = _payload()
    del p["funnel_steps"]
    payload_file.write_text(json.dumps(p), encoding="utf-8")
    assert _card()["state"] == "no_funnel"
    payload_file.write_text(json.dumps(_payload(funnel_steps=[])), encoding="utf-8")
    assert _card()["state"] == "no_funnel"


def test_steps_that_do_not_add_up_are_invalid(payload_file):
    payload_file.write_text(json.dumps(_payload(funnel_steps=_steps(result=59))),
                            encoding="utf-8")
    c = _card()
    assert c["state"] == "invalid"
    assert "59" in c["error"] and "60" in c["error"]


def test_corrupt_json_is_an_error_not_a_raise(payload_file):
    payload_file.write_text("{not json", encoding="utf-8")
    c = _card()
    assert c["state"] == "error" and c["error"]
    payload_file.write_text("[1, 2]", encoding="utf-8")
    assert _card()["state"] == "error"


def test_params_are_read_from_the_config_at_call_time(monkeypatch):
    entry = next(e for e in boards.BOARD_INPUTS if e["key"] == "module_comovement")
    text = " | ".join(entry["params"]())
    assert str(cfg.WINDOW) in text and str(cfg.MIN_OBS) in text
    assert str(cfg.OOS_HOLDOUT) in text and str(cfg.WINSOR_K) in text
    assert str(cfg.DEFAULT_HORIZON) in text and str(cfg.OHLC_PERIOD) in text
    assert cfg.BENCHMARKS[cfg.DEFAULT_BENCHMARK] in text
    monkeypatch.setattr(cfg, "WINDOW", 999)
    assert "999" in " | ".join(entry["params"]())




# ── editable settings block (#40 Part B) ─────────────────────────────────────


def test_the_settings_block_is_there_even_before_the_board_is_rendered(
        payload_file, rawstore_tmp_db):
    c = _card()
    assert c["state"] == "not_rendered" and c["settings"]["inputs"]


# ── the Swing card (#384 SW-S4) ─────────────────────────────────────────────




def _data_board_keys() -> list[str]:
    """Dashboard tabs that are data boards: ``TABS`` minus Settings, Logs and Runs (#26 PL5-b: read-only run log,
    no data and no Fetch)."""
    from RevenueChaser.app import dashboard

    return [t["key"] for t in dashboard.TABS
            if t["type"] == "tab" and t["key"] != "module_settings"]


def test_every_data_board_has_a_board_inputs_entry():
    """S9: the card registry is exactly the data boards, in nav order."""
    want = _data_board_keys()
    got = [e["key"] for e in boards.BOARD_INPUTS]
    assert got == want
    assert len(got) == 18


# Boards whose rendered payload emits ``funnel_steps`` (core.funnel). The rest
# are marked ``no_funnel``: the card must not invent steps or ask for a refresh.
_FUNNEL_BOARDS = ("module_comovement", "module_swing_potential",
                  "module_asymmetric_growth", "module_fundamentals")


def _entry(key):
    return next(e for e in boards.BOARD_INPUTS if e["key"] == key)




def test_a_board_that_emits_no_funnel_is_marked():
    for entry in boards.BOARD_INPUTS:
        if entry["key"] in _FUNNEL_BOARDS:
            assert entry["funnel"] == "funnel_steps", entry["key"]
        else:
            assert entry["funnel"] == "no_funnel", entry["key"]


def _valid_steps():
    from RevenueChaser.core import funnel

    return [
        funnel.step("universe", "Universe", 3, "start"),
        funnel.step("no_annual", "No annual financials", 2, "drop", by_design=False),
        funnel.step("scored", "Scored", 1, "result"),
    ]


def test_ag_and_fundamentals_cards_read_the_payload_funnel(monkeypatch, tmp_path):
    """The settings card shows the funnel the board emitted, via core.funnel."""
    from RevenueChaser.core import funnel

    steps = _valid_steps()
    for key in ("module_asymmetric_growth", "module_fundamentals"):
        path = tmp_path / f"{key}.json"
        path.write_text(json.dumps({"as_of": "2026-09-25T20:00:00+00:00",
                                    "funnel_steps": steps}), encoding="utf-8")
        monkeypatch.setitem(_entry(key), "payload_path", lambda p=path: p)
        card = _card(key)
        assert card["state"] == "ok", card
        assert funnel.validate(card["funnel_steps"]) == []
        assert [s["key"] for s in card["funnel_steps"]] == ["universe", "no_annual", "scored"]
        assert card["as_of"] == "2026-09-25T20:00:00+00:00"
        # The shared panel accepts the same steps the settings card shows.
        assert "No annual financials" in funnel.funnel_panel_html(card["funnel_steps"])
        from RevenueChaser.module_settings import report
        assert "No annual financials" in report._board_card(card)


def test_an_html_board_with_no_funnel_is_rendered_not_an_error(monkeypatch, tmp_path):
    """A page that is not JSON must not become a parse error when the board emits no funnel."""
    path = tmp_path / "earnings_radar_latest.html"
    path.write_text("<html>not json</html>", encoding="utf-8")
    monkeypatch.setitem(_entry("module_earnings_radar"), "payload_path", lambda: path)
    card = _card("module_earnings_radar")
    assert card["state"] == "ok" and card["funnel_steps"] == []


def test_a_no_funnel_board_does_not_ask_for_a_refresh(monkeypatch, tmp_path):
    """A board that emits none is not 'rendered before funnel reporting'."""
    path = tmp_path / "oipd.json"
    path.write_text(json.dumps({"as_of": "2026-09-25T20:00:00+00:00", "ticker": "SPY"}),
                    encoding="utf-8")
    monkeypatch.setitem(_entry("module_oipd"), "payload_path", lambda: path)
    card = _card("module_oipd")
    assert card["state"] == "ok"
    assert card["funnel_steps"] == []
    assert card["as_of"] == "2026-09-25T20:00:00+00:00"





# ── PR 4: the stock watch list is read from ops.sqlite, not the raw store ──

def test_the_watch_lists_card_reads_the_lists_themselves_and_not_an_artifact(rawstore_tmp_db):
    """#786: the board has no payload file, so its card is "not rendered" until avo has a list, then it carries
    the newest list write as its as-of. Its tables are the four of its own file, never an ops watch list."""
    entry = _entry("module_watchlists")
    assert entry["tables"] == ["wl_list", "wl_section", "wl_item", "wl_change"]
    assert _card("module_watchlists")["state"] == "not_rendered"
    from RevenueChaser.module_watchlists import store as wl_store
    wl_store.create_list("Growth")
    card = _card("module_watchlists")
    assert card["state"] == "ok" and card["as_of"] and card["as_of"].startswith("20")


def test_leaps_and_earnings_name_the_stock_watch_list_in_ops_not_the_store_table():
    leaps, er = _entry("module_leaps"), _entry("module_earnings_radar")
    assert "watchlist" not in leaps["tables"] and "watchlist" not in er["tables"]
    assert leaps["ops_tables"] == ["watchlist_stock"] and er["ops_tables"] == ["watchlist_stock"]
    assert boards._card(leaps)["ops_tables"] == ["watchlist_stock"]
    assert _entry("module_welcome")["ops_tables"] == ["watchlist_stock"]     # the "on my list" marks on its earnings
    assert all(e.get("ops_tables", []) == [] for e in boards.BOARD_INPUTS
               if e["key"] not in ("module_leaps", "module_earnings_radar", "module_welcome"))


def test_the_board_card_says_it_reads_the_stock_watch_list_from_ops_sqlite():
    from RevenueChaser.module_settings import report
    html = report._board_card(boards._card(_entry("module_leaps")))
    assert ('<span class="ds">Stock watch list</span><span class="tbl">(watchlist_stock)</span>' in html
            and "ops.sqlite" in html)
    assert "not claimed by any dataset" not in html


def test_ag_and_fundamentals_are_registered_with_a_funnel_reference():
    """Their funnels already exist; the card must name the payload key and the tables the scan reads."""
    ag = _entry("module_asymmetric_growth")
    assert ag["funnel"] == "funnel_steps" and ag["label"] == "Asymmetric Growth"
    assert ag["tables"] == []                                                 # the old-store tables went (#860)
    fund = _entry("module_fundamentals")
    assert fund["funnel"] == "funnel_steps" and fund["label"] == "Fundamentals"
    assert fund["tables"] == []
    assert "prices.bars" in boards._card(fund)["needs"]


# ── #642 N1: the card names what the boards read today ──────────────────────

def test_no_card_names_a_store_table_the_store_no_longer_holds():
    """Every retirement took its Settings row with it: a card may name only a table of a board file (#860)."""
    from RevenueChaser.core import rawstore
    named = {t for e in boards.BOARD_INPUTS for t in e["tables"]}
    assert named, "the cards name no table at all"
    assert sorted(named - set(rawstore.MANIFEST)) == []


def test_each_card_carries_the_needs_its_board_declares_or_plans():
    """The served reads are not typed a second time here: the card reads the board's own ``READS`` (or its planned
    reads), so the card and the flow diagram cannot disagree."""
    from RevenueChaser.rcdata.needs import boards as api_boards
    for entry in boards.BOARD_INPUTS:
        reads = api_boards.reads_of(entry["key"])
        card = boards._card(entry)
        assert card["needs"] == list(reads["needs"]), entry["key"]
        assert card["needs_declared"] is reads["declared"], entry["key"]
    fin = boards._card(_entry("module_financials"))
    assert fin["tables"] == [] and "identity.universe" in fin["needs"]


def test_the_card_names_a_served_need_with_its_provider_table_and_file():
    from RevenueChaser.module_settings import report
    html = report._board_card(boards._card(_entry("module_fundamentals")))
    assert '<span class="ds">prices.bars</span><span class="tbl">(price_bar_daily)</span>' in html
    assert "SEC EDGAR filings" in html and "fundamentals.duckdb" in html
    # A board with no declaration of its own says so, instead of claiming a measured read.
    assert "planned" in html


def test_the_old_identity_health_card_is_gone_with_its_equity_universe_text():
    """#642 N1: the S7 card left the page in PR 5 (``_nd_identity`` replaced it), but its help text stayed in the
    module and still told the reader that a job writes into ``equity_universe``, a table #860 removed."""
    from pathlib import Path
    from RevenueChaser.module_settings import report
    assert not hasattr(report, "_identity_card")
    assert "equity_universe" not in Path(report.__file__).read_text(encoding="utf-8")
