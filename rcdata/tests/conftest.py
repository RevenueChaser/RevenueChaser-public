"""rcdata test isolation: every test gets its own market roots, so ops.sqlite and the serving files never leak.

The root conftest points ``RC_MARKET_DIR`` / ``RC_MARKET_RAW_DIR`` at one scratch folder per process; that is shared
by every test the process runs, so a queue or a check row one test left would be the next test's input. rcdata reads
``config.MARKET_DIR`` at call time, so moving the two attributes is enough.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def market_roots(tmp_path, monkeypatch):
    from revenuechaser.core import config
    ssd, hdd = tmp_path / "market", tmp_path / "market_raw"
    monkeypatch.setattr(config, "MARKET_DIR", ssd)
    monkeypatch.setattr(config, "MARKET_RAW_DIR", hdd)
    monkeypatch.setenv("RC_MARKET_DIR", str(ssd))
    monkeypatch.setenv("RC_MARKET_RAW_DIR", str(hdd))
    # The process-wide read log is flushed at exit; a test's counts must not land in the scratch root after the
    # session removed it, so each test counts into its own log, which goes with it.
    from revenuechaser.rcdata import ops
    monkeypatch.setattr(ops, "read_log", ops.ReadLog(process="test"))
    return ssd, hdd


@pytest.fixture(scope="session")
def job_lists_file(tmp_path_factory):
    """A ``watchlists.duckdb`` holding the two job lists, both empty, made once per process through the store."""
    from revenuechaser.core import rawstore
    from revenuechaser.module_watchlists import store
    root, mp = tmp_path_factory.mktemp("job-lists"), pytest.MonkeyPatch()
    mp.setattr(rawstore, "STORE_DIR", root)
    try:
        store.seed_job_lists(by="test")
    finally:
        mp.undo()
    return root / rawstore.BOARDS_DIRNAME / "watchlists.duckdb"


#: Test files that start with no watch-list file at all: they test its absence or the board files' backup.
NO_JOB_LISTS = ("test_ops_watchlists", "test_backup")


@pytest.fixture(autouse=True)
def job_lists(request, job_lists_file, isolate_rawstore):
    """The option and stock lists exist, empty, as on a seeded server (plan v5 step 7g): a build reads them through
    the strict ``read.watched``, which raises when there is no list, so a build test would otherwise fail on a
    missing file it does not care about. A copy of a file, not two store writes per test."""
    if request.module.__name__.rpartition(".")[2] in NO_JOB_LISTS:
        return
    import shutil

    from revenuechaser.core import rawstore
    dest = isolate_rawstore / rawstore.BOARDS_DIRNAME / job_lists_file.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(job_lists_file, dest)


@pytest.fixture(autouse=True)
def no_backoff_wait(monkeypatch):
    """``run_request`` waits on the real clock between HTTP retries (2 s, then 4 s): a test of a failing source slept
    6 s per name (18 s in one spine test, #896). The default ``sleep`` becomes a no-op; a test that checks the waits
    passes its own ``sleep=`` and is not affected."""
    from revenuechaser.rcdata.build import base
    monkeypatch.setattr(base.run_request, "__kwdefaults__",
                        {**base.run_request.__kwdefaults__, "sleep": lambda s: None})


@pytest.fixture
def kinds_full():
    """Every dataset's own automation at raw + Parquet + DuckDB: the hourly pass these tests were written for, from
    before a dataset with no ``dataset_automation`` row read as off (the file-level mode is gone, avo 10 Nov 2026)."""
    from revenuechaser.rcdata import build, ops
    for name in build.DATASETS:
        ops.dataset_mode_set(name, "full", by="test")


class HttpMock:
    """Answers every request an ``httpx`` client (or ``httpx.get``) sends, at the transport: the HTTP boundary.

    ``add(substring, body, status=200, headers=None)`` answers the first route whose substring is in the URL; a
    callable ``body`` gets the request and returns ``(status, bytes, headers)``. Unknown URLs answer 404.
    ``requests`` keeps every request in order, so a test can assert the query string and count calls.

    ``fallback(...)`` registers the same thing behind every route, whenever it was added: what the host answers for
    a URL no test named (EDGAR publishes a daily index for every open day, not only the days a test cares about).
    """

    def __init__(self):
        self.routes: list[tuple[str, object, int, dict]] = []
        self.fallbacks: list[tuple[str, object, int, dict]] = []
        self.requests = []

    def add(self, substring: str, body=b"", status: int = 200, headers: dict | None = None) -> None:
        self.routes.append((substring, body, status, headers or {}))

    def fallback(self, substring: str, body=b"", status: int = 200, headers: dict | None = None) -> None:
        self.fallbacks.append((substring, body, status, headers or {}))

    def calls(self, substring: str = "") -> list:
        return [r for r in self.requests if substring in str(r.url)]

    def handle(self, request):
        import json as _json

        import httpx
        self.requests.append(request)
        for sub, body, status, headers in self.routes + self.fallbacks:
            if sub in str(request.url):
                if callable(body):
                    status, body, headers = body(request)
                if not isinstance(body, (bytes, str)):
                    body = _json.dumps(body)
                if isinstance(body, str):
                    body = body.encode("utf-8")
                return httpx.Response(status, content=body, headers=headers, request=request)
        return httpx.Response(404, content=b"no route", request=request)


@pytest.fixture
def http_mock(monkeypatch):
    import httpx
    mock = HttpMock()
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda self, request: mock.handle(request))
    return mock


@pytest.fixture
def fixture_text():
    from pathlib import Path
    root = Path(__file__).resolve().parent / "fixtures"
    return lambda name: (root / name).read_text(encoding="utf-8")
