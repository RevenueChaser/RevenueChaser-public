"""Phone notifications through the self-hosted ntfy on homesrv (avo, 17 Nov 2026: "bildirim kesinlikle").

A Fetch job the dashboard ran, and a Build the builder ran, post one line when they end: a pressed Fetch or Build
when it ends either way, the hourly builder's own runs only when they fail. The Settings problem cards reach the
phone through Grafana's alert rules (home-server ``grafana/provisioning/alerting/rc.yaml``), not from here.

``RC_NTFY_URL`` (the topic URL, e.g. ``http://127.0.0.1:2586/homesrv-rc``) and ``NTFY_PUBLISH_TOKEN`` come from the
unit's environment (home-server ``units/<unit>.service.d/ntfy.conf``). Without the URL nothing is sent, so a test
run, a Windows box or a checkout without ntfy sends nothing. A notification never fails or holds up the work it
reports: any error is a log line, and the call gives up after ``TIMEOUT_S``.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_S = 3.0


def send(title: str, message: str, *, priority: int = 3, tags: str = "") -> bool:
    """Post one notification; True when ntfy took it. Never raises."""
    url = os.environ.get("RC_NTFY_URL", "").strip()
    if not url:
        return False
    # ntfy reads Title/Tags from headers; a header must be latin-1, so the title keeps to that and the text is the body
    headers = {"Title": title.encode("latin-1", "replace").decode("latin-1")[:200], "Priority": str(priority)}
    if tags:
        headers["Tags"] = tags
    token = os.environ.get("NTFY_PUBLISH_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        httpx.post(url, content=message[:3000].encode("utf-8"), headers=headers, timeout=TIMEOUT_S).raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 - a notification must never fail the job it reports
        logger.warning("ntfy post failed: %s", type(exc).__name__)
        return False


def job_end(job: dict) -> bool:
    """A dashboard job (``app/jobs.py``) that ended ``done`` or ``error``; a cancel was pressed by avo, so no post."""
    status = job.get("status")
    if status not in ("done", "error"):
        return False
    name = str(job.get("module") or "job")
    if status == "error":
        return send(f"RC Fetch failed: {name}", str(job.get("error") or "no error text"), priority=4, tags="x")
    return send(f"RC Fetch done: {name}", str(job.get("message") or "finished"), priority=2,
                tags="white_check_mark")


def build_end(dataset: str, status: str, note: str | None, *, requested: bool) -> bool:
    """A builder run (``rcdata/build/base.py``) that ended: ``status`` is ok, skipped, failed or killed.
    A requested run (a Build button) posts either way; the hourly pass posts only a failure."""
    failed = status not in ("ok", "skipped")
    if not (failed or requested):
        return False
    if failed:
        return send(f"RC Build {status}: {dataset}", note or "no error text", priority=4, tags="x")
    return send(f"RC Build {'done' if status == 'ok' else status}: {dataset}", note or "finished", priority=2,
                tags="white_check_mark")
