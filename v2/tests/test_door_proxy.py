"""v2 step 7 (#1317): the door's proxy — its route table, the three classes and the one function that authorises.

Everything a request is allowed or refused by lives in :func:`v2.door.proxy.decide`, which takes a method, a path
and the request's headers and returns a decision. That is deliberate: route authorisation is the kind of logic the
repository asks for a mutation check on, and a mutation check needs one named function to mutate. A decorator or a
chain of ``if`` statements spread through ``app.py`` could not be read red.

The rules these tests hold to, each from the run plan's row 7 and the Grok round-1 blocker it answers
(``/mnt/project-files/gui_redesign/revenuechaser_v2_plan.md`` §9 item 1):

* only a **named** route is proxied at all — anything else is 404, never forwarded;
* class **Guarded** is refused outright, by both methods, and is never forwarded;
* a **Write** needs ``Tailscale-User-Login``, and the caller's own ``X-RC-Panel`` is passed through rather than
  minted by the door, so the dashboard's cross-site check still sees the caller;
* the upstream is loopback or the door refuses to start, so no environment variable turns the proxy into a relay;
* every write and every guarded press is written to the write log, and the log carries no body and no header but
  the login.
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.v2.door import config, proxy, writelog

LOGIN = {"tailscale-user-login": "tester@tailnet.invalid", "x-rc-panel": "v2"}


# ── the route table ─────────────────────────────────────────────────────────────────────────────────────────────

def test_every_route_in_the_table_carries_one_of_the_three_classes():
    assert proxy.ROUTES, "the table is empty"
    for route in proxy.ROUTES:
        assert isinstance(route.klass, proxy.RouteClass), route
    assert {r.klass for r in proxy.ROUTES} == set(proxy.RouteClass), "a class has no route"


def test_the_table_names_no_route_twice():
    patterns = [r.pattern for r in proxy.ROUTES]
    assert len(patterns) == len(set(patterns)), "a path is classified twice"


def test_every_pattern_is_an_absolute_path_with_no_wildcard_segment():
    for route in proxy.ROUTES:
        assert route.pattern.startswith("/"), route.pattern
        assert ":path}" not in route.pattern, f"{route.pattern} would match any depth"
        assert ".." not in route.pattern, route.pattern


def test_the_three_presses_avo_reserved_for_himself_are_guarded():
    """The builder timer, the Value Chain sync and a watch-list delete are never pressed through the door."""
    for path in ("/api/build/timer", "/run/module_value_chain", "/api/watchlists/list-7/delete"):
        route = proxy.classify(path)
        assert route is not None, f"{path} is not in the table at all, so a later edit could open it"
        assert route.klass is proxy.RouteClass.GUARDED, path


def test_no_route_that_spends_or_deletes_is_classified_read():
    """A Read is forwarded without a login, so a route that changes anything must never be one."""
    for route in proxy.ROUTES:
        if route.klass is not proxy.RouteClass.READ:
            continue
        for verb in ("/delete", "/remove", "/cancel", "/timer", "/run/"):
            assert verb not in route.pattern, f"{route.pattern} is Read but reads like a press"


# ── the decision ────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_path_that_is_not_in_the_table_is_not_proxied():
    d = proxy.decide("GET", "/api/made/up", {})
    assert not d.allowed and d.status == 404 and d.klass is None


def test_a_read_is_allowed_with_no_login_at_all():
    d = proxy.decide("GET", "/api/settings/status", {})
    assert d.allowed and d.klass is proxy.RouteClass.READ
    assert d.upstream_path == "/api/settings/status"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_a_read_route_pressed_with_a_write_method_is_405_not_a_write(method):
    d = proxy.decide(method, "/api/settings/status", LOGIN)
    assert not d.allowed and d.status == 405


def test_a_write_with_a_login_and_the_panel_header_is_allowed():
    d = proxy.decide("POST", "/api/build/request/spine/security", LOGIN)
    assert d.allowed and d.klass is proxy.RouteClass.WRITE
    assert d.upstream_path == "/api/build/request/spine/security"


def test_a_write_without_a_login_is_refused_403():
    d = proxy.decide("POST", "/api/build/request/spine/security", {"x-rc-panel": "v2"})
    assert not d.allowed and d.status == 403
    assert "login" in d.reason


def test_a_blank_login_is_no_login():
    headers = {"tailscale-user-login": "   ", "x-rc-panel": "v2"}
    assert not proxy.decide("POST", "/api/build/request/spine/security", headers).allowed


def test_a_write_without_the_callers_panel_header_is_refused():
    """The door never mints ``X-RC-Panel``: the dashboard's own check must see the caller, not the door."""
    headers = {"tailscale-user-login": "tester@tailnet.invalid"}
    d = proxy.decide("POST", "/api/build/request/spine/security", headers)
    assert not d.allowed and d.status == 403 and "panel" in d.reason


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_a_guarded_route_is_refused_by_both_methods_even_with_a_login(method):
    d = proxy.decide(method, "/api/build/timer", LOGIN)
    assert not d.allowed and d.status == 403
    assert d.klass is proxy.RouteClass.GUARDED
    assert not d.upstream_path, "a guarded route must not even name an upstream path"


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_a_write_the_browser_says_came_from_another_page_is_refused(site):
    """Another port on the same host is ``same-site``, which is why that value counts as another site (#231)."""
    d = proxy.decide("POST", "/api/build/request/spine/security", {**LOGIN, "sec-fetch-site": site})
    assert not d.allowed and d.status == 403


