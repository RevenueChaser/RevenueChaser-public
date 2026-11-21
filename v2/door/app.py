"""The FastAPI wiring of the v2 door: four read routes, the guards around them, and the static v2 web files.

Run plan row 6 (#1264, epic #1238). Everything the routes decide lives in :mod:`v2.door.boards` and
:mod:`v2.door.health`; this module is the HTTP surface and the guards, so a change to a rule is a change to a
tested function and not to a decorator.

**One prefix writes, and nothing else.** Step 7 (#1317) adds the proxy under ``/api/v1/proxy``; everywhere else
the door still refuses every method but ``GET``, ``HEAD`` and ``OPTIONS`` with 405 — not because no write route is
declared there, which would silently stop being true, but because the guard sits in front of every route the app
has. ``v2/tests/test_door_app.py`` fails if the guard stops holding.

What the proxy lets through is :func:`v2.door.proxy.decide` and nothing in this module: the handler below asks it,
forwards when it says so, and writes the line. A rule read here would be a rule that could not be mutation-tested.
"""
from __future__ import annotations

import gzip
import time
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from RevenueChaser.core import v2_envelope
from RevenueChaser.v2.door import boards, config, health, proxy, writelog

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# The one prefix a write may arrive on. Everything under it is classified by the route table; everything outside it
# is read-only, as it was in step 6.
PROXY_PREFIX = f"{config.API_PREFIX}/proxy"

# Where the `web` job's build lands (`v2/README.md` decision 6). Mounted when it is there; a door started from a
# checkout that has never run `npm run build` serves the API and says so at `/`, rather than failing to start.
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def content_security_policy() -> str:
    """The door's CSP: its own origin, plus the Grafana origin as the one thing its pages may frame.

    No CDN is named, ever (`v2/README.md` decision 2): v2 runs on a tailnet with no guaranteed outbound internet.
    ``frame-ancestors 'none'`` is the other direction — nothing may frame the door — and is why Grafana's own
    header, not this one, is what lets the v2 Settings screen show the RC boards (home-server
    `units/grafana-server.service.d/life.conf`).
    """
    frame = config.grafana_origin()
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        f"frame-src {frame}" if frame else "frame-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    ])


def create_app() -> FastAPI:
    """The door's app. Built by a function, not at import, so a test can build one per environment."""
    app = FastAPI(title="RevenueChaser v2 door", version=config.DOOR_VERSION,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.allowed_hosts()))

    @app.middleware("http")
    async def read_only(request: Request, call_next):
        """405 for anything but a read, and the door's headers on every answer."""
        if request.method.upper() not in READ_METHODS and not request.url.path.startswith(f"{PROXY_PREFIX}/"):
            response: Response = JSONResponse(
                {"detail": f"only {PROXY_PREFIX} takes a write; every other route of the door is read-only"},
                status_code=405, headers={"Allow": ", ".join(sorted(READ_METHODS))})
        else:
            response = await call_next(request)
        response.headers["Content-Security-Policy"] = content_security_policy()
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    _routes(app)
    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
    else:
        @app.get("/", include_in_schema=False)
        def no_web() -> Response:
            return Response(f"v2 web files are not built ({WEB_DIST}); {config.API_PREFIX} answers\n",
                            media_type="text/plain; charset=utf-8")
    return app


