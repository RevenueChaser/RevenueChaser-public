"""``python -m RevenueChaser.rcdata.build.sec_reads --plan [--reread]``: how many companies each registered question
would ask now, as JSON. No call is made and nothing is written; run it before a paid run."""
from __future__ import annotations

import json
import sys

from .. import DATASETS  # noqa: F401  (importing the builder registers the questions)
from . import reads

if __name__ == "__main__":
    if "--plan" not in sys.argv[1:]:
        raise SystemExit(__doc__)
    print(json.dumps(reads.plan_counts(reread="--reread" in sys.argv[1:]), indent=1))
