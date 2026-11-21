"""Every environment variable the door reads, each behind a function so a test can set it and a deploy can change it.

Nothing here is a module-level constant built from the environment: the dashboard's own ``core/config.py`` must be
read before the first RevenueChaser import for its roots to redirect, and repeating that trap in a second place
would make the door untestable. The artifacts root itself is **not** re-spelled here — it is
``core.config.OUTPUT_DIR``, the one place ``RC_CACHE_DIR`` is read (``core/tests/test_store_layout.py``).
"""
from __future__ import annotations

import os

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