def _routes(app: FastAPI) -> None:
    api = config.API_PREFIX

    @app.get(f"{api}/health")
    def get_health() -> Response:
        """One probe per dependency, each with a 2 s budget; 503 when a required probe is red."""
        result = health.run()
        return JSONResponse(result, status_code=200 if result["status"] == "ok" else 503,
                            headers={"Cache-Control": "no-store"})

    @app.get(f"{api}/version")
    def get_version() -> Response:
        """Which commit is serving, which envelope contract it speaks, and the boards it knows."""
        return JSONResponse({"door_version": config.DOOR_VERSION,
                             "build_sha": config.build_sha(),
                             "envelope_schema_version": v2_envelope.ENVELOPE_SCHEMA_VERSION,
                             "boards": list(boards.board_keys())},
                            headers={"Cache-Control": "no-store"})

    @app.get(f"{api}/boards")
    def get_boards() -> Response:
        """Every board's metadata and whether its envelope is present — never a board's rows."""
        return JSONResponse({"boards": boards.board_list()}, headers={"Cache-Control": "no-cache"})

    @app.get(f"{api}/boards/{{board}}")
    def get_board(board: str, request: Request) -> Response:
        """One board's envelope, served gzip as stored — the same bytes, not a re-serialisation.

        ``Content-Encoding: gzip`` when the client accepts it (every browser does), so nothing is compressed per
        request and the ``data`` the door hands over is byte for byte the ``data`` ``write_board`` hashed. A client
        that does not accept gzip gets it decompressed here, as the dashboard's payload route does.
        """
        try:
            raw = boards.stored_bytes(board)
        except boards.UnknownBoard:
            return JSONResponse({"detail": f"unknown board: {board}"}, status_code=404)
        except boards.NoEnvelope:
            return JSONResponse({"detail": f"no envelope for {board} yet"}, status_code=404)
        headers = {"Cache-Control": "no-cache", "Vary": "Accept-Encoding"}
        if "gzip" in request.headers.get("accept-encoding", ""):
            headers["Content-Encoding"] = "gzip"
            return Response(raw, media_type="application/json", headers=headers)
        return Response(gzip.decompress(raw), media_type="application/json", headers=headers)

    @app.api_route(f"{PROXY_PREFIX}/{{path:path}}", methods=["GET", "POST"])
    async def proxied(path: str, request: Request) -> Response:
        """One of the dashboard's routes, pressed under its class — Read, Write or Guarded.

        ``async def`` so the body is read without blocking, and :func:`v2.door.proxy.forward` — a blocking
        loopback call with a timeout — is handed to the threadpool, so one slow press does not stop the event loop
        and with it the health route a monitor is reading.

        The method is the caller's, not a guessed one: the prefix declares ``GET`` and ``POST``, and the route
        table decides which of the two a given path answers. Anything else gets FastAPI's own 405 before this runs.
        """
        upstream_path = "/" + path
        decision = proxy.decide(request.method, upstream_path, request.headers)
        started = time.monotonic()
        answer, status = await _answer(decision, request)
        _log(decision, request, upstream_path, status, started)
        return answer


async def _answer(decision: proxy.Decision, request: Request) -> tuple[Response, int]:
    """The answer this decision leads to, and the status the write log records.

    A refusal never reaches :func:`v2.door.proxy.forward`: the only call to it is below the ``allowed`` check, so
    a route the table guards cannot be pressed by a bug in the error handling either.
    """
    if not decision.allowed:
        return JSONResponse({"detail": decision.reason,
                             "klass": decision.klass.value if decision.klass else None},
                            status_code=decision.status), decision.status
    body = await request.body()
    if len(body) > proxy.MAX_BODY_BYTES:
        # Settings' presses are small JSON objects or empty. A door that streamed an unbounded body to the
        # dashboard would be a way to spend the dashboard's memory through the door.
        return JSONResponse({"detail": f"a press carries at most {proxy.MAX_BODY_BYTES} bytes"},
                            status_code=413), 413
    try:
        status, headers, out = await run_in_threadpool(
            proxy.forward, request.method, decision.upstream_path, request.url.query,
            proxy.forwarded_headers(request.headers), body)
    except proxy.UnsafeUpstream as exc:
        # The misconfiguration is the box's, so it is named; the caller is told nothing about where the door
        # would have gone, because that is the one value worth keeping to ourselves here.
        return JSONResponse({"detail": f"the door's upstream is misconfigured: {exc}"}, status_code=500), 500
    except proxy.UpstreamUnreachable:
        return JSONResponse({"detail": "the dashboard did not answer"}, status_code=504), 504
    return Response(out, status_code=status, media_type=headers.get("Content-Type", "application/json"),
                    headers={"Cache-Control": "no-store"}), status


def _log(decision: proxy.Decision, request: Request, path: str, status: int, started: float) -> None:
    """One write-log line, when the class is one the log is for (a read is not)."""
    if not writelog.should_record(decision):
        return
    writelog.record(decision, method=request.method, path=path, login=proxy.login_of(request.headers),
                    status=status, duration_ms=int((time.monotonic() - started) * 1000))


app = create_app()
