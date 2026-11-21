"""The door's proxy: the route table, the three classes, and the one function that authorises a request.

Run plan row 7 (#1317, epic #1238). The dashboard on port 8000 keeps the DuckDB writer and the job queue; v2 adds
no second writer, so every press a v2 screen makes is the dashboard's own route, reached through here.

**Why a table and not decorators.** The design plan's Grok round 1 called an unguarded proxy the one blocker of
this step (`revenuechaser_v2_plan.md` §9 item 1): a door that mints ``X-RC-Panel`` itself defeats the dashboard's
own cross-site check, because that check reads only the request it received. So the rules live in :func:`decide`,
which takes a method, a path and the request's headers and answers with a :class:`Decision`. One function, with no
HTTP object in its signature:

* it is the one place to read when asking what the door lets through;
* route authorisation is the class of logic this repository requires a **mutation check** for, and a mutation
  check needs a named function to mutate;
* ``app.py`` holds no rule of its own, so a rule cannot be changed by moving a decorator.

**Three classes, and what each one means.**

``READ``
    Forwarded with no login. A Read route may not change anything, which
    ``v2/tests/test_door_proxy.py`` holds to by reading the patterns themselves.
``WRITE``
    Forwarded only with a ``Tailscale-User-Login`` and the caller's ``X-RC-Panel``, and only when the browser does
    not say the request came from another page. Logged, always, allowed or refused.
``GUARDED``
    Refused 403 and never forwarded, whatever headers it carries: the builder timer, the Value Chain sync and a
    watch-list delete are avo's own presses, and the run plan says a thread never makes them
    (`revenuechaser_v2_run_plan.md`, "What a thread never does on its own in any step"). They are **in** the table
    rather than left out of it on purpose: a route that is merely absent is a 404 today and one table edit away
    from being open, while a route classified ``GUARDED`` has to be reclassified by hand to open.

**Why the forwarded path is rebuilt.** The caller's path string is matched against a pattern and the upstream path
is then assembled from that pattern and the segments it captured, each of which must be one plain segment. A path
the table does not name cannot be forwarded, and neither can a traversal dressed up as a segment.

**Why the upstream must be loopback.** The dashboard is on the same box, on the host network. A door that would
forward to any host an environment variable named is a relay for anything that can reach the tailnet, so
:func:`upstream_base` refuses one, and that refusal is at the first request rather than silently at deploy time.

**Why stdlib ``urllib`` and not ``httpx``.** The image installs ``v2/door/requirements.txt`` alone, and a proxy of
a handful of small loopback calls needs nothing a third dependency would bring. The routes here are declared with
``def`` and so run in FastAPI's threadpool, where a blocking call with a timeout is correct.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import Enum

from RevenueChaser.v2.door import config


class RouteClass(str, Enum):
    """What the door does with a route. ``str`` so it serialises into the write log as its own word."""

    READ = "read"
    WRITE = "write"
    GUARDED = "guarded"


@dataclass(frozen=True)
class Route:
    """One upstream path, its class, and the methods it answers.

    ``pattern`` is the dashboard's own path with ``{name}`` for a single segment. A ``GUARDED`` route answers both
    methods, so pressing it with a ``GET`` is a refusal and not a 405 that hints the route might work another way.
    """

    pattern: str
    klass: RouteClass

    @property
    def methods(self) -> frozenset[str]:
        if self.klass is RouteClass.READ:
            return frozenset({"GET", "HEAD"})
        if self.klass is RouteClass.WRITE:
            return frozenset({"POST"})
        return frozenset({"GET", "HEAD", "POST"})


def _read(*patterns: str) -> tuple[Route, ...]:
    return tuple(Route(p, RouteClass.READ) for p in patterns)


def _write(*patterns: str) -> tuple[Route, ...]:
    return tuple(Route(p, RouteClass.WRITE) for p in patterns)


def _guarded(*patterns: str) -> tuple[Route, ...]:
    return tuple(Route(p, RouteClass.GUARDED) for p in patterns)


# The table. It is the allowlist: a path that matches nothing here is not proxied at all.
#
# What it covers is step 9's board, Settings, and nothing beyond it. The board presses of step 10 and the watch-list
# edits of the pilots are added by the PRs that need them, each one classified here first — which is the point of
# keeping the table in one file, away from the screens that call it.
ROUTES: tuple[Route, ...] = (
    # ── Read: what Settings shows ───────────────────────────────────────────────────────────────────────────────
    *_read(
        "/api/settings/status",
        "/api/settings/requests",
        "/api/settings/tickers",
        "/api/settings/lookup/{ticker}",
        "/api/settings/sample/{table}",
        "/api/build/queue",
        "/api/build/datasets",
        "/api/build/state",
        "/api/automations",
        "/api/jobs",
        "/api/job/{job_id}",
        "/api/idle",
        "/api/logs",
        "/api/runs",
        "/api/data_asof/{mod}",
        "/api/watchlists",
    ),
    # ── Write: the presses Settings makes ───────────────────────────────────────────────────────────────────────
    # `/api/build/request/<path:dataset>` upstream takes a dataset of one or two segments ("spine/security"), so
    # both shapes are named rather than one wildcard: a wildcard would forward a depth the table never read.
    *_write(
        "/api/build/request/{dataset}",
        "/api/build/request/{dataset}/{part}",
        "/api/build/schedule/{dataset}/{action}",
        "/api/build/schedule/{dataset}/{part}/{action}",
        "/api/build/automation-ds/{dataset}",
        "/api/build/automation-ds/{dataset}/{part}",
        "/api/build/switch/{name}",
        "/api/job/{job_id}/cancel",
        "/api/automations/{name}/{action}",
    ),
    # ── Guarded: avo's own presses, refused here and never forwarded ────────────────────────────────────────────
    *_guarded(
        "/api/build/timer",
        "/run/module_value_chain",
        "/api/watchlist/{kind}/remove/{ticker}",
        "/api/watchlists/{list_id}/delete",
        "/api/watchlists/{list_id}/symbol/remove",
        "/api/watchlists/{list_id}/section/delete",
    ),
)

LOGIN_HEADER = "Tailscale-User-Login"
PANEL_HEADER = "X-RC-Panel"

#: The request headers that cross to the dashboard, and the only ones. A cookie, an ``Authorization`` or the
#: caller's ``Host`` never does: the dashboard must judge the caller by the caller's own identity headers, and
#: nothing the door forwards may carry a credential it was not given for this one press.
FORWARD_REQUEST_HEADERS = (PANEL_HEADER, LOGIN_HEADER, "Content-Type")

#: The response headers kept from the dashboard. Its own CSP and cache headers are the old shell's; the door
#: writes its own over every answer in ``app.py``.
FORWARD_RESPONSE_HEADERS = ("Content-Type",)

#: A captured segment: one path segment of the characters a dashboard id, ticker, dataset or job id uses. No
#: slash, no percent sign (so an encoded slash cannot smuggle a second segment), no dot pair.
_SEGMENT = re.compile(r"[A-Za-z0-9_:+-]+(?:\.[A-Za-z0-9_:+-]+)*\Z")

#: The loopback hosts the dashboard may be on. The door and the dashboard share the box and the host network.
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

#: What the browser says when a request came from a page of another site. ``same-site`` is in because another port
#: on the same host is ``same-site`` and is another application (#231, the dashboard's own ``_from_another_site``).
_ANOTHER_SITE = frozenset({"cross-site", "same-site"})

#: The body the proxy will carry upstream. Settings' presses are small JSON objects or empty; a larger body is a
#: sign of a caller the table was not written for, so it is refused rather than streamed.
MAX_BODY_BYTES = 64 * 1024


class UnsafeUpstream(RuntimeError):
    """``RC_DOOR_UPSTREAM`` names something that is not the dashboard on loopback."""


class UpstreamUnreachable(RuntimeError):
    """The dashboard did not answer. Its own 4xx and 5xx are answers and are passed through, not raised."""


@dataclass(frozen=True)
class Decision:
    """What the door does with this request, and why — the whole of the authorisation, as data.

    ``upstream_path`` is set only when ``allowed``: a refusal must not hand the caller a path it could not reach,
    and a guarded route must name none at all.
    """

    allowed: bool
    status: int
    klass: RouteClass | None
    reason: str
    upstream_path: str = ""


def classify(path: str) -> Route | None:
    """The route this path is, or ``None`` when the table does not name it.

    Matching is by segment against each pattern, and a captured segment must be one plain segment
    (:data:`_SEGMENT`). So ``/api/job/../../api/build/timer`` matches nothing, and neither does a path whose
    segment holds an encoded slash — the caller's string is never the forwarded string.
    """
    if not path.startswith("/") or path.startswith("//"):
        return None
    parts = path.split("/")[1:]
    for route in ROUTES:
        if _match(route.pattern, parts) is not None:
            return route
    return None


def _match(pattern: str, parts: list[str]) -> list[str] | None:
    """The captured segments of ``parts`` against ``pattern``, or ``None``."""
    expected = pattern.split("/")[1:]
    if len(expected) != len(parts):
        return None
    captured = []
    for want, got in zip(expected, parts):
        if want.startswith("{") and want.endswith("}"):
            if not _SEGMENT.match(got):
                return None
            captured.append(got)
        elif want != got:
            return None
    return captured


def _upstream_path(route: Route, path: str) -> str:
    """The path the door will press, assembled from the pattern and the segments it captured."""
    captured = _match(route.pattern, path.split("/")[1:])
    if captured is None:                                    # pragma: no cover - classify() matched already
        raise ValueError(path)
    out, taken = [], iter(captured)
    for want in route.pattern.split("/")[1:]:
        out.append(next(taken) if want.startswith("{") else want)
    return "/" + "/".join(out)


def decide(method: str, path: str, headers) -> Decision:
    """Whether this request crosses to the dashboard, and under which class.

    The order matters and is the order a reader would ask the questions in: is this route one we proxy at all; is
    it one we never press; is the method one it answers; and then, for a write only, is the caller who they must
    be. Nothing here reads a body or a query string: a rule that depended on either would be a rule the dashboard
    should be making.
    """
    got = _lower(headers)
    route = classify(path)
    if route is None:
        return Decision(False, 404, None, "not proxied: this path is not in the door's route table")
    # MUTATION (#1317, to be reverted): the Guarded class stops being refused and falls through to the write
    # checks, so a guarded press with a login would be forwarded. This commit exists to be read red in CI.
    if method.upper() not in route.methods:
        return Decision(False, 405, route.klass,
                        f"{method.upper()} is not how {route.klass.value} routes are pressed")
    if route.klass is RouteClass.READ:
        return Decision(True, 200, RouteClass.READ, "read", _upstream_path(route, path))

    # A write, and from here on the caller has to prove who they are. The same three questions the dashboard's own
    # `_local_only` asks, asked here too, because the dashboard will see the door's request and not the caller's.
    if (got.get("sec-fetch-site") or "").lower() in _ANOTHER_SITE:
        return Decision(False, 403, RouteClass.WRITE, "cross-site: the browser says this came from another page")
    origin = (got.get("origin") or "").strip()
    if origin == "null":
        return Decision(False, 403, RouteClass.WRITE, "cross-site: a null Origin")
    if origin and not _allowed_origin(origin):
        return Decision(False, 403, RouteClass.WRITE, "cross-site: the Origin is not one of the door's hosts")
    if not (got.get(LOGIN_HEADER.lower()) or "").strip():
        return Decision(False, 403, RouteClass.WRITE, f"login required: no {LOGIN_HEADER}")
    if not (got.get(PANEL_HEADER.lower()) or "").strip():
        return Decision(False, 403, RouteClass.WRITE, f"panel header required: no {PANEL_HEADER}")
    return Decision(True, 200, RouteClass.WRITE, "write", _upstream_path(route, path))


def _lower(headers) -> dict[str, str]:
    """The headers by lower-case name. HTTP header names are case-insensitive (RFC 9110); callers are not."""
    items = headers.items() if hasattr(headers, "items") else headers
    return {str(name).lower(): value for name, value in items}


def _allowed_origin(origin: str) -> bool:
    """True when the ``Origin``'s host is one the door answers for — the Host allowlist, read again here."""
    host = urllib.parse.urlsplit(origin).hostname or ""
    return host.lower() in {h.lower() for h in config.allowed_hosts()} or host.lower() in _LOOPBACK