@pytest.mark.parametrize("site", ["same-origin", "none", ""])
def test_the_doors_own_pages_and_the_address_bar_are_not_another_site(site):
    assert proxy.decide("POST", "/api/build/request/spine/security", {**LOGIN, "sec-fetch-site": site}).allowed


def test_an_origin_outside_the_host_allowlist_is_refused():
    d = proxy.decide("POST", "/api/build/request/spine/security",
                     {**LOGIN, "origin": "https://someone-elses.example"})
    assert not d.allowed and d.status == 403


def test_the_literal_null_origin_is_refused():
    d = proxy.decide("POST", "/api/build/request/spine/security", {**LOGIN, "origin": "null"})
    assert not d.allowed and d.status == 403


def test_the_doors_own_origin_is_accepted(monkeypatch):
    monkeypatch.setenv("RC_DOOR_HOSTS", "127.0.0.1,homesrv.example")
    d = proxy.decide("POST", "/api/build/request/spine/security",
                     {**LOGIN, "origin": "https://homesrv.example:8100"})
    assert d.allowed


def test_the_header_names_are_matched_whatever_their_case():
    headers = {"Tailscale-User-Login": "tester@tailnet.invalid", "X-RC-Panel": "v2"}
    assert proxy.decide("POST", "/api/build/request/spine/security", headers).allowed


# ── the path, rebuilt and never passed through ──────────────────────────────────────────────────────────────────

def test_the_upstream_path_is_rebuilt_from_the_pattern_and_the_matched_segments():
    d = proxy.decide("GET", "/api/job/abc-123", {})
    assert d.allowed and d.upstream_path == "/api/job/abc-123"


@pytest.mark.parametrize("path", [
    "/api/job/../../api/build/timer",
    "/api/job/a%2f..%2fb",
    "/api/job/a/b",
    "/api/job/",
    "//api/job/x",
    "/api/job/a b",
])
def test_a_segment_that_is_not_one_plain_segment_is_not_proxied(path):
    """The forwarded path is rebuilt from the table, so a traversal cannot reach a route the table never named."""
    d = proxy.decide("GET", path, {})
    assert not d.allowed, f"{path} was allowed as {d.upstream_path!r}"


def test_a_trailing_slash_is_not_the_same_route():
    assert not proxy.decide("GET", "/api/settings/status/", {}).allowed


# ── the upstream ────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_upstream_defaults_to_the_dashboard_on_loopback():
    assert proxy.upstream_base() == "http://127.0.0.1:8000"


