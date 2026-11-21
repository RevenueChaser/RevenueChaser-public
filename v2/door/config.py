"""Every environment variable the door reads, each behind a function so a test can set it and a deploy can change it.

Nothing here is a module-level constant built from the environment: the dashboard's own ``core/config.py`` must be
read before the first RevenueChaser import for its roots to redirect, and repeating that trap in a second place
would make the door untestable. The artifacts root itself is **not** re-spelled here — it is
``core.config.OUTPUT_DIR``, the one place ``RC_CACHE_DIR`` is read (``core/tests/test_store_layout.py``).
"""
from __future__ import annotations

import os
from pathlib import Path

# The dashboard the proxy presses (run plan row 7, #1317). It holds the DuckDB writer and the job queue, and v2
# adds no second writer, so every v2 press is one of its routes. Loopback by default and loopback only:
# `proxy.upstream_base()` refuses anything else, because a door that would forward to any host an environment
# variable named is a relay for whatever can reach the tailnet.
DEFAULT_UPSTREAM = "http://127.0.0.1:8000"

# How long a proxied press may take. The dashboard's own presses answer at once (a Fetch returns a job id and the
# job runs behind it), so a press that is still open after this is a wedged dashboard and not a slow one; the
# caller is told 504 rather than being left holding the connection.
UPSTREAM_TIMEOUT_S = 15.0

# The door's own version, bumped by hand when a route's shape changes. Not the envelope's ``schema_version`` and
# not the store's ``_SCHEMA_VERSION``: this number says what ``/api/v1`` answers, nothing about data on disk.
DOOR_VERSION = "1"

API_PREFIX = "/api/v1"

# Each health probe gets this many seconds and no more (run plan row 6: "2 s probes"). A probe that overruns is
# reported as a timeout, so one unreachable dependency cannot make the health route hang.
PROBE_BUDGET_S = 2.0

# The hosts the door answers for. The tailnet name is how avo reaches it through `tailscale serve --https=8100`,
# which keeps the tailnet Host (home-server `docs/rc-v2-door.md`); the loopback names are the box's own checks.
DEFAULT_HOSTS = ("127.0.0.1", "localhost", "homesrv.rhinoceros-dominant.ts.net")

# Grafana on the box, the one external origin the door's CSP names: the v2 Settings screen frames the RC Data
# Health and RC Fetch boards from it (step 9). Everything else is refused by the CSP, and no CDN is ever named
# (`v2/README.md` decision 2).
DEFAULT_GRAFANA_ORIGIN = "https://homesrv.rhinoceros-dominant.ts.net:3000"


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def allowed_hosts() -> tuple[str, ...]:
    """The Host allowlist (``RC_DOOR_HOSTS``, comma separated), else :data:`DEFAULT_HOSTS`."""
    return _csv("RC_DOOR_HOSTS", DEFAULT_HOSTS)


def grafana_origin() -> str:
    """The one origin the CSP lets the door's pages frame (``RC_DOOR_GRAFANA_ORIGIN``); empty disables framing."""
    value = os.getenv("RC_DOOR_GRAFANA_ORIGIN")
    return DEFAULT_GRAFANA_ORIGIN if value is None else value.strip()


def upstream() -> str:
    """The dashboard's base URL (``RC_DOOR_UPSTREAM``), else :data:`DEFAULT_UPSTREAM`.

    Checked rather than trusted: ``proxy.upstream_base()`` is what reads this, and it refuses a scheme that is not
    ``http``, a host that is not loopback, userinfo, and a path.
    """
    value = (os.getenv("RC_DOOR_UPSTREAM") or "").strip()
    return value or DEFAULT_UPSTREAM


def write_log_path() -> Path | None:
    """Where the write log is appended on disk (``RC_DOOR_WRITE_LOG``), or ``None`` for nowhere.

    ``None`` is the default and is correct in the container: the image is ``read_only: true`` with one ``:ro``
    mount, so the line goes to the process log and journald keeps it (``v2/door/writelog.py``). A box that wants a
    file gives the variable a path on a writable mount; the write side must never need the artifacts root to
    become writable (#1317).
    """
    value = (os.getenv("RC_DOOR_WRITE_LOG") or "").strip()
    return Path(value) if value else None


def build_sha() -> str:
    """The 40-character SHA the image was built from (``RC_BUILD_SHA``), else ``""``.

    The Dockerfile takes it as a build argument, so ``/api/v1/version`` answers which merged commit is serving —
    the question a deploy's before/after check asks first.
    """
    return (os.getenv("RC_BUILD_SHA") or "").strip()


def redis_url() -> str:
    """``RC_REDIS_URL`` when the ops state is on Redis (``rcdata/ops.py``), else ``""``.

    The read side needs no Redis: it reads envelope files. The URL is here so the health route can say whether the
    compose service the write side of step 7 will need is reachable, and so an unset value is an honest "not
    configured" rather than a failed probe.
    """
    return (os.getenv("RC_REDIS_URL") or "").strip()
