"""v2 — the second interface's own tree (epic #1238, run plan ``plans/2026-11-21_0230_revenuechaser_v2-run-plan.md``).

Step 3 fills only ``schemas/`` (one JSON Schema per board that writes a payload) and ``validate.py`` (the small
subset of JSON Schema those files use). The door (``v2/door/``) and the web frame (``v2/web/``) arrive in steps 6
and 8. Nothing here is imported by the present dashboard: the envelope itself is written by
``core/v2_envelope.py``, next to the K10 payload, and the old boards keep reading the payload file.
"""
