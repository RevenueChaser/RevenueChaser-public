"""The v2 door: the read-only ``/api/v1`` over the v2 envelopes, and the static v2 web files.

Run plan row 6 (claude-coordinator ``plans/2026-11-21_0230_revenuechaser_v2-run-plan.md``, #1264, epic #1238).
The stack is ``v2/README.md``; the homesrv side (port 8100, ``life-rc-v2.slice``, the Grafana frame origin and the
``tailscale serve`` line) is home-server ``docs/rc-v2-door.md``.

The split in this package is deliberate, because the unit tier must be able to test the door's rules without a
server and without FastAPI's test client doing the thinking:

- ``boards.py`` — reads the envelope files. No HTTP, no framework: paths, bytes and metadata.
- ``health.py`` — the probes, each with its own time budget. Takes the probe callables, so a test can make one slow.
- ``config.py`` — every environment variable the door reads, read on call and never cached at import.
- ``app.py`` — the FastAPI wiring: the routes, the method guard, the Host allowlist, the headers, the static mount.

Read only, in this step by construction: ``app.py`` refuses every method but ``GET``, ``HEAD`` and ``OPTIONS``, so
there is no route through the door to a write until the proxy of step 7 exists.
"""
