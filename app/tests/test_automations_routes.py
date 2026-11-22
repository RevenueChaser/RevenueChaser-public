"""/api/automations routes and the rule that nothing reaches the scheduler on its own (#130)."""
from __future__ import annotations

import pytest

from revenuechaser.app import dashboard
from revenuechaser.core import automations as A


@pytest.fixture
def fake():
    f = A.FakeScheduler()
    A.set_scheduler(f)
    yield f
    A.set_scheduler(None)


_HDR = {"X-RC-Panel": "automations"}


class _Client:
    """The test client, sending the panel's header on POST like the real panel does."""

    def __init__(self, c):
        self._c = c

    def post(self, *a, headers=None, **k):
        return self._c.post(*a, headers={**_HDR, **(headers or {})}, **k)

    def __getattr__(self, name):
        return getattr(self._c, name)


@pytest.fixture
def client():
    return _Client(dashboard.app.test_client())


def test_get_lists_registry_rows_with_live_state(client, fake):
    d = client.get("/api/automations").get_json()
    assert d["ok"] and d["available"]
    assert [r["name"] for r in d["rows"]] == [e.name for e in A.REGISTRY]
    assert {r["state"] for r in d["rows"]} == {"not_installed"}
    assert fake.mutations == []






def test_unknown_name_is_404_and_touches_nothing(client, fake):
    r = client.post("/api/automations/Some%20Other%20Task/remove")
    assert r.status_code == 404
    assert "Some" not in r.get_data(as_text=True)
    assert fake.calls == []












def test_settings_collect_carries_static_rows_and_never_calls_the_scheduler(rawstore_tmp_db, fake):
    from revenuechaser.module_settings import inventory
    payload = inventory.collect()
    assert [r["name"] for r in payload["automations"]] == [e.name for e in A.REGISTRY]
    assert "state" not in payload["automations"][0]
    assert fake.calls == []










def test_one_failing_row_still_answers_200(client):
    class Broken(A.FakeScheduler):
        def status(self, name):
            raise A.AutomationError("unreadable scheduler answer")

    A.set_scheduler(Broken())
    try:
        r = client.get("/api/automations")
        assert r.status_code == 200
        assert {x["state"] for x in r.get_json()["rows"]} == {"error"}
    finally:
        A.set_scheduler(None)
