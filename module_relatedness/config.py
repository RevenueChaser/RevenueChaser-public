"""Relatedness board configuration (200-ticker spike).

Business similarity from 10-K Item 1 / 20-F Item 4 text: LLM structured profile
per company, then a local cosine over the profile attributes. See
docs/plan_200ticker.md.
"""
from __future__ import annotations

import os

from revenuechaser.core import llm_prices, llm_writers
from revenuechaser.core.config import OUTPUT_DIR
from revenuechaser.rcdata import sec_sections
from revenuechaser.module_value_chain import config as vc_config

RELATEDNESS_LATEST = OUTPUT_DIR / "relatedness_latest.html"
RELATEDNESS_JSON = OUTPUT_DIR / "relatedness" / "relatedness_latest.json"

# The floor under which a filing text is not sent to the writer at all (#313). Value Chain's own
# MIN_ITEM_CHARS, so "this is a sliced Item 1, not a table-of-contents fragment" means the same thing on both
# boards. A model asked from a one-line description does not refuse; it writes the profile from the company
# name (measured on the live store 2026-10-30: 20 of 1,503 pilot names carry an empty Item 1 and 58 one under
# this floor, AAP's being 1 character).
MIN_INPUT_CHARS = vc_config.MIN_ITEM_CHARS


def default_writer() -> str:
    """The writer a board call that names none runs on: the registry's default, which has no fee (EVREN).

    avo, 20 Nov 2026: "Fetch ve build sirasinda deepseek api kullanilan islem kalmasin hepsi evren deepseek
    olmali". Every function of this board carried the paid ``deepseek`` as its own default until then, so a caller
    that forgot the argument spent money. It is read at call time and in one place, so the tests of the DeepSeek
    path pin it here instead of naming the writer at 81 call sites (``tests/conftest.py``).
    """
    from revenuechaser.core import llm_writers
    return llm_writers.DEFAULT

# v3 (#400, Relatedness v2 Step 1): one structured JSON profile from the whole Item 1 / Item 4 (no input cut), read
# in chunks above 60k characters, JSON mode and no thinking (``profile_v3``). Every v2 profile reads stale and is
# redone by the next run of the board's writer. v2 (#388 D5) named the company instead of the ticker.
# v3b (#400 10-K package, avo "basla" 10 Nov 2026): the B input -- the new Item 1 cut, without its non-business
# sections, with the filing's customer sentences and XBRL customers in the prompt. Every v3 profile reads stale.
# v3c (#717, avo "prompt degisikligini de yap" 11 Nov 2026): a customer or supplier also carries the listed
# ``parent`` the text names and whether the text presents it as ``public``. Bumped before R1 on purpose: it makes
# the 388 profiles of today stale (about $1), where the same change after R1 would restale ~4,750 (about $14).
# v3d (#841): the business text comes from the SEC form reader (``sec/forms``), and the prompt is given the
# filing's segment note and concentration note beside the text. Both blocks ride in the context, which is outside
# the input hash, so without a bump they would reach only freshly profiled companies.
PROMPT_VERSION = "v3d"

# The most of a business section a profile reads (#841), or None for no cap. ``ours-2`` stores the section uncut
# (p99 264,822 characters, max 488,947 on the 5,131 stored annual reports, 13 Nov 2026) and a profile is one call
# per 60,000 characters. The owner's decision, 13 Nov 2026 ("maliyet onemli degil"): no cap, so no company's
# section is cut; a full round is 8,366 first-attempt calls against 8,128 under the 200,000 cap ``ours-1`` stored
# with (240,000 would have been 8,139 calls and cut 72 companies). The value is inside the hashed text: setting
# one later restales every company over it.
# Not the ``MAX_INPUT_CHARS`` v2 cut every text at (removed by v3, #400).
MAX_BUSINESS_CHARS: int | None = None

