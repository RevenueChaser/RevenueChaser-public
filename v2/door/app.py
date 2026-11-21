"""The FastAPI wiring of the v2 door: four read routes, the guards around them, and the static v2 web files.

Run plan row 6 (#1264, epic #1238). Everything the routes decide lives in :mod:`v2.door.boards` and
:mod:`v2.door.health`; this module is the HTTP surface and the guards, so a change to a rule is a change to a
tested function and not to a decorator.

**Read only, by construction.** The proxy and its Read / Write classes are step 7. Until then the door refuses
every method but ``GET``, ``HEAD`` and ``OPTIONS`` with 405 — not because no write route is declared (that is true
today and would silently stop being true), but because the guard sits in front of every route the app will ever
have. ``v2/tests/test_door_app.py`` fails if the guard stops holding.
"""
from __future__ import annotations

import gzip
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from RevenueChaser.core import v2_envelope
from RevenueChaser.v2.door import boards, config, health

READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

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
        if request.method.upper() not in READ_METHODS:
            response: Response = JSONResponse(
                {"detail": "the v2 door is read-only; the write classes are step 7"},
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


app = create_app()
