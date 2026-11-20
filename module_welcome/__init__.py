"""Welcome board: the opening screen. Its rows live in its own ``boards/welcome.duckdb`` (DECISIONS S9, S16)."""

#: The needs this board reads (``rcdata.needs.boards``). #643 PR 5: the four market tiles; PR 5b and PR 6: the
#: earnings card (``earnings.next`` for the calendar row, ``identity.security`` for a name the row does not carry)
#: and the freshness card, which reads the builder's own run ledger in ops (``job_runs2``) and no served need.
READS = ("earnings.next", "identity.security", "macro.dgs10", "market.series", "market.spx_close", "market.vix")