# Where a profile run gets its profiles (avo, 16 Nov 2026): ``service`` mirrors the SEC reading service's answers to
# ``company.profile`` into ``relatedness_profiles`` and calls no model; ``own`` is the board's own writer, kept until
# the clean-up for the tests of it and for the writer comparison.
PROFILES_FROM = "service"

# The rule version the business sections must be cut with before a profile run reads them (``_forms_ready``,
# #841). None turns the check off.
FORMS_RULES_VERSION = sec_sections.forms_rows_version()

# $ hard-stop: cap the number of LLM calls per run (~1.5x the expected spend).
# The cap's cost per call, measured on DeepSeek Flash: the 10 Nov 2026 pilot wrote 400 names in 668 calls for about
# 1 USD. It replaces the 0.006 the cap carried before, which was "about 4x" of the v2 figure, guessed until the pilot
# could measure it (review of PR #557). A chunked filing is several calls, each counted.
# The number itself lives in ``core.llm_prices`` since #166, because the day ledger costs an answer with it too: two
# copies would let this run's ceiling and the day's recorded spend drift apart. A model with no measured figure
# there leaves this at the pilot's number rather than at zero, which would make the cap refuse every call.
EST_USD_PER_CALL = llm_prices.measured_usd_per_call(llm_writers.get("deepseek").models[0]) or 0.0018
# A full round is every company with usable text: about 4,750 names at 1.67 calls each, so ~7,900 calls, ~14 USD
# (#712). The cap sits above that so one run covers the round instead of stopping six times and looking finished.
USD_CAP = float(os.getenv("RC_RELATEDNESS_USD_CAP", "25.0"))
LLM_WORKERS = 8
# A free writer's run (EVREN) whose first N replies hold no usable profile stops (``unusable``) before it counts an
# attempt on any group; the endpoint or the model is then wrong, not the companies.
UNUSABLE_STOP = 5

# Fixed profile schema. Similarity is defined on these fields only.
PROFILE_FIELDS = (
    "products", "end_markets", "business_model",
    "customer_types", "value_chain_role", "keywords",
)
FIELD_WEIGHTS = {
    "products": 1.0,
    "end_markets": 1.0,
    "business_model": 0.8,
    "customer_types": 0.8,
    "value_chain_role": 0.6,
    "keywords": 0.4,
}
# Similarity v2 (#669, plan 2026-10-30 Step 2): score = 0.6 s_do + 0.25 s_chain + 0.15 s_struct, with
# s_chain = 0.6 type Jaccard + 0.4 shared-name bonus. Starting weights from the Fable review (section 4.3);
# the validation set (Step 4) tunes them and writes the chosen values here with the run id.
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_CACHE = OUTPUT_DIR / "fastembed"
W_DO, W_CHAIN, W_STRUCT = 0.6, 0.25, 0.15
W_CHAIN_TYPES, W_CHAIN_NAMES = 0.6, 0.4
TOP_PEERS = 25
# A peer is shown only with at least this many shared tags (#395, review RL-3). No score floor: measured 4 Nov 2026
# on 93 DeepSeek profiles, floor 0.10 -> hand P@10 0.459, 0.02 -> 0.726, none -> 0.728 / recall@25 0.799; a floor
# hides true peers because the idf lowers the cosine scale.
PEER_MIN_SCORE = 0.0
PEER_MIN_SHARED = 2

# Incremental scoring of a whole-board Refresh (#1132, the code half of #884). The rows a Refresh actually scores
# are the changed profiles plus every profile whose stored top list named one (``incremental.rows_to_rescore``).
# Above this share of the board the bookkeeping buys nothing and the full matrix is scored instead.
INCREMENTAL_MAX_SHARE = 0.2
# The size of the score grid a full run saves in the payload (``score_quantiles``), so an incremental run can rank a
# new peer's percentile without the whole upper triangle: 1,001 points = 0.1-percentile resolution. A saved payload
# without the grid (one written before #1132) sends a Refresh through the full matrix once.
SCORE_QUANTILES = 1001