@pytest.mark.parametrize("url", [
    "http://example.com:8000",
    "http://10.0.0.5:8000",
    "https://homesrv.rhinoceros-dominant.ts.net:8000",
    "file:///etc/passwd",
    "http://127.0.0.1:8000@example.com",
])
def test_an_upstream_that_is_not_loopback_is_refused(monkeypatch, url):
    """The dashboard is on the same box. A door that would forward anywhere else is a relay, so it refuses."""
    monkeypatch.setenv("RC_DOOR_UPSTREAM", url)
    with pytest.raises(proxy.UnsafeUpstream):
        proxy.upstream_base()


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000"])
def test_a_loopback_upstream_is_accepted(monkeypatch, url):
    monkeypatch.setenv("RC_DOOR_UPSTREAM", url)
    assert proxy.upstream_base() == url


def test_only_the_named_headers_are_forwarded_upstream():
    """The caller's identity and panel header go; a cookie or an authorization header never does."""
    sent = proxy.forwarded_headers({**LOGIN, "cookie": "session=secret", "authorization": "Bearer t",
                                    "content-type": "application/json", "host": "evil.example"})
    assert set(sent) == {"X-RC-Panel", "Tailscale-User-Login", "Content-Type"}
    assert sent["Tailscale-User-Login"] == "tester@tailnet.invalid"
    assert sent["X-RC-Panel"] == "v2"


def test_the_forwarded_panel_header_is_the_callers_value_not_one_the_door_invented():
    assert proxy.forwarded_headers({**LOGIN, "x-rc-panel": "settings"})["X-RC-Panel"] == "settings"


# ── the write log ───────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def log_file(tmp_path, monkeypatch):
    path = tmp_path / "writes.log"
    monkeypatch.setenv("RC_DOOR_WRITE_LOG", str(path))
    return path


def _lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_an_allowed_write_is_logged_with_its_login_class_and_status(log_file):
    writelog.record(proxy.decide("POST", "/api/build/request/spine/security", LOGIN),
                    method="POST", path="/api/build/request/spine/security",
                    login="tester@tailnet.invalid", status=200, duration_ms=12)
    row, = _lines(log_file)
    assert row["login"] == "tester@tailnet.invalid"
    assert row["klass"] == "write" and row["outcome"] == "allowed" and row["status"] == 200
    assert row["path"] == "/api/build/request/spine/security"
    assert row["ts"].endswith("Z")


def test_a_refused_guarded_press_is_logged_with_its_reason(log_file):
    d = proxy.decide("POST", "/api/build/timer", LOGIN)
    writelog.record(d, method="POST", path="/api/build/timer", login="tester@tailnet.invalid",
                    status=403, duration_ms=0)
    row, = _lines(log_file)
    assert row["klass"] == "guarded" and row["outcome"] == "refused" and row["status"] == 403
    assert row["reason"] == d.reason


def test_the_log_carries_no_body_no_query_and_no_header_but_the_login(log_file):
    writelog.record(proxy.decide("POST", "/api/build/request/spine/security", LOGIN),
                    method="POST", path="/api/build/request/spine/security",
                    login="tester@tailnet.invalid", status=200, duration_ms=1)
    row, = _lines(log_file)
    assert set(row) == {"ts", "login", "method", "path", "klass", "outcome", "reason", "status", "duration_ms"}


def test_a_login_cannot_forge_a_second_log_line(log_file):
    """A header value is a caller's text: one press is one line, whatever newlines the value holds."""
    writelog.record(proxy.decide("POST", "/api/build/timer", LOGIN), method="POST", path="/api/build/timer",
                    login="a@b.invalid\n{\"login\": \"root\"}", status=403, duration_ms=0)
    rows = _lines(log_file)
    assert len(rows) == 1
    assert "\n" not in rows[0]["login"]


def test_an_overlong_login_is_truncated_rather_than_written_whole(log_file):
    writelog.record(proxy.decide("POST", "/api/build/timer", LOGIN), method="POST", path="/api/build/timer",
                    login="x" * 5000, status=403, duration_ms=0)
    assert len(_lines(log_file)[0]["login"]) <= writelog.MAX_LOGIN_CHARS