def login_of(headers) -> str:
    """The caller's tailnet login, or ``""``. An identity, not a credential: it is logged, never forwarded on."""
    return (_lower(headers).get(LOGIN_HEADER.lower()) or "").strip()


def forwarded_headers(headers) -> dict[str, str]:
    """Exactly :data:`FORWARD_REQUEST_HEADERS`, with the caller's own values and no value the door invented."""
    got = _lower(headers)
    out = {}
    for name in FORWARD_REQUEST_HEADERS:
        value = (got.get(name.lower()) or "").strip()
        if value:
            out[name] = value
    return out


def upstream_base() -> str:
    """``RC_DOOR_UPSTREAM``, checked: ``http`` on a loopback host with no userinfo, else :class:`UnsafeUpstream`.

    Read per request rather than at import, so a door that is given a bad value fails the press that needs it and
    keeps answering its read routes.
    """
    raw = config.upstream()
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme != "http":
        raise UnsafeUpstream(f"the upstream must be http on loopback, not {parts.scheme or 'a bare host'!r}")
    if "@" in parts.netloc:
        raise UnsafeUpstream("the upstream must carry no userinfo")
    host = (parts.hostname or "").lower()
    if host not in _LOOPBACK:
        raise UnsafeUpstream(f"the dashboard is on this box; {host or raw!r} is not loopback")
    if parts.path.rstrip("/") or parts.query or parts.fragment:
        raise UnsafeUpstream("the upstream is a host and a port, with no path")
    return raw.rstrip("/")


def forward(method: str, upstream_path: str, query: str, headers: dict[str, str],
            body: bytes) -> tuple[int, dict[str, str], bytes]:
    """Press the dashboard and hand back ``(status, headers, body)``.

    The dashboard's own 4xx and 5xx are answers and come back as they are: a press refused by *it* must not look
    to the caller like a press refused by the door. Only a dashboard that does not answer at all raises.
    """
    url = f"{upstream_base()}{upstream_path}" + (f"?{query}" if query else "")
    request = urllib.request.Request(url, data=body or None, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=config.UPSTREAM_TIMEOUT_S) as answer:
            return answer.status, _kept(answer.headers), answer.read()
    except urllib.error.HTTPError as answer:                # a 403 or a 404 from the dashboard is its answer
        return answer.code, _kept(answer.headers), answer.read()
    except (urllib.error.URLError, OSError) as exc:
        raise UpstreamUnreachable(f"{type(exc).__name__}: {exc}") from exc


def _kept(headers) -> dict[str, str]:
    got = _lower(headers)
    return {name: got[name.lower()] for name in FORWARD_RESPONSE_HEADERS if name.lower() in got}
