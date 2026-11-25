"""``python -m revenuechaser.rcdata.build.sec_reads --plan [--reread [question ...]]``: how many companies each
registered question would ask now, as JSON. ``--reread`` alone is the word for every question, ``--reread debt.note``
for that one only. No call is made and nothing is written; run it before a paid run."""
from __future__ import annotations

import json
import sys

from .. import DATASETS  # noqa: F401  (importing the builder registers the questions)
from . import reads

if __name__ == "__main__":
    if "--plan" not in sys.argv[1:]:
        raise SystemExit(__doc__)
    args = sys.argv[1:]
    named = tuple(a for a in args[args.index("--reread") + 1:] if not a.startswith("--")) if "--reread" in args else ()
    print(json.dumps(reads.plan_counts(reread=named or "--reread" in args), indent=1))
