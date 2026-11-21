# The v2 door's image: the web build in one stage, the Python door in another, nothing of either toolchain in the
# layer that runs. Built on the box from the merged SHA (`v2/README.md` decision 6: homesrv installs no Node, no
# npm and no Playwright browser — the Node toolchain exists only inside this build).
#
# Build context is the repository root, so the Dockerfile is given with -f:
#   docker compose build door            (compose passes RC_BUILD_SHA; see docker-compose.yml)

# ── the v2 web files ────────────────────────────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS web
WORKDIR /build
# The lockfile first, so a change to the app's source does not reinstall the dependency tree.
COPY v2/web/package.json v2/web/package-lock.json ./
# `npm ci` is the only install command (decision 6), and `--ignore-scripts` because nothing in the allowlist needs
# a postinstall and a build should not run one.
RUN npm ci --ignore-scripts
COPY v2/web/ ./
RUN npm run build

# ── the door ────────────────────────────────────────────────────────────────────────────────────────────────────
FROM python:3.14-alpine AS door
# The merged SHA this image was built from; `/api/v1/version` answers it, which is how a deploy proves which
# commit is serving.
ARG RC_BUILD_SHA=""
ENV RC_BUILD_SHA=${RC_BUILD_SHA} \
    PYTHONPATH=/srv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Only the door's own dependencies, never the repository's requirements.txt: the reasons are in
# v2/door/requirements.txt.
COPY v2/door/requirements.txt /tmp/door-requirements.txt
RUN pip install --no-cache-dir -r /tmp/door-requirements.txt && rm /tmp/door-requirements.txt

# `from RevenueChaser.core import ...` needs the checkout to BE the package, so the tree lands at
# /srv/RevenueChaser with /srv on the path. Only what the door imports is copied: there is no board code, no
# rcdata build, no dashboard and no test harness in this image.
WORKDIR /srv/RevenueChaser
COPY __init__.py ./
COPY core/__init__.py core/config.py core/v2_envelope.py core/
COPY v2/__init__.py v2/
COPY v2/door/ v2/door/
COPY --from=web /build/dist/ v2/web/dist/

# Not root. The door only ever reads, and the artifacts and store mounts are read-only in compose, so the
# container has nothing to write to at all.
RUN addgroup -S door && adduser -S -G door door
USER door

# `127.0.0.1`, not `0.0.0.0`: the container runs on the HOST network (docker-compose.yml), so `0.0.0.0` would open
# 8100 to the home network and the Server tab's ports check would be right to call it an unknown port. Loopback
# only, reached from outside through `tailscale serve --https=8100`.
#
# One worker: the door reads files and the whole tailnet is one person. More workers would multiply the memory
# `life-rc-v2.slice` caps for no gain, and `--proxy-headers` is off because `tailscale serve` keeps the real Host
# and the door's own Host allowlist is what checks it.
CMD ["uvicorn", "RevenueChaser.v2.door.app:app", "--host", "127.0.0.1", "--port", "8100", "--workers", "1"]
