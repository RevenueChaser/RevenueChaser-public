"""core/notify.py: phone notifications through ntfy (avo, 17 Nov 2026)."""
import httpx
import pytest

from RevenueChaser.core import notify


@pytest.fixture
def posts(monkeypatch):
    sent = []

    def fake_post(url, *, content, headers, timeout):
        sent.append({"url": url, "body": content.decode(), "headers": headers})
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv("RC_NTFY_URL", "http://127.0.0.1:2586/homesrv-rc")
    monkeypatch.setenv("NTFY_PUBLISH_TOKEN", "tk_test")
    return sent


def test_nothing_is_sent_without_a_url(posts, monkeypatch):
    monkeypatch.delenv("RC_NTFY_URL")
    assert notify.send("t", "m") is False
    assert posts == []


def test_send_carries_title_priority_and_token(posts):
    assert notify.send("RC Fetch done: x", "ok", priority=2, tags="white_check_mark") is True
    (p,) = posts
    assert p["url"].endswith("/homesrv-rc") and p["body"] == "ok"
    assert p["headers"] == {"Title": "RC Fetch done: x", "Priority": "2", "Tags": "white_check_mark",
                            "Authorization": "Bearer tk_test"}


def test_no_token_no_header(posts, monkeypatch):
    monkeypatch.delenv("NTFY_PUBLISH_TOKEN")
    notify.send("t", "m")
    assert "Authorization" not in posts[0]["headers"]


def test_a_title_outside_latin1_still_posts(posts):
    assert notify.send("RC Fetch done: ğ→", "ç") is True
    assert posts[0]["headers"]["Title"].startswith("RC Fetch done: ")
    assert posts[0]["body"] == "ç"


def test_a_refused_or_failed_post_never_raises(monkeypatch):
    monkeypatch.setenv("RC_NTFY_URL", "http://127.0.0.1:2586/homesrv-rc")

    def refused(url, **kw):
        return httpx.Response(403, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", refused)
    assert notify.send("t", "m") is False

    def down(url, **kw):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", down)
    assert notify.send("t", "m") is False


def test_job_end_posts_done_and_error_but_not_cancel(posts):
    assert notify.job_end({"module": "sec13f", "status": "done", "message": "12 rows"}) is True
    assert notify.job_end({"module": "sec13f", "status": "error", "error": "kaput"}) is True
    assert notify.job_end({"module": "sec13f", "status": "cancelled"}) is False
    assert notify.job_end({}) is False
    assert [p["headers"]["Title"] for p in posts] == ["RC Fetch done: sec13f", "RC Fetch failed: sec13f"]
    assert posts[1]["body"] == "kaput" and posts[1]["headers"]["Priority"] == "4"


@pytest.mark.parametrize("status,requested,title", [
    ("ok", True, "RC Build done: prices"),
    ("skipped", True, "RC Build skipped: prices"),
    ("failed", True, "RC Build failed: prices"),
    ("failed", False, "RC Build failed: prices"),
    ("killed", False, "RC Build killed: prices"),
    ("ok", False, None),
    ("skipped", False, None),
])
def test_build_end_posts_a_pressed_build_and_every_failure(posts, status, requested, title):
    notify.build_end("prices", status, "why", requested=requested)
    assert [p["headers"]["Title"] for p in posts] == ([title] if title else [])