def test_with_no_log_path_set_the_record_still_works_and_writes_no_file(tmp_path, monkeypatch):
    """The container is ``read_only: true``; the line goes to the process log, which journald keeps."""
    monkeypatch.delenv("RC_DOOR_WRITE_LOG", raising=False)
    assert config.write_log_path() is None
    writelog.record(proxy.decide("POST", "/api/build/timer", LOGIN), method="POST", path="/api/build/timer",
                    login="tester@tailnet.invalid", status=403, duration_ms=0)
    assert not list(tmp_path.iterdir())


def test_a_read_is_not_written_to_the_write_log(log_file):
    assert writelog.should_record(proxy.decide("GET", "/api/settings/status", {})) is False
    for klass in (proxy.RouteClass.WRITE, proxy.RouteClass.GUARDED):
        assert writelog.should_record(proxy.Decision(False, 403, klass, "x")) is True


# ── the HTTP surface ────────────────────────────────────────────────────────────────────────────────────────────
#
# The unit tier opens no socket at all (the root ``conftest.py`` raises ``NetworkAccessAttempted``), so the
# forwarding itself is stubbed here and driven over a real socket in ``module_testing/e2e/test_v2_door.py``.
# What these tests are for is the wiring: that the method guard lets a proxy write through and nothing else, and
# that a refusal never reaches :func:`proxy.forward`.

fastapi_testclient = pytest.importorskip("fastapi.testclient")

HOST = "127.0.0.1"


@pytest.fixture
def client(monkeypatch, log_file):
    """A door whose proxy records what it would have forwarded instead of forwarding it."""
    from revenuechaser.v2.door import app as door_app

    monkeypatch.setenv("RC_DOOR_HOSTS", HOST)
    sent = []

    def fake_forward(method, upstream_path, query, headers, body):
        sent.append({"method": method, "path": upstream_path, "query": query, "headers": headers, "body": body})
        return 200, {"Content-Type": "application/json"}, b'{"ok": true}'

    monkeypatch.setattr(proxy, "forward", fake_forward)
    with fastapi_testclient.TestClient(door_app.create_app(), base_url=f"http://{HOST}:8100") as c:
        c.sent = sent
        c.log_file = log_file
        yield c


def _url(path: str) -> str:
    return f"{config.API_PREFIX}/proxy{path}"


def test_a_proxied_read_is_forwarded_and_answered(client):
    r = client.get(_url("/api/settings/status"))
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert client.sent[0]["path"] == "/api/settings/status"


def test_a_proxied_read_keeps_the_query_string(client):
    client.get(_url("/api/settings/lookup/AAPL"), params={"force": "1"})
    assert client.sent[0]["query"] == "force=1"


def test_a_proxied_write_with_a_login_is_forwarded_with_the_callers_headers(client):
    r = client.post(_url("/api/build/request/spine/security"), headers={
        "Tailscale-User-Login": "tester@tailnet.invalid", "X-RC-Panel": "v2"})
    assert r.status_code == 200
    assert client.sent[0]["headers"]["Tailscale-User-Login"] == "tester@tailnet.invalid"
    assert client.sent[0]["headers"]["X-RC-Panel"] == "v2"


def test_a_write_without_a_login_is_403_and_is_never_forwarded(client):
    r = client.post(_url("/api/build/request/spine/security"), headers={"X-RC-Panel": "v2"})
    assert r.status_code == 403
    assert client.sent == [], "a refused write reached the dashboard"


@pytest.mark.parametrize("path", ["/api/build/timer", "/run/module_value_chain", "/api/watchlists/list-7/delete"])
def test_every_guarded_route_is_403_over_http_and_never_forwarded(client, path):
    for call in (client.post, client.get):
        r = call(_url(path), headers={"Tailscale-User-Login": "tester@tailnet.invalid", "X-RC-Panel": "v2"})
        assert r.status_code == 403, path
    assert client.sent == [], path


