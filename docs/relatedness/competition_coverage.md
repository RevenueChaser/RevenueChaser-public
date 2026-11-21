# Which companies have no Competition passage, 20 Nov 2026

The test of [`results.md`](results.md) is built from the Competition passages of 10-K Item 1. This is the
measurement of who has none, because those companies can never be a namer and their own rivals are never
checked (`/mnt/project-files/relatedness_no_competition_caps.json`).

| | companies (by CIK) |
|---|---|
| universe companies | 5,294 |
| with a Competition passage | 3,758 |
| **without one** | **1,536** |

## The gap is flat across size

The share missing a passage, by market-cap rank band (cap = the newest issuer market cap within 14 days of the
store's newest session, the board's own rule; one row per CIK, the largest class's cap):

| top | missing | share |
|---|---|---|
| 100 | 37 | 37% |
| 500 | 170 | 34% |
| 1,000 | 317 | 31.7% |
| 2,000 | 609 | 30.4% |
| 3,000 | 904 | 30.1% |

Median market cap of the missing companies $820.6M against $709.2M for the whole universe, and 137 of the
missing have no cap value at all (417 in the universe). So this is not a small-company hole: a third of the
largest hundred has no Competition passage either.

The ten largest missing, with their rank: SPCX (11), WMT (12), XOM (18), CVX (23), PG (24), GE (30), HD (31),
UNH (32), INTC (34), MS (35). This is the same fact [`results.md`](results.md) states from the other side — the
largest companies name nobody — counted here.
