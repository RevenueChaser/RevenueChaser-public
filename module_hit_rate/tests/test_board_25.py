"""#25: the Hit Rate board's data and page (``module_hit_rate/board.py``)."""
from __future__ import annotations

from datetime import date, timedelta

from revenuechaser.module_hit_rate import board

D0 = date(2026, 1, 5)


def _picks(n=30, horizon=30, mfe=0.25):
    return [{"source": "swing", "subject": f"T{i}", "forecast_date": D0 + timedelta(days=i % 3),
             "model_version": "s1", "horizon_days": horizon, "status": "closed", "mfe": mfe} for i in range(n)]


def _base(day, n, ge10):
    return {"forecast_date": day, "horizon_days": 30, "n": n, "ge20": 0, "ge10": ge10, "ge5": n}


def test_a_readable_board_is_set_against_the_universe_on_its_own_freeze_dates():
    base = [_base(D0, 100, 40), _base(D0 + timedelta(days=1), 100, 20), _base(D0 + timedelta(days=2), 100, 30),
            _base(D0 + timedelta(days=9), 100, 100)]           # not a freeze date of the board: left out
    data = board.build(_picks(), base)
    thirty = next(h for h in data["horizons"] if h["horizon"] == 30)
    line, = thirty["lines"]
    assert line["readable"] and line["ge10"] == 1.0
    assert line["universe"]["ge10"] == 0.3 and line["universe"]["ge5"] == 1.0


def test_an_unreadable_board_shows_its_counts_and_no_rate():
    data = board.build(_picks(n=10), [])
    line, = next(h for h in data["horizons"] if h["horizon"] == 30)["lines"]
    assert not line["readable"] and line["universe"] is None
    page = board.render_html(data)
    assert "Not readable yet" in page and "10 closed records" in page


def test_no_picks_is_an_explicit_empty_state():
    assert "No frozen picks yet." in board.render_html(board.build([], []))


def test_the_tab_renders_from_an_empty_store():
    from revenuechaser.app import dashboard
    r = dashboard.app.test_client().get("/view/module_hit_rate")
    assert r.status_code == 200 and "Hit Rate" in r.get_data(as_text=True)