def test_a_path_the_table_does_not_name_is_404_and_never_forwarded(client):
    assert client.post(_url("/api/build/switch/does-not-exist/extra/depth"), headers={
        "Tailscale-User-Login": "tester@tailnet.invalid", "X-RC-Panel": "v2"}).status_code == 404
    assert client.get(_url("/api/made/up")).status_code == 404
    assert client.sent == []


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_the_proxy_prefix_takes_only_get_and_post(client, method):
    r = client.request(method, _url("/api/build/request/spine/security"), headers={
        "Tailscale-User-Login": "tester@tailnet.invalid", "X-RC-Panel": "v2"})
    assert r.status_code == 405
    assert client.sent == []


def test_the_read_routes_outside_the_proxy_are_still_read_only(client):
    """Step 7 opens one prefix and not the door: a POST anywhere else is still refused by the method guard."""
    for path in (f"{config.API_PREFIX}/boards", f"{config.API_PREFIX}/health", "/"):
        assert client.post(path).status_code == 405, path


def test_a_proxied_write_leaves_a_line_in_the_write_log(client):
    client.post(_url("/api/build/request/spine/security"), headers={
        "Tailscale-User-Login": "tester@tailnet.invalid", "X-RC-Panel": "v2"})
    row, = _lines(client.log_file)
    assert row["outcome"] == "allowed" and row["klass"] == "write"
    assert row["path"] == "/api/build/request/spine/security"


def test_a_refused_write_leaves_a_line_too(client):
    client.post(_url("/api/build/timer"), headers={
        "Tailscale-User-Login": "tester@tailnet.invalid", "X-RC-Panel": "v2"})
    row, = _lines(client.log_file)
    assert row["outcome"] == "refused" and row["klass"] == "guarded" and row["status"] == 403


def test_a_proxied_read_leaves_no_line(client):
    client.get(_url("/api/settings/status"))
    assert not client.log_file.exists() or not _lines(client.log_file)


def test_the_proxy_answers_carry_the_doors_own_headers(client):
    r = client.get(_url("/api/settings/status"))
    assert "Content-Security-Policy" in r.headers
    assert r.headers["X-Content-Type-Options"] == "nosniff"


# ── the rules that are about the file rather than a call ─────────────────────────────────────────────────────────

_DOOR = __import__("pathlib").Path(proxy.__file__).parent
_DOC = (_DOOR.parents[1] / "docs" / "v2" / "door.md").read_text(encoding="utf-8")


def test_the_proxy_and_the_write_log_add_no_third_party_package_to_the_image():
    """The image installs ``v2/door/requirements.txt`` alone, and a loopback proxy needs nothing beyond stdlib.

    ``httpx`` would be the obvious reach and is deliberately not taken: it would be a fourth pinned dependency,
    a line in ``THIRD-PARTY-NOTICES.md`` and a megabyte in a door whose whole job is a handful of small presses.
    """
    import ast
    import sys
    allowed = {"revenuechaser", "__future__"}
    for name in ("proxy.py", "writelog.py"):
        tree = ast.parse((_DOOR / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                root = module.split(".")[0]
                assert root in sys.stdlib_module_names or root in allowed, f"{name} imports {module}"


def test_the_doc_names_every_route_in_the_table_with_its_class():
    """A route table in code and a different one in the doc is how a Guarded route quietly becomes a Write."""
    for route in proxy.ROUTES:
        assert f"`{route.pattern}`" in _DOC, f"{route.pattern} is not in docs/v2/door.md"
    for klass in proxy.RouteClass:
        assert f"**{klass.value.capitalize()}**" in _DOC, klass


def test_the_doc_states_the_prefix_and_the_timeout_the_code_owns():
    from revenuechaser.v2.door import app as door_app
    assert f"`{door_app.PROXY_PREFIX}`" in _DOC
    assert f"{config.UPSTREAM_TIMEOUT_S:g} s" in _DOC.replace("**", "")
    for variable in ("RC_DOOR_UPSTREAM", "RC_DOOR_WRITE_LOG"):
        assert variable in _DOC, variable
