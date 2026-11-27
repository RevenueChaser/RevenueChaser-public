"""``prices/serving``: the served prices store, built from the sources' staging tables (no fetch, no network).

**Tables** (``prices.duckdb``, serving schema version 1), every one keyed on the security id (``prices.security_id``):

- ``price_bar_daily``: one bar per security and New York session, **nominal** (the prices as traded that day):
  Yahoo's (``yfinance/bars``) only on a session Compustat has no row of the security (F28), else the WRDS history (Alpaca's bars are the tester's, ``prices.tester``, and never served) -- ``wrds/prices``'s
  Compustat on every day it prices and lists, a day without ``trfd`` too, its return read with ``trfd`` = 1 and the
  day's dividend flagged; **CRSP serves no bar** (avo, 4 Nov 2026: the cross-check only) -- and the S&P 500 index
  level from the market store's Cboe file (``index:SPX``, the close only);
- ``corporate_action``: Alpaca's actions of the store's securities, resolved to the security that traded under the
  action's symbol nearest its date (else the spine's current ticker), and Compustat's splits and dividends of the
  securities with bars where Alpaca has no action of that kind that day, with ``applied`` (used by ``adj_factor``),
  ``not_applied_why``, the split ``ratio`` (new over old shares) and the cash ``amount`` per share; an action whose
  ex-date is after the newest session is kept, not applied, and raises no issue until it goes ex;
- ``adj_factor``: per security, the periods ``[valid_from, valid_to)`` between two ex-dates and the factors that
  turn a nominal bar of the period into today's basis: ``split_factor`` (the product of ``1 / ratio`` of every split
  and stock dividend after it) and ``tr_factor`` (that, times ``1 - amount / close before the ex-date`` of every cash
  dividend after it). A bar after the last ex-date, or of a security with no action, has both factors 1. The
  factors are applied on read (``rcdata.read.bars``); nothing stored is ever adjusted;
- ``shares_class``: shares per class and day: ``outstanding`` from the SEC covers (an unlisted class keyed
  ``class:<CIK>:<member>``, and so is an ADR issuer's count, which is of ordinary shares, not of the ADSs) and, for a
  single-class issuer, every past cover's count from its company facts (``sec/companyfacts``, the history the covers
  lack), ``float`` from Yahoo and from Unusual Whales;
- ``security_symbol``: the symbols each security traded under and when (from its bars; the spine's ticker for a Tier
  A name with none yet);
- ``market_cap_daily``: close times shares per security and session, the shares being the bar's own (a history
  source's), else a WRDS source's of that session, else the newest cover on or before the session, moved over the
  splits between the two; and the issuer's sum over its listed classes, each at its newest cap at most
  ``ISSUER_WITHIN_DAYS`` old (``issuer_market_cap``; an unlisted class has no price and is not in it). A count of 0
  is none, and an ADR has no cap (its counts are the issuer's ordinary shares; #711, until an ADS ratio is read):
  both keep their row with ``market_cap`` and ``shares`` NULL and ``shares_source`` ``zero_count`` or ``adr_no_ratio``;
- ``price_revision``: the values a later read replaced (Alpaca's re-read of the last sessions, the monthly WRDS
  refresh), with when and by which run;
- ``wrds_price_diff``: the WRDS difference report (``wrds_history.COMPARISONS``), one row per comparison and ``as_of``
  (a whole build keeps the live file's older reports, ``stage.carry_reports``): the closes
  of CRSP against Compustat and of each against Alpaca on the sessions both have, and each WRDS source's own day
  return against the store's (its closes, the store's factors) on consecutive sessions; a difference over 1 bp
  counts. Shown on the ``wrds/prices`` Settings card.

**Views** under the old ``prices.duckdb`` names (D4), with the old columns: ``price_bars_daily`` (split-adjusted OHLC,
``adj_close`` total-return adjusted, both to today, ``fetched_at`` the build time so the old reader applies no split
a second time), ``price_actions`` (splits and dividends, the amount in today's share basis) and
``index_levels_daily`` (``^GSPC``).

**What is stored** is today's universe and nothing else (``prices.universe``, avo's rule of 4 Nov 2026): the
``_universe`` table is built from the live spine before anything else, and Alpaca's, Compustat's and CRSP's rows are
each filtered through it. A SPAC, warrant, unit, preferred, closed-end fund or untyped name, a fund under
``universe.ETF_MIN_AUM`` or of unknown AUM, and every delisted name are therefore absent from every table here.

**Memory**: DuckDB holds a ``PRIMARY KEY``'s index in memory for the whole insert, and ``price_bar_daily`` and
``market_cap_daily`` are the two tables with a row per security **and** session. The key stays on (avo, 4 Nov
2026: with the store cut to today's universe the index fits); ``RC_PRICES_NO_PRIMARY_KEY=1`` writes those two
without it and checks their key with one query instead (``no_primary_key``, ``duplicate_keys``).

**Build issues** (``ISSUE_KINDS``) are computed here and written to ``ops.sqlite`` once the new file is live
(``after_swap``, ``ops.sync_issues``): an issue found again stays open, one no longer found is resolved.
"""
from __future__ import annotations

import logging
from datetime import date

import duckdb

from ... import ops
from .. import base, secd
from . import KIND, incremental, stage, universe, wrds_history, yahoo_bars
from .cover_shares import DEI_SOURCE as DEI

logger = logging.getLogger(__name__)

NAME = "prices/serving"
VIEWS = ("security_symbol_now", "price_bars_daily", "price_actions", "index_levels_daily")
TABLES = ("price_bar_daily", "corporate_action", "adj_factor", "shares_class", "security_symbol",
          "market_cap_daily", "price_revision", "wrds_price_diff")
ALPACA_BARS, ALPACA_ACTIONS = "alpaca/bars", "alpaca/corporate_actions"
COVER, YAHOO, TV = "sec/cover_shares", "yfinance/float", "tradingview/float"
# The oldest a company facts count may be on the session it gives a cap to: a year and a filing's lag.
DEI_MAX_AGE_DAYS = 400
INDEX_SOURCE = "market_series/cboe"
# A day whose split-adjusted close moved by this factor or more, either way, with no split that day.
GAP_FACTOR = 1.9
# ... measured from the security's previous served bar, at most this many days before it.
GAP_DAYS = 7
# The 1-bp rule: our total-return day return against the source's own adjusted one.
TOLERANCE = 1e-4
# Alpaca's adjusted closes come rounded to the cent, so its day return can be off by half a cent on each close
# (KO in the server's sample, 29 Oct 2026: 1.1-1.3 bp at ~$70 between two days no factor separates). The rule
# allows that much where it is more than 1 bp: the widest the return can move with the two closes half a cent apart
# in opposite directions, h * (close + previous) / (previous * (previous - h)), exact, since a row can sit on it
# (ADV, 29 Oct: 20.395 and 19.865 rounded apart; the first-order bound was 0.02 % short).
# shortcut: the cent rounding is read from the sample's KO rows, Alpaca does not document it; measure it on the server
# (count of rows left, and their sizes) and narrow or widen this once a full Tier A build runs.
HALF_CENT = 0.005
# The newest session of a **stock** bar: the ``index:SPX`` row is written a session ahead of the equity bars, so an
# unfiltered ``max(session_date)`` reported the store one day fresher than it is (plan v2 step 1, #1413).
NEWEST_STOCK_SQL = "SELECT max(session_date) FROM price_bar_daily WHERE security_id NOT LIKE 'index:%'"
FLOAT_OVER = 1.05
FLOAT_DISAGREE = 0.25
# A cover count behind a market cap and Yahoo's sharesOutstanding further apart than this, on the newest session up to
# Yahoo's answer whose cap is cover-sourced, is an issue (AEHL in the server's sample: a count from before its
# dilution, 400 times too small).
SHARES_DISAGREE = 0.25
# A CRSP split (``wrds_history.CRSP_SPLITS``, the cross-check) is the same split as another source's this many days
# from it, either way.
SPLIT_SAME_DAYS = 3
# ... and the same split as another source's of **the same ratio** this many days from it, either way. The two
# sources date one split apart when its ex-date moved after Compustat recorded the planned one: NVDA's 2-for-1 is
# Compustat's 12 Sep 2001 (the first planned date, the week the exchanges were closed) and CRSP's 17 Sep 2001 (the
# real ex-date), five days and the same ratio, so the near rule above let both in and the share basis stepped twice
# -- the oldest ``split_factor`` 1/960 where 1/480 is right, every adjusted close before 12 Sep 2001 half of it
# (#661, measured on the live file 21 Nov 2026). A week covers a slip of a trading week and no more. Measured over
# the 80 applied CRSP splits of that file (72 securities; the coordinator's scan of the same day, one read-only
# query): a Compustat split of the security sits within 3 days of none of them, within 7 days of 1 (NVDA), within
# 15 and 31 days of 3, within 90 days of 6 -- and NVDA is the **only** pair of the six whose two ratios agree. The
# ratio is the rule and the window is the belt: every wider bucket adds pairs this rule would not take anyway.
SPLIT_SAME_RATIO_DAYS = 7
# The two ratios are quotients of rounded factors (``dlycumfacpr``, ``ajexdi``), so the same split comes out a
# little apart in the two sources; this much apart, either way, is still one ratio. The measured set leaves this
# wide open: NVDA's pair agrees exactly (2.0 against 2.0), and the nearest of the five pairs that are two events
# sits 2.5 times apart (ATI, 2.02008 against 5.0) -- the set holds nothing between 1 % and 147 %.
SPLIT_RATIO_TOLERANCE = 0.01
# An applied split's ratio against the move of the served **raw** closes across its ex-date (#1333, draft P-E): a
# real split's raw close steps by its ratio, so the move and 1/ratio agree apart from the day's own return. This
# much apart, either way, is a ratio the served bars do not show -- the split is named, never dropped, because
# which of the two is wrong (the source's ratio, or the bars) is a decision over served money data and needs a
# whole prices build behind it. Measured on the live file 21 Nov 2026: 137 applied splits (Alpaca 9, Compustat 126,
# CRSP 2), two clusters -- a split recorded where the price did not move (HON 29 Jun 2026 ratio 0.5, NVRI, GMEX,
# GFAI) and a reverse split at the wrong ratio. SCCO's Alpaca stock dividend of 3 Nov 2026 is the same shape: a
# ratio of 2.0106 (``ACTION_RATIO``'s ``1 + rate`` over a raw rate of 1.0106, where the name's Compustat stock
# dividends are about 1.012) against a close that moved 179.36 -> 173.49, so every adjusted close before it is
# halved (#1333, draft P-D). A day's own return never reaches this factor for a name with a split, and a split
# that is right is within a few percent of it.
SPLIT_MOVE_FACTOR = 1.5
# How far before its gap or its Alpaca split a CRSP split can still decide an issue there: a build on the live copy
# finds the CRSP splits this many days before what it rebuilds again, and the gaps ``SPLIT_SAME_DAYS`` before it
# (a split from then on can take a CRSP split, and with it the gap's explanation; ``incremental``, review S6 of #564).
NEAR_SPLIT_DAYS = GAP_DAYS + max(SPLIT_SAME_DAYS, SPLIT_SAME_RATIO_DAYS)
# A dividend is applied with the close of the last bar before its ex-date, at most this many days before it.
CLOSE_BEFORE_DAYS = 7
# The issuer cap of a session counts each listed class at its newest cap at most this many days old (a thin class
# that did not trade that day still counts): the window ``rcdata.read.latest_market`` reads the newest cap in.
ISSUER_WITHIN_DAYS = 14
# How many bars a security the build goes on serving may come out short of the live file before the build is
# refused (``_refuse_shrink``, #1096, avo's word of 19 Nov 2026). A source that restates the last days of one name
# -- a late cover, a corrected session -- costs a bar or two there; a name whose history is genuinely cut is far
# worse than that. Within the tolerance the shortfall is named in the build note instead of refused.
PER_ID_SHRINK_BARS = 5
APPLIED = ("split", "stock_dividend", "cash_dividend")
NOT_APPLIED = ("spin_off", "unit_split", "rights_distribution")
# The actions the factors did not apply (an action announced for a later day aside), and whether each is only
# counted: a cash dividend that went ex on or before its security's first served bar (on that bar too: the factors
# move the bars before the ex-date, and there are none). A security with no served bar at all, and any other kind of
# action, is named (review D6 and D7 of #420).
UNAPPLIED_SQL = """
    SELECT c.source_id, c.action, c.security_id, c.not_applied_why,
           coalesce(c.action = 'cash_dividend' AND c.ex_date <= f.first_day, false) AS before_history
    FROM corporate_action c
    LEFT JOIN (SELECT security_id, min(session_date) AS first_day FROM price_bar_daily GROUP BY 1) f USING (security_id)
    WHERE c.applied = false AND NOT starts_with(c.not_applied_why, 'not yet ex')"""

ISSUE_KINDS = {
    "source_never_run": "a source this build needs has no data yet (key: the dataset)",
    "crsp_ticker_link": ("a spine security, no ETF, whose CRSP PERMNO linked by ticker alone, no CUSIP behind it "
                         "(key: the security id; the detail names the PERMNO and the ticker, review S4 of #353 and "
                         "SHOULD 5 of its delta review)"),
    "duplicate_key": ("a table written without a PRIMARY KEY holds a key value twice (key: the table and the key "
                      "value; ``no_primary_key``, ``duplicate_keys``)"),
    "tier_a_no_bar": ("a Tier A name of the stored universe with no bar on the newest served session (key: the "
                      "security id)"),
    "tier_a_no_shares": ("a Tier A name of the stored universe with no shares, so no market cap, on the newest "
                         "session (key: the security id); an ADR is ``adr_no_ratio`` instead"),
    "adr_no_ratio": ("a Tier A ADR of the stored universe with a bar on the newest session and no market cap, because "
                     "its share counts are the issuer's ordinary shares and no ADS ratio is read yet (key: the "
                     "security id; #711, prices plan 16 Nov 2026 decision B)"),
    "universe_etf_no_bar": ("an ETF of the stored universe (a ticker of the spine's etf table, or a fund of the "
                            "my_universe list) with no bar on the newest served session (key: the ticker; review M3 "
                            "of #382, D5 of #420)"),
    "etf_identity_disagrees": ("a universe fund whose spine ``etf`` row gives a gvkey:iid, while prices claims "
                               "another for it: its spine row's, its ticker series (``_etf_tic_series``) or its CUSIP "
                               "alias (``_gvkey_alias``); found only, nothing served changes (key: the ticker; #1585, "
                               "avo 27 Nov 2026 option A)"),
    "etf_identity_unclaimed": ("a universe fund whose spine ``etf`` row gives a gvkey:iid that no prices path claims "
                               "for it (key: the ticker; #1585)"),
    "universe_etf_ticker_shared": ("more than one recent Compustat series carries the ticker of a universe fund the "
                                   "spine cannot route; one is stored, the detail names them all (key: the ticker; "
                                   "review D1 of #420)"),
    "price_gap_no_action": ("the split-adjusted close moved by GAP_FACTOR or more with no split that day "
                            "(key: security:session)"),
    "price_gap_warrant": ("``price_gap_no_action`` of a security the spine types a warrant or a unit, kept apart so the "
                          "gaps of shares stand alone; nothing is dropped (key: security:session; prices plan 16 Nov "
                          "2026 decision C)"),
    "split_only_crsp": ("CRSP's dlycumfacpr records a split no Compustat or Alpaca split is within SPLIT_SAME_DAYS of, "
                        "between two served bars at most GAP_DAYS apart, **and the served close does not jump across "
                        "it**: a CRSP factor step the served bars do not show, named as the cross-check of "
                        "Compustat's splits and never applied. One the served close jumps GAP_FACTOR or more across "
                        "is a split Compustat lacks and is applied instead of named, as source wrds/crsp "
                        "(key: security:session; review M6 of #382, avo 21 Nov 2026 on #661)"),
    "split_applied_crsp": ("a ``split_only_crsp`` candidate the served close jumps GAP_FACTOR or more across, so "
                           "Compustat lacks the split and the served history was wrong there: it is **applied** "
                           "from CRSP as source wrds/crsp, the one CRSP row that is served, and stays named so the "
                           "exception is visible (key: security:session; #661, avo 21 Nov 2026)"),
    "split_crsp_restated": ("a ``split_applied_crsp`` candidate Compustat or Alpaca already records at the same ratio "
                            "(within SPLIT_RATIO_TOLERANCE) up to SPLIT_SAME_RATIO_DAYS days away: one split the two "
                            "sources date apart, not two, so it is applied **once**. Which of the two days carries "
                            "it is the served bars' answer (avo, 22 Nov 2026: the real ex-date wins): the basis "
                            "changed between the two bars the jump is measured across, so where the other source's "
                            "day is outside that gap it is not the real ex-date and CRSP's row is the applied one, "
                            "the other source's left in the table unapplied (``action_not_applied``, reason "
                            "'restated by CRSP'). Where both days fall in the same gap the bars cannot tell them "
                            "apart and no bar's basis moves either way, so the other source's row stays the applied "
                            "one. The detail names the other row's day and ratio and which way it went "
                            "(key: security:session; #661, NVDA's 2-for-1 of Sep 2001)"),
    "split_ratio_unexplained": ("an **applied** split, reverse split or stock dividend whose ratio the served raw "
                               "closes across its ex-date do not show: the move and 1/ratio are SPLIT_MOVE_FACTOR "
                               "or more apart, between two served bars at most GAP_DAYS apart with no second split "
                               "between them. Named only -- nothing is dropped and no factor changes -- because "
                               "which side is wrong is avo's call and costs a whole prices build (key: "
                               "security:session; the detail names the ratio, the move and the two bars; #1333 "
                               "drafts P-D and P-E)"),
    "adjustment_differs": ("a served bar's total-return day return is more than 1 bp from Alpaca's adjusted one, or "
                           "more than the rounding of its cent-rounded closes where that is larger (the tester, "
                           "key: security:session)"),
    "alpaca_close_differs": ("a history bar's close (Compustat's, or CRSP's) is more than 1 bp and half a cent from "
                             "Alpaca's close of the session (the tester, key: security:session:source)"),
    "dividend_not_applied": "a cash dividend the factors could not use (key: the action id)",
    "action_not_applied": "a spin-off, unit split or rights distribution the factors do not apply (key: the action id)",
    "cover_class_unmapped": "a cover class whose trading symbol is no spine ticker of its CIK (key: CIK:symbol)",
    "cover_adr_ordinary": ("an ADR's issuer's cover count: ordinary shares, not ADSs, so kept under class: and no "
                           "market cap from it (key: the ADR's security id)"),
    "float_above_outstanding": "the newest float is above FLOAT_OVER times the shares outstanding (key: the security id)",
    "float_sources_disagree": ("TradingView's and Yahoo's newest float differ by more than FLOAT_DISAGREE (key: the "
                               "security id)"),
    "shares_disagree_yahoo": ("the cover shares behind a market cap and Yahoo's newest sharesOutstanding differ by more "
                              "than SHARES_DISAGREE, on the newest cover-sourced cap up to Yahoo's answer (key: the "
                              "security id)"),
}

PRICE_BAR = [("security_id", "TEXT"), ("session_date", "DATE"), ("symbol", "TEXT"), ("cik", "TEXT"),
             ("open", "DOUBLE"), ("high", "DOUBLE"), ("low", "DOUBLE"), ("close", "DOUBLE"), ("volume", "DOUBLE"),
             ("vwap", "DOUBLE"), ("trade_count", "BIGINT"), ("shares_outstanding", "DOUBLE"), ("source", "TEXT"),
             ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]
CORPORATE_ACTION = [("security_id", "TEXT"), ("ex_date", "DATE"), ("action", "TEXT"), ("action_type", "TEXT"),
                    ("ratio", "DOUBLE"), ("amount", "DOUBLE"), ("currency", "TEXT"), ("special", "BOOLEAN"),
                    ("applied", "BOOLEAN"), ("not_applied_why", "TEXT"), ("symbol", "TEXT"), ("new_symbol", "TEXT"),
                    ("record_date", "DATE"), ("payable_date", "DATE"), ("process_date", "DATE"), ("source", "TEXT"),
                    ("source_id", "TEXT"), ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]
ADJ_FACTOR = [("security_id", "TEXT"), ("valid_from", "DATE"), ("valid_to", "DATE"), ("split_factor", "DOUBLE"),
              ("tr_factor", "DOUBLE"), ("events", "INTEGER")]
SHARES_CLASS = [("security_id", "TEXT"), ("measure", "TEXT"), ("as_of", "DATE"), ("value", "DOUBLE"),
                ("symbol", "TEXT"), ("cik", "TEXT"), ("class_member", "TEXT"), ("source", "TEXT"),
                ("source_ref", "TEXT"), ("filed", "DATE"), ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"),
                ("run_id", "TEXT")]
SECURITY_SYMBOL = [("security_id", "TEXT"), ("symbol", "TEXT"), ("cik", "TEXT"), ("valid_from", "DATE"),
                   ("valid_to", "DATE"), ("source", "TEXT")]
MARKET_CAP = [("security_id", "TEXT"), ("session_date", "DATE"), ("cik", "TEXT"), ("close", "DOUBLE"),
              ("shares", "DOUBLE"), ("shares_source", "TEXT"), ("shares_as_of", "DATE"), ("market_cap", "DOUBLE"),
              ("issuer_market_cap", "DOUBLE")]
PRICE_REVISION = [("security_id", "TEXT"), ("session_date", "DATE"), ("symbol", "TEXT"), ("open", "DOUBLE"),
                  ("high", "DOUBLE"), ("low", "DOUBLE"), ("close", "DOUBLE"), ("volume", "DOUBLE"), ("source", "TEXT"),
                  ("fetched_at", "DOUBLE"), ("run_id", "TEXT"), ("revised_at", "DOUBLE"), ("revised_by", "TEXT")]
WRDS_PRICE_DIFF = [("comparison", "TEXT"), ("as_of", "DATE"), ("securities", "INTEGER"), ("sessions", "INTEGER"),
                   ("close_differs", "INTEGER"), ("max_close_diff", "DOUBLE"), ("return_differs", "INTEGER"),
                   ("max_return_diff", "DOUBLE"), ("first_session", "DATE"), ("last_session", "DATE")]
SCHEMAS = {"price_bar_daily": PRICE_BAR, "corporate_action": CORPORATE_ACTION, "adj_factor": ADJ_FACTOR,
           "shares_class": SHARES_CLASS, "security_symbol": SECURITY_SYMBOL, "market_cap_daily": MARKET_CAP,
           "price_revision": PRICE_REVISION, "wrds_price_diff": WRDS_PRICE_DIFF}
# The key of a table, checked after its insert (``duplicate_keys``).
KEYS = {"price_bar_daily": ("security_id", "session_date"), "market_cap_daily": ("security_id", "session_date")}
# The tables that may be written **without** a ``PRIMARY KEY``: the two with a row per security **and session**.
# DuckDB builds an ART index for a primary key and holds it in memory for the whole ``INSERT``, on top of the
# statement's own memory, and the scratch build of 3 Nov 2026 ran the 5 GB ``memory_limit`` out after 4 h 51 min
# writing ``price_bar_daily``. avo, 4 Nov 2026: **the key stays on** -- with the store cut to today's universe
# (``prices.universe``, about 7,400 names where the whole Compustat history was 18,947 ids) the index fits -- and
# the measured build decides. ``RC_PRICES_NO_PRIMARY_KEY=1`` writes these two without it and checks their key with
# one grouped query instead (``duplicate_keys``, a ``duplicate_key`` build issue), so a build that still does not
# fit needs no code change.
MAY_DROP_PRIMARY_KEY = ("price_bar_daily", "market_cap_daily")
NO_PRIMARY_KEY_ENV = "RC_PRICES_NO_PRIMARY_KEY"
# One ``_hist_all`` row per (security, session), the lowest priority (Compustat, 1, before CRSP) of those ``where`` keeps,
# then the lowest series (two Compustat series of one aliased fund: chunking changes ``rowid`` order, review F3 of
# #654), as a filter on ``rowid``. A hash aggregate, not a ``row_number()`` window: the window over every security and
# session of 2010-2025 (60.7M rows, 39.2M partitions) ran out of DuckDB's 5 GB, where this spills (#372).
HIST_FIRST = ("rowid IN (SELECT arg_min(rowid, row(priority, series)) FROM _hist_all {where} "
              "GROUP BY security_id, session_date)")
# The history rows a session may be served from: Compustat's. A CRSP row is staged for the difference report and
# the split cross-check and is never served (avo, 4 Nov 2026; ``wrds_history``'s CRSP section).
HIST_SERVED = f"source <> '{wrds_history.CRSP}'"

# The security id of a spine row, the SQL twin of ``prices.security_id``.
SPINE_ID = ("CASE WHEN nullif(gvkey, '') IS NOT NULL AND nullif(iid, '') IS NOT NULL THEN gvkey || ':' || iid "
            "WHEN nullif(composite_figi, '') IS NOT NULL THEN 'figi:' || composite_figi "
            "WHEN nullif(cik, '') IS NOT NULL THEN 'cik:' || cik || ':' || upper(ticker) "
            "ELSE 'sym:' || upper(ticker) END")
# The factor period a day falls in: ``<a>.valid_from <= <day> < <a>.valid_to``, open at both ends.
IN_PERIOD = ("{a}.security_id = {sid} AND {day} >= coalesce({a}.valid_from, DATE '0001-01-01') "
             "AND ({a}.valid_to IS NULL OR {day} < {a}.valid_to)")


def period(a: str, sid: str, day: str) -> str:
    return IN_PERIOD.format(a=a, sid=sid, day=day)


# The same lookup as an ASOF join: the factor period of a day is the one whose ``valid_to`` is the nearest after it.
# That is the row ``IN_PERIOD`` picks only while ``adj_factor`` keeps three preconditions, all made by ``ADJ_SQL`` (one
# row per ex-date of the applied events, ``FROM _act_final WHERE applied ... GROUP BY ALL``): one row per
# (security_id, valid_to); a security's periods contiguous (each ``valid_from`` is the previous row's ``valid_to``, the
# first NULL); ``valid_to`` never NULL. A NULL day matches no period in ``IN_PERIOD`` (factor 1), but DuckDB's ASOF_JOIN
# operator (used above ``asof_loop_join_threshold`` left rows) matches it to the oldest period, so the day is read as
# ``DATE '9999-12-31'``, after every ``valid_to``: no row, as before. The range join is evaluated as a blockwise
# nested loop: on the WRDS history (5.6M bars, 64k factor rows, 30 Oct 2026) one pass took 347 s, the ASOF join 1.7 s,
# and the serving build ran three of them over every bar (``market_cap_daily`` twice, the WRDS report). A day that is
# no column (``DATE '9999-12-31'``) has no ASOF inequality, so that lookup keeps ``period``.
AS_OF_PERIOD = ("ASOF LEFT JOIN adj_factor {a} ON {a}.security_id = {sid} "
                "AND coalesce({day}, DATE '9999-12-31') < {a}.valid_to")


def factor_join(a: str, sid: str, day: str) -> str:
    """``ASOF LEFT JOIN adj_factor <a>`` on the factor period of ``day`` (a column), the rows ``period`` would match."""
    return AS_OF_PERIOD.format(a=a, sid=sid, day=day)


def no_primary_key() -> tuple[str, ...]:
    """The tables this build writes without a ``PRIMARY KEY``: none unless ``RC_PRICES_NO_PRIMARY_KEY`` is set
    (``MAY_DROP_PRIMARY_KEY``, avo's decision of 4 Nov 2026)."""
    import os
    return MAY_DROP_PRIMARY_KEY if os.getenv(NO_PRIMARY_KEY_ENV, "").strip() not in ("", "0", "false") else ()


def duplicate_keys(con: duckdb.DuckDBPyConnection, table: str, limit: int = 20) -> list[tuple[str, int]]:
    """The key values ``table`` holds more than once, ``[(key, rows), ...]``, at most ``limit`` of them: what a
    dropped ``PRIMARY KEY`` would have refused (``no_primary_key``). Empty when the key is unique."""
    key = KEYS[table]
    cols = ", ".join(f'"{c}"' for c in key)
    text = " || ':' || ".join(f'CAST("{c}" AS TEXT)' for c in key)
    return [(k, n) for k, n in con.execute(
        f"SELECT {text} AS key, count(*) AS n FROM {table} GROUP BY {cols} HAVING count(*) > 1 "
        f"ORDER BY n DESC, key LIMIT {limit}").fetchall()]


def _create(con: duckdb.DuckDBPyConnection, table: str, select: str, live: bool = False, rows: str | None = None) -> int:
    """Fill ``table`` from ``select``. A whole build creates it. On the live copy (``live``) the table is there with
    the live rows: ``rows`` (a condition, ``incremental.where``) names the rows that are rebuilt, which are deleted
    and loaded again from ``select``; without it every row is. The delete commits before the insert, so a key
    deleted and loaded again never meets itself in the ``PRIMARY KEY``'s index."""
    schema = SCHEMAS[table]
    names = ", ".join(f'"{c}"' for c, _ in schema)
    if live:
        con.execute(f"DELETE FROM {table}" + (f" WHERE {rows}" if rows else ""))
        con.execute(f"INSERT INTO {table} ({names}) SELECT {names} FROM ({select})"
                    + (f" WHERE {rows}" if rows else ""))
        return stage.count(con, table)
    cols = ", ".join(f'"{c}" {t}' for c, t in schema)
    key = None if table in no_primary_key() else KEYS.get(table)
    con.execute(f"CREATE TABLE {table} ({cols}{f', PRIMARY KEY ({chr(44).join(key)})' if key else ''})")
    con.execute(f"INSERT INTO {table} ({names}) SELECT {names} FROM ({select})")
    return stage.count(con, table)


#: Every gvkey:iid a prices path claims for a fund ticker (``universe.norm`` form): its spine ``security`` row, its
#: ticker series, and its CUSIP alias, reached through the spine row's id or the ``sym:``/``cik:`` id the fetch minted.
ETF_CLAIMS_SQL = f"""
    SELECT {universe.norm('s.ticker')} AS tic, s.gvkey || ':' || s.iid AS gid, 'spine security' AS how FROM stg_spine s
    WHERE nullif(s.gvkey, '') IS NOT NULL AND nullif(s.iid, '') IS NOT NULL
    UNION ALL SELECT tic, gid, 'ticker series' FROM _etf_tic_series WHERE pick = 1
    UNION ALL SELECT {universe.norm('s.ticker')}, a.gid, 'cusip alias' FROM _gvkey_alias a
              JOIN stg_spine s ON s.security_id = a.security_id
    UNION ALL SELECT {universe.norm("split_part(a.security_id, ':', 2)")}, a.gid, 'cusip alias' FROM _gvkey_alias a
              WHERE a.security_id LIKE 'sym:%'
    UNION ALL SELECT {universe.norm("split_part(a.security_id, ':', 3)")}, a.gid, 'cusip alias' FROM _gvkey_alias a
              WHERE a.security_id LIKE 'cik:%'"""
#: Per universe fund with a spine gvkey:iid: that gid, the claims that differ, and how many claims there are at all.
ETF_IDENTITY_SQL = f"""
    WITH sp AS (SELECT {universe.norm('ticker')} AS tic, gvkey || ':' || iid AS gid FROM stg_etf
                WHERE nullif(gvkey, '') IS NOT NULL AND nullif(iid, '') IS NOT NULL
                QUALIFY count(*) OVER (PARTITION BY {universe.norm('ticker')}) = 1),
         c AS (SELECT DISTINCT tic, gid, how FROM ({ETF_CLAIMS_SQL}))
    SELECT u.ticker, sp.gid, string_agg(c.how || ' ' || c.gid, '; ' ORDER BY c.how, c.gid)
                             FILTER (WHERE c.gid = sp.gid), count(c.gid)
    FROM _universe_etf u JOIN sp USING (tic) LEFT JOIN c USING (tic)
    GROUP BY 1, 2 ORDER BY 1"""


def etf_identity_filled(con: duckdb.DuckDBPyConnection) -> int:
    """How many ``stg_etf`` rows carry a gvkey:iid: 0 on a spine from before schema 11 (no such columns)."""
    return con.execute("SELECT count(*) FROM stg_etf WHERE nullif(gvkey, '') IS NOT NULL "
                       "AND nullif(iid, '') IS NOT NULL").fetchone()[0]


def etf_identity_issues(con: duckdb.DuckDBPyConnection) -> list[tuple[str, str, str]]:
    """The spine owns ETF identity (#1585, avo 27 Nov 2026 option A): every universe fund whose spine ``etf`` row
    gives a gvkey:iid is checked against each gvkey:iid a prices path claims for it. A claim that differs is
    ``etf_identity_disagrees``, no claim at all ``etf_identity_unclaimed``. Found only: the served ids stay what the
    prices paths make them, and the follow-ups (#1600, #1601) decide when a disagreement refuses a build."""
    if not _has(con, "stg_etf", "stg_spine", "_universe_etf", "_etf_tic_series", "_gvkey_alias"):
        return []
    found: list[tuple[str, str, str]] = []
    for ticker, gid, other, claims in con.execute(ETF_IDENTITY_SQL).fetchall():
        if other:
            found.append(("etf_identity_disagrees", ticker, f"{ticker}: the spine gives {gid}; prices claims {other}"))
        elif not claims:
            found.append(("etf_identity_unclaimed", ticker, f"{ticker}: the spine gives {gid}; no prices path claims it"))
    return found


def _spine(con: duckdb.DuckDBPyConnection) -> int:
    """``stg_spine``: the live spine's ``security`` rows with their security id (empty before a first spine), and
    ``is_etf`` / ``inception`` from its ``etf`` table when it has one (schema 4, #349), for the CRSP ticker rule;
    ``stg_etf``: that ``etf`` table's own rows, which the universe rule reads (``prices.universe``)."""
    from ... import serving
    con.execute("CREATE OR REPLACE TEMP TABLE stg_spine (ticker TEXT, cik TEXT, tier TEXT, security_type TEXT, "
                "gvkey TEXT, iid TEXT, composite_figi TEXT, security_id TEXT, cusip TEXT, is_etf BOOLEAN, "
                "inception DATE)")
    con.execute("CREATE OR REPLACE TEMP TABLE stg_etf (ticker TEXT, aum DOUBLE, is_etn BOOLEAN, is_cef BOOLEAN, "
                "gvkey TEXT, iid TEXT)")
    con.execute(f"CREATE OR REPLACE TEMP TABLE stg_{universe.MY_UNIVERSE_TABLE} (ticker TEXT, kind TEXT)")
    live = serving.live_path("spine")
    if not live.exists():
        return 0
    con.execute(f"ATTACH {base.sql_path(live)} AS live_spine (READ_ONLY)")
    try:
        has_etf = con.execute("SELECT count(*) FROM duckdb_tables() WHERE database_name = 'live_spine' "
                              "AND table_name = 'etf'").fetchone()[0]
        etf_ids = has_etf and con.execute(
            "SELECT count(*) FROM duckdb_columns() WHERE database_name = 'live_spine' AND table_name = 'etf' "
            "AND column_name IN ('gvkey', 'iid')").fetchone()[0] == 2
        ids = "gvkey AS etf_gvkey, iid AS etf_iid" if etf_ids else "NULL AS etf_gvkey, NULL AS etf_iid"
        etf = (f"LEFT JOIN (SELECT ticker AS etf_ticker, inception, {ids} FROM live_spine.etf) e "
               "ON e.etf_ticker = ticker" if has_etf else
               "LEFT JOIN (SELECT NULL AS etf_ticker, CAST(NULL AS DATE) AS inception, NULL AS etf_gvkey, "
               "NULL AS etf_iid) e ON false")
        # Plan v4 step 4 (#1413): a fund the security table keys only by CIK takes the etf table's Compustat
        # series, so it is served as gvkey:iid; the old cik: id is moved by the re-key guard (_move_rekeyed).
        bare = ("nullif(s.gvkey, '') IS NULL AND nullif(s.composite_figi, '') IS NULL "
                "AND nullif(e.etf_gvkey, '') IS NOT NULL AND nullif(e.etf_iid, '') IS NOT NULL")
        con.execute(f"INSERT INTO stg_spine SELECT ticker, cik, tier, security_type, gvkey, iid, composite_figi, "
                    f"{SPINE_ID}, cusip, is_etf, inception FROM (SELECT s.ticker, s.cik, s.tier, s.security_type, "
                    f"CASE WHEN {bare} THEN e.etf_gvkey ELSE s.gvkey END AS gvkey, "
                    f"CASE WHEN {bare} THEN e.etf_iid ELSE s.iid END AS iid, s.composite_figi, "
                    f"nullif(s.cusip, '') AS cusip, e.etf_ticker IS NOT NULL AS is_etf, e.inception "
                    f"FROM live_spine.security s {etf})")
        if has_etf:
            # By name: the universe rule reads aum/is_etn/is_cef; gvkey/iid feed only the identity check (#1585).
            con.execute("INSERT INTO stg_etf (ticker, aum, is_etn, is_cef, gvkey, iid) SELECT ticker, aum, is_etn, "
                        f"is_cef, {'gvkey, iid' if etf_ids else 'NULL, NULL'} FROM live_spine.etf")
        has_mine = con.execute("SELECT count(*) FROM duckdb_tables() WHERE database_name = 'live_spine' "
                               "AND table_name = ?", [universe.MY_UNIVERSE_TABLE]).fetchone()[0]
        if has_mine:
            # ``kind`` says which names are funds (review D5 of #420); a list from before #417's schema has none.
            has_kind = con.execute("SELECT count(*) FROM duckdb_columns() WHERE database_name = 'live_spine' "
                                   "AND table_name = ? AND column_name = 'kind'",
                                   [universe.MY_UNIVERSE_TABLE]).fetchone()[0]
            con.execute(f"INSERT INTO stg_{universe.MY_UNIVERSE_TABLE} SELECT ticker, "
                        f"{'kind' if has_kind else 'NULL'} FROM live_spine.{universe.MY_UNIVERSE_TABLE}")
            con.execute("CREATE OR REPLACE TEMP TABLE _my_universe_held AS SELECT true AS held")
    finally:
        con.execute("DETACH live_spine")
    return stage.count(con, "stg_spine")


def _etf_own_start(con: duckdb.DuckDBPyConnection) -> None:
    """``_etf_own_start``: the first session each ticker was ever seen trading by a source that keys by ticker --
    Alpaca's bars and Yahoo's bars -- which is a fund's own listing window, whatever Compustat holds under that
    ticker. ``universe.ETF_TIC_SERIES_SQL`` reads it: a Compustat series whose prices all stop before the fund began
    trading is a reused ticker's earlier fund and may not be claimed by this one (review S1, #1510). A source this
    build has no staging table for simply names no ticker, and the claim rule then behaves as it did."""
    parts = [f"SELECT {universe.norm('ticker')} AS tic, session_date FROM {name}"
             for name in ("stg_alpaca_bars", yahoo_bars.STAGING) if _has(con, name)]
    body = " UNION ALL ".join(parts) or "SELECT NULL AS tic, CAST(NULL AS DATE) AS session_date WHERE false"
    con.execute("CREATE OR REPLACE TEMP TABLE _etf_own_start AS SELECT tic, min(session_date) AS first_day "
                f"FROM ({body}) WHERE tic IS NOT NULL AND session_date IS NOT NULL GROUP BY 1")


def _universe(ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> int:
    """``_universe_ticker`` and ``_universe``: what this build stores (``prices.universe``, avo's rule of 4 Nov
    2026). Every stored source is filtered through ``_universe``, so a name outside today's universe -- a SPAC, a
    warrant, a preferred, a small or unknown-AUM fund, an untyped name, anything delisted -- is never written."""
    mine = con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = '_my_universe_held'"
                       ).fetchone()[0]
    con.execute("CREATE OR REPLACE TEMP TABLE _universe_ticker AS "
                + (universe.STORED_TICKER_SQL if mine else universe.TICKER_SQL))
    beside = sorted(universe.kept_beside())
    if beside:
        con.execute("INSERT INTO _universe_ticker SELECT unnest(?) EXCEPT SELECT ticker FROM _universe_ticker",
                    [beside])
    con.execute(f"CREATE OR REPLACE TEMP TABLE _universe_etf AS {universe.UNIVERSE_ETF_SQL}")
    _etf_own_start(con)
    con.execute(f"CREATE OR REPLACE TEMP TABLE _etf_tic_series AS {universe.ETF_TIC_SERIES_SQL}")
    con.execute("CREATE OR REPLACE TEMP TABLE _yahoo_rekey AS "
                + (yahoo_bars.RENAMED_SQL if _has(con, yahoo_bars.STAGING)
                   else "SELECT NULL AS ticker, NULL AS security_id WHERE false"))
    con.execute(f"CREATE OR REPLACE TEMP TABLE _universe AS {universe.UNIVERSE_SQL}")
    # A fund only Yahoo prices (no spine row, no Alpaca bar, no Compustat series) is in the universe by its ticker,
    # never by its CIK: a CIK reaches an issuer's other classes (review of #1490, findings 3 and 4).
    con.execute(f"""INSERT INTO _universe SELECT DISTINCT {yahoo_bars.ID} FROM {yahoo_bars.STAGING} y {yahoo_bars.JOIN}
                    WHERE y.ticker IN (SELECT ticker FROM _universe_ticker) AND {yahoo_bars.SERVED}
                    EXCEPT SELECT security_id FROM _universe""")
    # A name that left the universe keeps its stored bars (avo, DECISIONS S18: the store collects everything and is
    # never narrowed; #1079 dropped 20 securities when names left ``my_universe``). It stops getting new fetches
    # (``prices.scope``), but every id the live file serves stays in what this build stores.
    held = stage.live_served(con)
    kept = 0
    if held:
        kept = stage.count(con, "_universe")
        con.execute("INSERT INTO _universe SELECT unnest(?) EXCEPT SELECT security_id FROM _universe", [sorted(held)])
        kept = stage.count(con, "_universe") - kept
    n = stage.count(con, "_universe")
    if mine:
        held = stage.count(con, f"stg_{universe.MY_UNIVERSE_TABLE}")
        where = f"{held} names of the spine's {universe.MY_UNIVERSE_TABLE} list"
    else:
        stocks = con.execute(f"SELECT count(*) FROM stg_spine WHERE {universe.STOCK_MEMBER}").fetchone()[0]
        funds = con.execute(f"SELECT count(*) FROM stg_etf WHERE {universe.ETF_MEMBER}").fetchone()[0]
        where = (f"{stocks} stocks (tier {'+'.join(universe.STOCK_TIERS)}, "
                 f"{', '.join(universe.STOCK_TYPES)}) and {funds} ETFs over "
                 f"{universe.ETF_MIN_AUM:,.0f} AUM, by the rule (no {universe.MY_UNIVERSE_TABLE} list yet)")
    ctx.notes.append(f"universe: {where}, {len(beside)} benchmarks, rotation ETFs and watched names beside them, "
                     f"{kept} ids the live file serves outside it kept, {n} security ids stored")
    return n


def _loss(row: tuple[str, int, int]) -> int:
    """The bars a ``(security_id, was, has)`` row of ``_refuse_shrink`` lost."""
    return row[1] - row[2]


def _named(rows: list[tuple[str, int, int]]) -> str:
    """The worst 20 of the rows, each as ``id was -> has``."""
    return ", ".join(f"{sid} {was:,} -> {has:,}" for sid, was, has in rows[:20]) + (" ..." if len(rows) > 20 else "")


# A live ``cik:<CIK>:<T>`` id whose spine row (same CIK and ticker) now carries a stronger id this build serves: the
# spine re-keyed it (the night run of 22 Nov 2026 linked 208 names by ticker, ``link_source = 'tic_nocik'``; five of
# them -- BRRR, IBIT, NCIQ, XRPC, GBUG -- had bars under the old id on the live file, 23 Nov 2026, #1413 / C3).
REKEYED_SQL = """
    SELECT l.security_id AS old_id, any_value(s.security_id) AS new_id
    FROM (SELECT unnest(?) AS security_id) l
    JOIN stg_spine s ON s.cik = split_part(l.security_id, ':', 2) AND s.ticker = split_part(l.security_id, ':', 3)
    WHERE s.security_id <> l.security_id
      AND s.security_id IN (SELECT DISTINCT security_id FROM price_bar_daily)
    GROUP BY 1 HAVING count(DISTINCT s.security_id) = 1"""


# A live id the Yahoo fetch saw (``sym:T``, ``figi:X``, ``cik:C:T``) whose Yahoo rows this build serves under another
# id: Compustat or the spine picked the name up, or the name was renamed and its old ticker file now keys to the
# spine's current id (``yahoo_bars.ID``, ``yahoo_bars.RENAMED_SQL``). Yahoo is not asked for the old name any more,
# and the old id would be carried frozen beside the new one (review N2 and #1490 finding 8; avo's D1 of
# 24 Nov 2026 "Yeni id'ye taşı": moved as C3 moves).
YAHOO_REKEYED_SQL = f"""
    SELECT y.security_id AS old_id, any_value({yahoo_bars.ID}) AS new_id
    FROM {yahoo_bars.STAGING} y {yahoo_bars.JOIN}
    WHERE y.security_id IN (SELECT unnest(?)) AND {yahoo_bars.ID} <> y.security_id AND {yahoo_bars.SERVED}
      AND {yahoo_bars.ID} IN (SELECT DISTINCT security_id FROM price_bar_daily)
      AND y.security_id NOT IN (SELECT DISTINCT security_id FROM price_bar_daily)
    GROUP BY 1 HAVING count(DISTINCT {yahoo_bars.ID}) = 1"""


def _has(con: duckdb.DuckDBPyConnection, *names: str) -> bool:
    """Every one of ``names`` is a table or view of ``con``."""
    return con.execute("SELECT count(DISTINCT table_name) FROM information_schema.tables WHERE table_name IN "
                       "(SELECT unnest(?))", [list(names)]).fetchone()[0] == len(set(names))


def _move_rekeyed(ctx: base.RunContext, con: duckdb.DuckDBPyConnection, live: dict[str, int]) -> set[str]:
    """C3 option (a), #1413: a re-keyed id is **moved**, not lost and not served twice. The new id takes the old
    id's live bars for every session it has none of (its own bar wins a session both hold), and the old id is not
    carried back by ``_refuse_shrink``. Without this the build served the name under both ids, two rows a session in
    ``price_bars_daily``. The old id's rows leave the served file with it: avo's word (C3), so the build that first
    does it is a whole build with a backup."""
    old = sorted(sid for sid in live if sid.startswith("cik:"))
    pairs = dict(con.execute(REKEYED_SQL, [old]).fetchall()) if old else {}
    if _has(con, yahoo_bars.STAGING, "_etf_tic_series", "_yahoo_rekey", "stg_spine"):
        pairs |= dict(con.execute(YAHOO_REKEYED_SQL, [sorted(set(live) - set(pairs))]).fetchall())
    if pairs:
        carried = stage.carry_live_as(con, pairs)
        ctx.notes.append(f"{len(pairs)} re-keyed ids moved to their spine id with {carried:,} live bars the new id "
                         "had no session of: " + ", ".join(f"{o} -> {n}" for o, n in sorted(pairs.items())[:20]))
    return set(pairs)


def _refuse_shrink(ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> None:
    """Refuse a build whose ``price_bar_daily`` serves fewer securities or fewer rows than the live file, unless the
    request asked for it (``allow_shrink``). The serving swap's own guard allows a 1 % row shrink per table, and
    #1079's loss of 20 securities was 40,327 of 30 million rows, 0.13 %: it went through.

    A Compustat series that became a served fund's alias (``_gvkey_alias``) is moved, not lost: its id goes and its
    sessions join the fund's, so neither its id nor its rows count, and the fund's rows are compared with the fund's
    alone.

    A security the live file serves that this build's sources return no bar for at all (a name gone from Compustat's
    and Alpaca's files: bankrupt, renamed to an ``...Q`` ticker; VBNK, KPTI, KNRXF, PLCE on 19 Nov 2026) keeps the
    bars the live file holds: they are copied over before the counts, so the store is never narrowed by a source
    that stopped.

    The rows are compared **per security id as well as over the file** (#1096). The file total alone let a served
    name lose bars whenever the rest of the file grew by more: the 19 Nov 2026 whole build (request #800) grew
    ``price_bar_daily`` 30,140,389 -> 30,906,005 rows and still came out 32 bars short over 10 securities, and it
    swapped in. The swap's own guard cannot catch it either: it compares a table's row count, and the table grew.

    The per-id check has a tolerance of ``PER_ID_SHRINK_BARS`` bars (avo's word of 19 Nov 2026): a security that
    comes out **more** than that many bars short of the live file refuses the build, and a shortfall within the
    tolerance -- what a source restating the last days of one name costs -- is named in the build note instead, so
    it is read and not silent. The file total still may not shrink at all, whatever the per-id counts are. The only
    way past the guard is the request's explicit ``allow_shrink`` (avo's word, DECISIONS S18), which turns the whole
    guard off and is recorded with the request's params."""
    live = stage.live_served(con)
    if not live:
        return
    rekeyed = _move_rekeyed(ctx, con, live)
    if ctx.allow_shrink:
        return

    def served() -> dict[str, int]:
        return dict(con.execute("SELECT security_id, count(*) FROM price_bar_daily "
                                "WHERE security_id NOT LIKE 'index:%' GROUP BY 1").fetchall())

    now = served()
    moved = {g for g, sid in con.execute("SELECT gid, security_id FROM _gvkey_alias").fetchall() if sid in now}
    moved |= rekeyed
    gone = sorted(set(live) - set(now) - moved)
    if gone:
        carried = stage.carry_live(con, gone)
        ctx.notes.append(f"{len(gone)} securities no source returns a bar for kept with their {carried:,} stored "
                         f"bars: {', '.join(gone[:20])}{' ...' if len(gone) > 20 else ''}")
        now = served()
    lost = sorted(set(live) - set(now) - moved)
    # Worst first, so the 20 the message names are the 20 deepest shortfalls.
    short = sorted(((sid, was, now[sid]) for sid, was in live.items()
                    if sid not in moved and sid in now and now[sid] < was),
                   key=lambda r: (r[2] - r[1], r[0]))
    over = [r for r in short if _loss(r) > PER_ID_SHRINK_BARS]
    before = sum(n for sid, n in live.items() if sid not in moved)
    after = sum(now.values())
    if short and not over:
        ctx.notes.append(f"{sum(_loss(r) for r in short):,} bars short inside {len(short)} securities still "
                         f"served, each within the {PER_ID_SHRINK_BARS}-bar tolerance: {_named(short)}")
    if lost or over or after < before:
        bars = sum(_loss(r) for r in over)
        raise ValueError(f"price_bar_daily would lose {len(lost)} securities, and {bars:,} bars inside "
                         f"{len(over)} securities it still serves over the {PER_ID_SHRINK_BARS}-bar per-security "
                         f"tolerance (rows {before:,} -> {after:,}) against the live file; "
                         f"lost: {', '.join(lost[:20]) or 'none'}{' ...' if len(lost) > 20 else ''}; "
                         f"short: {_named(over) if over else 'none'}. "
                         f"Pass allow_shrink only on avo's word (DECISIONS S18)")


def _index_levels(con: duckdb.DuckDBPyConnection) -> str:
    """The S&P 500 index level from the market store's Cboe Parquet, as bars (``index:SPX``)."""
    parts = sorted((base.parquet_root() / "cboe" / "index").glob("year=*/part-0.parquet"))
    empty = "SELECT " + ", ".join(f"CAST(NULL AS {t}) AS {c}" for c, t in PRICE_BAR) + " WHERE false"
    if not parts:
        return empty
    files = ", ".join(base.sql_path(p) for p in parts)
    return ("SELECT 'index:SPX' AS security_id, session_date, 'SPX' AS symbol, CAST(NULL AS TEXT) AS cik, open, high, "
            "low, coalesce(close, value) AS close, CAST(NULL AS DOUBLE) AS volume, CAST(NULL AS DOUBLE) AS vwap, "
            "CAST(NULL AS BIGINT) AS trade_count, CAST(NULL AS DOUBLE) AS shares_outstanding, "
            f"'{INDEX_SOURCE}' AS source, source_as_of, fetched_at, run_id FROM read_parquet([{files}], "
            "union_by_name = true) WHERE series_id = 'SPX' AND session_date = obs_date "
            "QUALIFY row_number() OVER (PARTITION BY obs_date ORDER BY fetched_at DESC) = 1")


BUILD_SQL = """
CREATE OR REPLACE TEMP TABLE _alp AS
    SELECT coalesce(s.security_id, b.security_id) AS security_id, b.session_date, b.ticker AS symbol, b.cik,
           b.open, b.high, b.low, b.close, b.volume, b.vwap, b.trade_count,
           CAST(NULL AS DOUBLE) AS shares_outstanding, '{bars}' AS source, b.source_as_of, b.fetched_at, b.run_id,
           b.symbol AS alpaca_symbol, b.close_all, b.all_return, b.tier
    FROM stg_alpaca_bars b LEFT JOIN stg_spine s ON s.ticker = b.ticker AND s.cik IS NOT DISTINCT FROM b.cik
    WHERE {in_universe_alp}
    QUALIFY row_number() OVER (PARTITION BY coalesce(s.security_id, b.security_id), b.session_date
                               ORDER BY b.fetched_at DESC) = 1;
CREATE OR REPLACE TEMP TABLE _symsec AS
    SELECT alpaca_symbol, security_id, min(session_date) AS lo, max(session_date) AS hi FROM _alp GROUP BY ALL;
CREATE OR REPLACE TEMP TABLE _act AS
    WITH a AS (SELECT *, coalesce(ex_date, effective_date, process_date) AS eff FROM stg_alpaca_actions
               QUALIFY row_number() OVER (PARTITION BY action_id ORDER BY fetched_at DESC) = 1),
    cand AS (
        SELECT a.action_id, m.security_id, 0 AS pri,
               CASE WHEN a.eff < m.lo THEN date_diff('day', a.eff, m.lo)
                    WHEN a.eff > m.hi THEN date_diff('day', m.hi, a.eff) ELSE 0 END AS dist
        FROM a JOIN _symsec m ON m.alpaca_symbol = upper(a.symbol)
        UNION ALL
        SELECT a.action_id, s.security_id, 1 AS pri, 0 AS dist
        FROM a JOIN stg_spine s ON s.ticker = replace(upper(a.symbol), '.', '-')
        WHERE s.security_id IN (SELECT security_id FROM _symsec)),
    best AS (SELECT action_id, security_id FROM cand
             QUALIFY row_number() OVER (PARTITION BY action_id ORDER BY pri, dist, security_id) = 1)
    SELECT best.security_id, a.*, '{actions}' AS source FROM a JOIN best USING (action_id);
CREATE OR REPLACE TEMP TABLE _permno_link AS {link};
CREATE OR REPLACE TEMP TABLE _gvkey_alias AS {alias};
"""
# The history rows, over the WRDS staging: whole on a whole build, the rebuilt slice on the live copy (``incremental``).
BUILD_HIST_SQL = """
CREATE OR REPLACE TEMP TABLE _secd_listed AS {listed};
CREATE OR REPLACE TEMP TABLE _hist_all AS
    SELECT * FROM ({crsp}) UNION ALL BY NAME SELECT * FROM ({comp}) UNION ALL BY NAME SELECT * FROM ({yahoo});
"""
# Yahoo's bars (``yfinance/bars``, avo 24 Nov 2026, F28): asked only for the names Compustat has not priced lately,
# priority 3, so ``HIST_FIRST`` serves one only on a session no Compustat row of the security has. Keyed by
# ``yahoo_bars.ID``: the Compustat series claiming a fund's ticker, else the spine's id, else the spine's id of a
# renamed name's CIK (``_yahoo_rekey``), else the fetch's; a ``class:``
# id never (review of #1490, findings 2 and 3).
YAHOO_BARS = f"""
    SELECT {yahoo_bars.ID} AS security_id, y.session_date, y.ticker AS symbol, y.cik,
           y.open, y.high, y.low, y.close, y.volume, CAST(NULL AS DOUBLE) AS vwap, CAST(NULL AS BIGINT) AS trade_count,
           CAST(NULL AS DOUBLE) AS shares_outstanding, '{yahoo_bars.NAME}' AS source, y.source_as_of, y.fetched_at,
           y.run_id, 3 AS priority, {yahoo_bars.ID} AS series
    FROM {yahoo_bars.STAGING} y {yahoo_bars.JOIN}
    WHERE y.session_date <= coalesce(getvariable('rc_build_date'), DATE '9999-12-31')
      AND {yahoo_bars.ID} IN (SELECT security_id FROM _universe) AND {yahoo_bars.SERVED}
    QUALIFY row_number() OVER (PARTITION BY {yahoo_bars.ID}, y.session_date ORDER BY y.fetched_at DESC) = 1"""
# The kind of an action for "the same action on the same day": a split, a reverse split and a stock dividend are one
# kind, each a step of the share basis (review SHOULD 3 of #382: Compustat's ajexdi step and an Alpaca stock dividend
# of the same day were both applied).
ACTION_KIND = ("CASE WHEN {a}.action_type IN ('forward_split', 'reverse_split', 'stock_dividend') THEN 'split' "
               "WHEN {a}.action_type IN ('cash_dividend', 'capital_gains_distribution') THEN 'cash_dividend' "
               "ELSE {a}.action_type END")
# The ratio and the amount ``corporate_action`` serves of an Alpaca action, over its raw rates.
ACTION_RATIO = ("CASE WHEN {a}.action_type IN ('forward_split', 'reverse_split') AND {a}.old_rate > 0 "
                "AND {a}.new_rate > 0 THEN {a}.new_rate / {a}.old_rate "
                "WHEN {a}.action_type = 'stock_dividend' AND {a}.rate > 1 THEN {a}.rate "
                "WHEN {a}.action_type = 'stock_dividend' AND {a}.rate > 0 THEN 1 + {a}.rate END")
# Alpaca writes a stock dividend's ``rate`` as the share ratio (new over old): all 8 in the tree on 24 Nov 2026 lie
# between 1 and 1.5 (SCCO 1.0106 = Compustat's ajexdi step), so ``1 + rate`` doubled every factor (#1413).
# shortcut: a rate at or below 1 is still read as a fraction (no live example of one), revisit when Alpaca shows one.
ACTION_AMOUNT = "CASE WHEN {a}.action_type IN ('cash_dividend', 'capital_gains_distribution') THEN {a}.rate END"
# Compustat's split that Alpaca has a day or few off is the same split (#268): Compustat's ``datadate`` is the first
# session on the new basis and Alpaca's ``ex_date`` is not always that day, so the same-day rule in
# ``_wrds_actions`` let both rows in and the share basis stepped twice -- a doubled split factor over every bar
# before it. Alpaca's is kept, as on the same day. A split, a reverse split and a stock dividend are one kind here
# (``ACTION_KIND``), but **an Alpaca stock dividend never stands in for Compustat's row** (SCCO, 3 Nov 2026, #1413
# P-D): Alpaca's ``rate`` read as ``1 + rate`` gave 2.0106 where Compustat's own step was about 1.01, so every
# adjusted close before it was halved. Compustat's row is kept and the Alpaca stock dividend beside it is held back
# (``ALPACA_STOCK_DIV_BESIDE``, its ``not_applied_why``). Only Compustat's row is dropped,
# and only against an Alpaca row, so a second Compustat split of its own is untouched; a cash dividend is matched by
# amount instead (the twins in ``_wrds_actions``).
# Side effect: a real second split within SPLIT_SAME_DAYS of Alpaca's would be dropped too. On the live copy a pair
# across the rebuilt window's start stays until the next whole build. ``{mine}`` is a chunk's own securities.
SPLIT_TWIN_SQL = f"""DELETE FROM _act w WHERE w.source = '{wrds_history.NAME}'
    AND {ACTION_KIND.format(a='w')} = 'split'{{mine}}
    AND EXISTS (SELECT 1 FROM _act p WHERE p.security_id = w.security_id AND p.source = '{ALPACA_ACTIONS}'
                AND {ACTION_KIND.format(a='p')} = 'split' AND p.action_type <> 'stock_dividend'
                AND abs(date_diff('day', p.ex_date, w.ex_date)) <= {SPLIT_SAME_DAYS})"""
# The Alpaca stock dividend ``SPLIT_TWIN_SQL`` lets Compustat's split-kind row stand beside: one share-basis step,
# Compustat's, is applied, never both (#1413 P-D). Over ``_act`` and an alias ``a`` of the action.
ALPACA_STOCK_DIV_BESIDE = f"""(a.source = '{ALPACA_ACTIONS}' AND a.action_type = 'stock_dividend'
    AND EXISTS (SELECT 1 FROM _act w WHERE w.security_id = a.security_id AND w.source = '{wrds_history.NAME}'
                AND {ACTION_KIND.format(a='w')} = 'split'
                AND abs(date_diff('day', w.ex_date, a.ex_date)) <= {SPLIT_SAME_DAYS}))"""

# Alpaca's cash dividend that copies the rate of its own stock dividend the same day and security: a mislabelled twin
# of the stock dividend, never cash (SCCO, 3 Nov 2026: a stock dividend at 1.0106 and two cash rows, 1.30 and 1.0106,
# read by the parquet check of #1413). Held back with ``not_applied_why``. Over ``_act`` and an alias ``a``.
ALPACA_CASH_TWIN_OF_STOCK_DIV = f"""(a.source = '{ALPACA_ACTIONS}' AND a.action_type = 'cash_dividend'
    AND EXISTS (SELECT 1 FROM _act s WHERE s.security_id = a.security_id AND s.source = '{ALPACA_ACTIONS}'
                AND s.action_type = 'stock_dividend' AND s.ex_date = a.ex_date AND s.rate = a.rate))"""


class PricesServing:
    name = NAME
    parquet_reads = ("cboe/index",)                     # the index:SPX bars (_index_levels; dirty.read_dirs)
    kind = KIND
    providers: tuple[str, ...] = ()
    tables = TABLES
    feeds: tuple[str, ...] = ()       # it builds every served table itself
    cadence = "daily"
    backfill_needs_from = False
    # In the scheduled flow since #446 step 8: a build on a copy of the live file fits the builder's window, so this
    # dataset is due on its cadence with no hand start. Its **whole** build does not fit (86 min for the 2010+
    # volume, 6 h 12 min for the first one with the WRDS history), so the hourly pass leaves that one to a person:
    # ``base.WholeBuildByHand``, a skipped check row naming the reason.
    whole_build_by_hand = True

    def default_as_of(self) -> date:
        from ....core import calendar
        return calendar.latest_complete_session()

    def fetch(self, ctx: base.RunContext, as_of: date) -> list:
        return []                                   # built from the other datasets' Parquet only

    def backfill(self, ctx: base.RunContext, start, end: date) -> None:
        return None

    def to_parquet(self, ctx, raw) -> list:
        return []

    def to_parquet_all(self, ctx, raws) -> list:
        return []

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        from . import bars as _bars  # noqa: F401 - the staging tables below are the sources'
        found: list[tuple[str, str, str]] = []
        have = {ALPACA_BARS: stage.count(con, "stg_alpaca_bars"), ALPACA_ACTIONS: stage.count(con, "stg_alpaca_actions"),
                COVER: stage.count(con, "stg_sec_cover"), YAHOO: stage.count(con, "stg_yahoo_float"),
                TV: stage.count(con, "stg_tv_float")}
        for ds, n in have.items():
            if not n:
                found.append(("source_never_run", ds, f"{ds} has no rows in this build"))
        _spine(con)
        # The serving build's own date, the latest complete New York session, cuts the history's future rows (review
        # SHOULD 2 of #382): not DuckDB's UTC wall clock, and not the as-of of the dataset that started the build (a
        # backfill to a past day must not cut the later history). Set before ``_universe``, whose ETF branch reads it.
        con.execute(f"SET VARIABLE rc_build_date = DATE '{self.default_as_of().isoformat()}'")
        _universe(ctx, con)
        con.execute(BUILD_SQL.format(in_universe_alp=universe.IN_UNIVERSE.format(
                                         sid="coalesce(s.security_id, b.security_id)"),
                                     bars=ALPACA_BARS, actions=ALPACA_ACTIONS, link=wrds_history.PERMNO_LINK,
                                     alias=wrds_history.GVKEY_ALIAS))
        self._link_note(ctx, con, found)
        counts = {}
        # A build on the live copy (#446): what it rebuilds is worked out over the whole identity just built, and
        # the WRDS staging narrowed to it before the history rows are made (``incremental``).
        live = incremental.active(ctx)
        sc = None
        if live:
            sc = incremental.scope(ctx, con, lambda: counts.__setitem__("shares_class",
                                                                        self._shares(con, found, live=True)))
            ctx.pending[NAME + ":scope"] = sc
        incremental.record_identity(con)
        rows = incremental.where("session_date") if live else None
        # A whole build runs the WRDS history one chunk of securities at a time (#654), so its spill is about 1/N of
        # one pass; ``RC_PRICES_CHUNKS=1`` and the build on the live copy keep the single pass.
        chunked = None if live or stage.chunks() == 1 else Chunked(ctx, con, stage.chunks())
        if chunked is None:
            con.execute(BUILD_HIST_SQL.format(crsp=wrds_history.CRSP_BARS, comp=wrds_history.COMP_BARS,
                                              listed=wrds_history.SECD_LISTED, yahoo=YAHOO_BARS))
            # Alpaca's bar wins its session; of the history bars, Compustat's (priority 1) before CRSP's.
            bars_sql = f"SELECT * FROM ({_index_levels(con)}) UNION ALL {HIST_BARS}"
            counts["price_bar_daily"] = _create(con, "price_bar_daily", bars_sql, live, rows)
            moved, basis = _hist_counts(con)
        else:
            counts["price_bar_daily"], moved, basis = chunked.bars(self)
        self._key_check(ctx, con, "price_bar_daily", found)
        # The carry of a security no source returns a bar for (``_refuse_shrink``) adds rows after the count above,
        # so the count the swap checks is taken again here: the 19 Nov 2026 whole build carried 12,190 bars and the
        # swap then refused it over exactly those rows ("has 30905400 rows, expected 30893210").
        _refuse_shrink(ctx, con)
        counts["price_bar_daily"] = stage.count(con, "price_bar_daily")
        # The dated exchange rule against today's code: what it serves that today's code would not, and the reverse.
        if any(moved):
            ctx.notes.append(f"exchange history: {moved[0]} secd rows of {moved[1]} securities listed that day though "
                             f"not today, {moved[2]} rows of {moved[3]} listed today though not that day"
                             + (" (of the stored securities)" if chunked else ""))
        if basis:
            ctx.notes.append("Compustat day returns by rule: "
                             + ", ".join(f"{n} {b}" for b, n in sorted(basis.items())))
        counts["corporate_action"] = self._actions(ctx, con, found, live, wrds=chunked is None)
        if live:
            # The factors are made from every action the file now holds, with the close before each from its bars:
            # ``_act_final``'s ``close_before``, by the same ASOF join.
            con.execute("""CREATE OR REPLACE TEMP TABLE _act_final AS
                SELECT c.*, p.close AS close_before FROM corporate_action c ASOF LEFT JOIN price_bar_daily p
                    ON p.security_id = c.security_id AND c.ex_date > p.session_date""")
        counts["adj_factor"] = _create(con, "adj_factor", ADJ_SQL, live)
        if not live:
            counts["shares_class"] = self._shares(con, found)
        counts["security_symbol"] = _create(con, "security_symbol", SYMBOL_SQL, live)
        if chunked is None:
            # On the live copy the caps of a rebuilt session need the bars ``ISSUER_WITHIN_DAYS`` before it, and
            # nothing older: the issuer cap reads each class's newest cap at most that old.
            near = (f"AND ({incremental.where(f'b.session_date + INTERVAL {ISSUER_WITHIN_DAYS} DAY', 'b.security_id')})"
                    if live else "")
            caps_sql = MARKET_CAP_SQL.format(within=ISSUER_WITHIN_DAYS).replace("/*near*/", near)
            counts["market_cap_daily"] = _create(con, "market_cap_daily", caps_sql, live, rows)
        else:
            counts["market_cap_daily"] = chunked.caps()
        self._key_check(ctx, con, "market_cap_daily", found)
        counts["price_revision"] = _create(con, "price_revision",
                                           f"{REVISION_SQL} UNION ALL {wrds_history.REVISIONS_SQL}", live)
        alpaca = None
        if live:
            counts["wrds_price_diff"] = stage.count(con, "wrds_price_diff")
        elif chunked is None:
            counts["wrds_price_diff"] = self._wrds_report(con)
        else:
            counts["wrds_price_diff"], alpaca = chunked.report()
            chunked.note()
        if not live:
            counts["wrds_price_diff"] += stage.carry_reports(con)
        self._views(con)
        found += self._issues(con, have, live, alpaca)
        identity = etf_identity_issues(con)
        found += identity
        ctx.notes.append(f"etf identity vs the spine (#1585): {etf_identity_filled(con)} etf rows carry a gvkey:iid; "
                         f"{sum(k == 'etf_identity_disagrees' for k, _, _ in identity)} universe funds claimed "
                         f"otherwise, {sum(k == 'etf_identity_unclaimed' for k, _, _ in identity)} unclaimed")
        ctx.pending[NAME] = found
        return counts

    @staticmethod
    def _key_check(ctx: base.RunContext, con: duckdb.DuckDBPyConnection, table: str, found: list) -> None:
        """The key of a table written without a ``PRIMARY KEY`` (``no_primary_key``), checked once its rows are in:
        a duplicate the key would have refused is a build issue, named with its key value, and the build goes on.
        With the key on, DuckDB has already refused one, so there is nothing to check."""
        if table not in no_primary_key():
            return
        dups = duplicate_keys(con, table)
        if not dups:
            return
        ctx.notes.append(f"{table}: {len(dups)} key value(s) held more than once")
        for key, n in dups:
            found.append(("duplicate_key", f"{table}:{key}",
                          f"{n} rows share ({', '.join(KEYS[table])}) = {key}"))

    @staticmethod
    def _link_note(ctx: base.RunContext, con: duckdb.DuckDBPyConnection, found: list) -> None:
        """The CRSP link, observable (review S4 of #353): PERMNOs per rule, the unlinked ones, the gvkey aliases; the
        ticker links, the one rule without an identifier behind it, as one issue naming them."""
        if not stage.count(con, "stg_wrds_dsf"):
            return
        by = dict(con.execute("SELECT how, count(*) FROM _permno_link GROUP BY how").fetchall())
        unlinked = con.execute("SELECT count(DISTINCT permno) FROM stg_wrds_dsf "
                               "WHERE permno NOT IN (SELECT permno FROM _permno_link)").fetchone()[0]
        aliases = stage.count(con, "_gvkey_alias")
        no_day = con.execute("SELECT count(*) FROM stg_spine WHERE is_etf AND inception IS NULL AND security_id "
                             "NOT IN (SELECT security_id FROM _permno_link) AND ticker IN "
                             "(SELECT arg_max_null(ticker, dlycaldt) FROM stg_wrds_dsf GROUP BY permno)").fetchone()[0]
        ctx.notes.append("CRSP link: " + ", ".join(f"{by.get(h, 0)} by {h}" for h in
                                                   ("hdrcusip", "cusip", "ticker", "compustat"))
                         + f"; {unlinked} unlinked; {aliases} gvkey aliases; "
                         f"{no_day} ETFs without an inception day unlinked")
        # One issue per security (an open issue's detail is not rewritten, so one shared row would freeze its list).
        # An ETF's ticker link is its designed one (the spine holds no CUSIP for it; the inception day guards it).
        for sid, permno, ticker in con.execute(
                "SELECT l.security_id, l.permno, s.ticker FROM _permno_link l JOIN stg_spine s USING (security_id) "
                "WHERE l.how = 'ticker' AND NOT coalesce(s.is_etf, false) ORDER BY s.ticker").fetchall():
            found.append(("crsp_ticker_link", sid, f"PERMNO {permno} linked to {ticker} by ticker only (no CUSIP)"))

    # ── Actions ───────────────────────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _wrds_actions(con: duckdb.DuckDBPyConnection, live: bool = False, chunk: bool = False) -> None:
        """The WRDS history's part of the actions, over the WRDS staging: Compustat's into ``_act``, CRSP's lone
        splits into ``_crsp_split_near``. A chunk (``Chunked``) adds the rows of its own securities to both."""
        mine = " AND w.security_id IN (SELECT security_id FROM _bucket)" if chunk else ""
        # Compustat's actions of the securities with bars, unless Alpaca has one of that kind that day (an Alpaca stock
        # dividend does not count: Compustat's step is the one applied, ``ALPACA_STOCK_DIV_BESIDE``).
        con.execute(f"""INSERT INTO _act BY NAME SELECT w.* FROM ({wrds_history.ACTIONS_SQL}) w
            WHERE w.security_id IN (SELECT DISTINCT security_id FROM price_bar_daily){mine}
              AND NOT EXISTS (SELECT 1 FROM _act p WHERE p.security_id = w.security_id AND p.ex_date = w.ex_date
                              AND {ACTION_KIND.format(a='p')} = {ACTION_KIND.format(a='w')}
                              AND p.action_type <> 'stock_dividend')""")
        # Yahoo's splits and dividends (D2, 24 Nov 2026), only on a day whose served bar is Yahoo's and that holds no
        # Alpaca or Compustat action of the kind: a Yahoo-only name had no total return at all (review of #1490, 1).
        con.execute(f"""INSERT INTO _act BY NAME SELECT y.* FROM ({yahoo_bars.ACTIONS_SQL}) y
            WHERE EXISTS (SELECT 1 FROM price_bar_daily b WHERE b.security_id = y.security_id
                          AND b.session_date = y.ex_date AND b.source = '{yahoo_bars.NAME}'){mine.replace('w.', 'y.')}
              AND NOT EXISTS (SELECT 1 FROM _act p WHERE p.security_id = y.security_id AND p.ex_date = y.ex_date
                              AND {ACTION_KIND.format(a='p')} = {ACTION_KIND.format(a='y')})""")
        # The split Alpaca and Compustat both know, its day a session or two apart (``SPLIT_TWIN_SQL``, #268); the
        # dropped ones are counted for the build note.
        splits = con.execute(SPLIT_TWIN_SQL.format(mine=mine)).fetchone()[0]
        con.execute("CREATE TEMP TABLE IF NOT EXISTS _split_twin (n BIGINT)")
        con.execute("INSERT INTO _split_twin VALUES (?)", [splits])
        # Compustat's cash dividend that Alpaca has with the same amount a day or few off (Compustat's day is not
        # always Alpaca's ex-date) is the same dividend: Alpaca's is kept, as on the same day, and the dropped ones
        # are counted for the build note (prices plan 16 Nov 2026, P5: 041545:03 0.0516 on 21, 22 and 23 Oct).
        # Side effect: a real second dividend of the same amount within SPLIT_SAME_DAYS would be dropped too. A special
        # or a non-USD Alpaca row never stands in for Compustat's. On the live copy a pair across the rebuilt window's
        # start stays until the next whole build.
        twins = con.execute(f"""DELETE FROM _act w WHERE w.source = '{wrds_history.NAME}'
            AND {ACTION_KIND.format(a='w')} = 'cash_dividend'{mine}
            AND EXISTS (SELECT 1 FROM _act p WHERE p.security_id = w.security_id AND p.source = '{ALPACA_ACTIONS}'
                        AND {ACTION_KIND.format(a='p')} = 'cash_dividend'
                        AND abs(date_diff('day', p.ex_date, w.ex_date)) <= {SPLIT_SAME_DAYS}
                        AND abs(p.rate - w.rate) < 1e-9 AND p.special IS NOT DISTINCT FROM w.special
                        AND coalesce(upper(p.currency), 'USD') = 'USD')""").fetchone()[0]
        con.execute("CREATE TEMP TABLE IF NOT EXISTS _div_twin (n BIGINT)")
        con.execute("INSERT INTO _div_twin VALUES (?)", [twins])
        # CRSP's splits are the cross-check only (Order 4; the WRDS access inventory of 3 Nov 2026 prefers
        # Compustat's daily splits, and avo's rule of 4 Nov 2026 leaves CRSP no served bar): one no Alpaca or
        # Compustat split of the security is near is kept aside; the one the served close jumps across is applied
        # from CRSP (#661, avo 21 Nov 2026), the rest are named only.
        into = "INSERT INTO _crsp_split_near" if chunk else "CREATE OR REPLACE TEMP TABLE _crsp_split_near AS"
        con.execute(f"""{into}
            SELECT w.* FROM ({wrds_history.CRSP_SPLITS}) w
            WHERE w.security_id IN (SELECT DISTINCT security_id FROM price_bar_daily){mine}
              AND NOT EXISTS (SELECT 1 FROM _act p WHERE p.security_id = w.security_id
                              AND {ACTION_KIND.format(a='p')} = 'split'
                              AND abs(date_diff('day', p.ex_date, w.ex_date)) <= {SPLIT_SAME_DAYS})
              {f"AND {incremental.where(f'w.ex_date + INTERVAL {NEAR_SPLIT_DAYS} DAY', 'w.security_id')}"
               if live else ""}""")

    @staticmethod
    def _actions(ctx: base.RunContext, con: duckdb.DuckDBPyConnection, found: list, live: bool = False,
                 wrds: bool = True) -> int:
        if wrds:                                    # a chunked build added the WRDS part chunk by chunk
            PricesServing._wrds_actions(con, live)
        con.execute("CREATE TEMP TABLE IF NOT EXISTS _div_twin (n BIGINT)")
        twins = con.execute("SELECT coalesce(sum(n), 0) FROM _div_twin").fetchone()[0]
        if twins:
            ctx.notes.append(f"{twins} Compustat cash dividend(s) left out: Alpaca has the same amount within "
                             f"{SPLIT_SAME_DAYS} days")
        con.execute("CREATE TEMP TABLE IF NOT EXISTS _split_twin (n BIGINT)")
        split_twins = con.execute("SELECT coalesce(sum(n), 0) FROM _split_twin").fetchone()[0]
        if split_twins:
            ctx.notes.append(f"{split_twins} Compustat split(s) left out: Alpaca has a split within "
                             f"{SPLIT_SAME_DAYS} days")
        # Alpaca's own repeats (041545:03 on 22 and 23 Oct 2026) are counted, not dropped: avo decides (prices plan P5).
        alpaca_twins = con.execute(f"""SELECT count(*) FROM _act a JOIN _act b ON b.security_id = a.security_id
            AND a.source = '{ALPACA_ACTIONS}' AND b.source = '{ALPACA_ACTIONS}' AND a.ex_date < b.ex_date
            AND date_diff('day', a.ex_date, b.ex_date) <= {SPLIT_SAME_DAYS} AND abs(a.rate - b.rate) < 1e-9
            AND {ACTION_KIND.format(a='a')} = 'cash_dividend' AND {ACTION_KIND.format(a='b')} = 'cash_dividend'
            """).fetchone()[0]
        if alpaca_twins:
            ctx.notes.append(f"{alpaca_twins} pair(s) of Alpaca cash dividends with the same amount within "
                             f"{SPLIT_SAME_DAYS} days, both kept")
        # Review M6 of #382: such a split stands in for the ``price_gap_no_action`` it explains, so it carries the
        # served close's move across its ex-date, from the security's last served bar before it to its first on or
        # after it: the same two bars the gap check pairs, but their raw closes, not its split-adjusted ones (the two
        # ratios differ only where another split sits between those bars, NIT 1 of #420). A jump of GAP_FACTOR or
        # more is a split Compustat lacks, and the served history is wrong there; a smaller move is a CRSP factor
        # step the served bars do not show. One with
        # no served bar on both sides within GAP_DAYS (before Compustat's series starts, or a halt) touches no served
        # bar and explains no gap: counted in the note, not named.
        con.execute("""CREATE OR REPLACE TEMP TABLE _crsp_split_span AS
            SELECT c.*, b.session_date AS day_before, b.close AS close_before_split,
                   a.session_date AS day_after, a.close AS close_after_split
            FROM _crsp_split_near c
            ASOF LEFT JOIN (SELECT security_id, session_date, close FROM price_bar_daily WHERE close > 0) b
                ON b.security_id = c.security_id AND c.ex_date > b.session_date
            ASOF LEFT JOIN (SELECT security_id, session_date, close FROM price_bar_daily WHERE close > 0) a
                ON a.security_id = c.security_id AND c.ex_date <= a.session_date""")
        # The same split the two sources date apart (#661): a candidate of the same ratio as a Compustat or Alpaca
        # split of its security up to SPLIT_SAME_RATIO_DAYS away -- further than the near rule's SPLIT_SAME_DAYS,
        # which is why it is a candidate at all. The nearest such row is carried along, so the detail can name it.
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _crsp_split_dup AS
            SELECT c.security_id, c.ex_date,
                   arg_min(p.ex_date, abs(date_diff('day', p.ex_date, c.ex_date))) AS dup_ex_date,
                   arg_min(p.source, abs(date_diff('day', p.ex_date, c.ex_date))) AS dup_source,
                   arg_min({ACTION_RATIO.format(a='p')}, abs(date_diff('day', p.ex_date, c.ex_date))) AS dup_ratio
            FROM _crsp_split_near c JOIN _act p ON p.security_id = c.security_id
            WHERE {ACTION_KIND.format(a='p')} = 'split'
              AND abs(date_diff('day', p.ex_date, c.ex_date)) <= {SPLIT_SAME_RATIO_DAYS}
              AND {ACTION_RATIO.format(a='p')} > 0 AND {ACTION_RATIO.format(a='c')} > 0
              AND abs(ln({ACTION_RATIO.format(a='c')} / {ACTION_RATIO.format(a='p')}))
                  <= ln({1 + SPLIT_RATIO_TOLERANCE})
            GROUP BY 1, 2""")
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _crsp_only_split AS
            SELECT s.*, s.close_after_split / s.close_before_split AS served_move,
                   d.dup_ex_date, d.dup_source, d.dup_ratio,
                   d.dup_ex_date > s.day_before AND d.dup_ex_date <= s.day_after AS dup_in_gap
            FROM _crsp_split_span s
            LEFT JOIN _crsp_split_dup d ON d.security_id = s.security_id AND d.ex_date = s.ex_date
            WHERE date_diff('day', s.day_before, s.day_after) <= {GAP_DAYS}""")
        jump = f"abs(ln(served_move)) >= ln({GAP_FACTOR})"
        # One split, two dates: only one of them is the day the share basis changed, so only one row is applied
        # (#661). Without this, both step the basis and every adjusted close before the earlier date is off by the
        # ratio -- NVDA's oldest split_factor came out 1/960 where 1/480 is right.
        dup = "dup_ex_date IS NOT NULL"
        # **Which** of the two dates is applied is avo's decision of 22 Nov 2026 ("Gercek değeri tabiki"): the real
        # ex-date wins. The served bars say which that is -- the basis changed between ``day_before`` and
        # ``day_after``, the two bars the jump is measured across, and CRSP's ex-date is inside that gap by
        # construction. Where the other source's date is **outside** it, that date is not the day the basis changed
        # (NVDA: Compustat's 12 Sep 2001 is the planned date, postponed because the exchanges were closed; CRSP's
        # 17 Sep 2001 is the real one, and the served closes halve across it), so **CRSP's row is the applied one**
        # and the other source's stays in ``corporate_action`` unapplied, naming the reason. Where the other
        # source's date is inside the same gap, the served bars cannot tell the two apart and no bar's basis moves
        # either way: nothing is gained by moving the split, so the other source's row stands.
        moved = f"{jump} AND {dup} AND NOT dup_in_gap"
        kept = f"{jump} AND {dup} AND dup_in_gap"
        # avo's decision of 21 Nov 2026 (#661): a CRSP-only split the served close jumps GAP_FACTOR or more across
        # is a split Compustat lacks, and the served history is wrong there, so that row **is served** -- the one
        # exception to "no CRSP row is served" (avo, 4 Nov 2026). Measured on the live file that day: 80 such days,
        # e.g. TNXP's 27 Nov 2018 close served as 0.4156 where its 1:10 reverse split makes it 4.1560. The row
        # carries CRSP's own source, so a reader can tell it apart from Compustat's splits. One whose served bars do
        # not jump is a CRSP factor step the bars do not show (611 of the 691 that day): named only, never applied,
        # because applying it would move a history that is already right.
        applied = con.execute(f"""INSERT INTO _act BY NAME
            SELECT security_id, action_id, action_type, ex_date, eff, old_rate, new_rate, rate, special, currency,
                   record_date, payable_date, '{wrds_history.CRSP}' AS source, source_as_of, fetched_at, run_id
            FROM _crsp_only_split WHERE {jump} AND NOT {dup}""").fetchone()[0]
        # The real ex-date of a restated pair: CRSP's row is applied, as the one the served bars agree with.
        moved_n = con.execute(f"""INSERT INTO _act BY NAME
            SELECT security_id, action_id, action_type, ex_date, eff, old_rate, new_rate, rate, special, currency,
                   record_date, payable_date, '{wrds_history.CRSP}' AS source, source_as_of, fetched_at, run_id
            FROM _crsp_only_split WHERE {moved}""").fetchone()[0]
        # ... and the other source's row is held back, keyed on **its** day, with the reason ``_act_final`` writes.
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _split_restated_by_crsp AS
            SELECT security_id, dup_ex_date, min(ex_date) AS crsp_ex_date, min(day_before) AS day_before,
                   min(day_after) AS day_after
            FROM _crsp_only_split WHERE {moved} GROUP BY 1, 2""")
        # An applied one keeps a row of its own kind: a served CRSP row is the exception, so it stays visible.
        for sid, day, aid, ratio, move, before, after in con.execute(
                "SELECT security_id, ex_date, action_id, new_rate, served_move, day_before, day_after "
                f"FROM _crsp_only_split WHERE {jump} AND NOT {dup} ORDER BY 1, 2").fetchall():
            found.append(("split_applied_crsp", f"{sid}:{day}", f"PERMNO {aid.split(':')[2]}: applied from CRSP, "
                          f"ratio {ratio:.4f}, no Compustat or Alpaca split within {SPLIT_SAME_DAYS} days; the "
                          f"served close jumped x{move:.3f} from {before} to {after}, so Compustat lacks this "
                          "split (#661)"))
        for sid, day, aid, ratio, move, before, after in con.execute(
                "SELECT security_id, ex_date, action_id, new_rate, served_move, day_before, day_after "
                f"FROM _crsp_only_split WHERE NOT ({jump}) ORDER BY 1, 2").fetchall():
            found.append(("split_only_crsp", f"{sid}:{day}", f"PERMNO {aid.split(':')[2]}: CRSP's dlycumfacpr has a "
                          f"split of ratio {ratio:.4f}, no Compustat or Alpaca split within {SPLIT_SAME_DAYS} days; "
                          f"the served close moves x{move:.3f} from {before} to {after}, no jump in the served bars"))
        # One split the two sources date apart: the detail says which of the two days is applied and why. The
        # served bars decide -- the basis changed inside (day_before, day_after], and a date outside that gap is
        # not the day it changed (avo, 22 Nov 2026: the real ex-date wins).
        for sid, day, aid, ratio, dup_day, dup_source, dup_ratio, move, before, after, in_gap in con.execute(
                "SELECT security_id, ex_date, action_id, new_rate, dup_ex_date, dup_source, dup_ratio, served_move, "
                f"day_before, day_after, dup_in_gap FROM _crsp_only_split WHERE {jump} AND {dup} "
                "ORDER BY 1, 2").fetchall():
            which = (f"the served close jumps x{move:.3f} between {before} and {after} and not across "
                     f"{dup_day}, so {day} is the real ex-date and **CRSP's row is the applied one**; "
                     f"{dup_source}'s row stands unapplied, and the bars between the two days are now on the "
                     "right basis"
                     if not in_gap else
                     f"both days fall between the served bars {before} and {after}, so the bars cannot tell them "
                     f"apart and no bar's basis moves either way: {dup_source}'s row stays the applied one")
            found.append(("split_crsp_restated", f"{sid}:{day}", f"PERMNO {aid.split(':')[2]}: {dup_source} has the "
                          f"same split at ratio {dup_ratio:.4f} on {dup_day}, {abs((dup_day - day).days)} day(s) "
                          f"away and within {SPLIT_RATIO_TOLERANCE:.0%} of CRSP's {ratio:.4f}, so this is one split "
                          f"the two sources date apart and it is applied once (#661). {which}"))
        named, restated = con.execute(
            f"SELECT count(*) FILTER (WHERE NOT ({jump})), count(*) FILTER (WHERE {jump} AND {dup}) "
            "FROM _crsp_only_split").fetchone()
        outside = (con.execute("SELECT count(*) FROM _crsp_split_span").fetchone()[0]
                   - named - restated - applied)
        if named or applied or restated or outside:
            ctx.notes.append(f"split_only_crsp: {applied} applied as {wrds_history.CRSP} (the served close jumps "
                             f"{GAP_FACTOR} times or more: Compustat lacks the split, #661), {restated} the same "
                             f"split another source dates within {SPLIT_SAME_RATIO_DAYS} days at the same ratio "
                             f"({moved_n} of them applied from {wrds_history.CRSP} as the real ex-date, the other "
                             f"source's row held back), {named} named with no jump in the served bars, {outside} "
                             f"with no served bar on both sides within {GAP_DAYS} days, not named")
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _act_typed AS
            SELECT a.*, CASE WHEN action_type IN ('forward_split', 'reverse_split') THEN 'split'
                             WHEN action_type IN ('cash_dividend', 'capital_gains_distribution') THEN 'cash_dividend'
                             ELSE action_type END AS action,
                   {ACTION_RATIO.format(a='a')} AS ratio, {ACTION_AMOUNT.format(a='a')} AS amount
            FROM _act a""")
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _act_close AS
            SELECT a.*, p.close AS close_before, p.session_date AS close_day
            FROM _act_typed a ASOF LEFT JOIN price_bar_daily p
                ON p.security_id = a.security_id AND a.ex_date > p.session_date""")
        # An action announced for a later day (the actions window reaches ahead) waits until its ex-date has a
        # session: applied now, it would turn today's bars into a basis that does not exist yet. What is wrong with
        # the action itself (no ratio, no amount) is named at once, so a malformed one gets the window's notice;
        # only what needs the close before the ex-date, and a kind the factors never apply, waits.
        newest = f"({NEWEST_STOCK_SQL})"
        # The row CRSP's real ex-date stands in for (above): it records the same split, so applying it too would
        # step the basis twice, and its own day is not the day the basis changed. It stays in the table, unapplied,
        # and ``action_not_applied`` names it with this reason (avo, 22 Nov 2026).
        restated_by = ("(SELECT max(r.crsp_ex_date) FROM _split_restated_by_crsp r "
                       "WHERE r.security_id = a.security_id AND r.dup_ex_date = a.ex_date)")
        why = f"""CASE
            WHEN {ALPACA_CASH_TWIN_OF_STOCK_DIV}
                THEN 'the same rate as Alpaca''s stock dividend that day: a mislabelled copy of it, not cash (#1413)'
            WHEN {ALPACA_STOCK_DIV_BESIDE}
                THEN 'Compustat records this step within {SPLIT_SAME_DAYS} days and its row is the applied one '
                     || '(an Alpaca stock dividend never stands in for it, #1413)'
            WHEN action IN ('split', 'stock_dividend') AND {restated_by} IS NOT NULL
                THEN 'restated by CRSP: the same split, and the served close changes basis across '
                     || CAST({restated_by} AS TEXT) || ', the real ex-date, which CRSP''s row carries'
            WHEN action IN ('split', 'stock_dividend') AND ex_date IS NULL THEN 'no ex-date'
            WHEN action IN ('split', 'stock_dividend') AND ratio IS NULL THEN 'no ratio'
            WHEN action = 'cash_dividend' AND ex_date IS NULL THEN 'no ex-date'
            WHEN action = 'cash_dividend' AND coalesce(upper(currency), 'USD') <> 'USD' THEN 'paid in ' || currency
            WHEN action = 'cash_dividend' AND NOT (amount > 0) THEN 'no amount'
            WHEN ex_date > {newest} THEN 'not yet ex: the ex-date is after the newest session'
            WHEN action = 'cash_dividend' AND (close_before IS NULL
                 OR date_diff('day', close_day, ex_date) > {CLOSE_BEFORE_DAYS}) THEN 'no close before the ex-date'
            WHEN action = 'cash_dividend' AND NOT (amount < close_before) THEN 'the amount is not below the close'
            WHEN action IN {NOT_APPLIED} THEN action || ': not applied by the factors'
            END"""
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _act_final AS
            SELECT security_id, ex_date, action, action_type, ratio, amount, currency, special,
                   CASE WHEN action IN {APPLIED} OR action IN {NOT_APPLIED} THEN ({why}) IS NULL END AS applied,
                   {why} AS not_applied_why, symbol, new_symbol, record_date, payable_date, process_date,
                   source, action_id AS source_id, source_as_of, fetched_at, run_id,
                   close_before
            FROM _act_close a""")
        # On the live copy: every Alpaca action again (they are few, and which security one lands on can move),
        # and the WRDS actions of the rebuilt days and securities.
        rebuilt = (f"(source = '{ALPACA_ACTIONS}' OR {incremental.where('ex_date')})" if live else None)
        n = _create(con, "corporate_action", "SELECT * FROM _act_final ORDER BY security_id, ex_date, action", live,
                    rebuilt)
        # A cash dividend that went ex on or before its security's first served bar adjusts no served bar (the
        # factors move the bars before the ex-date, and there are none): the history's start, not a defect. It is
        # counted in the note and not named, so the few that are defects are not buried (review D6 of #420: 7,497
        # of homesrv's 7,514 were "no close before the ex-date"). The table still records it, unapplied.
        before_history = 0
        for aid, action, sid, why_, before in con.execute(UNAPPLIED_SQL).fetchall():
            if before:
                before_history += 1
                continue
            kind = "dividend_not_applied" if action == "cash_dividend" else "action_not_applied"
            found.append((kind, aid, f"{sid}: {why_}"))
        if before_history:
            named = sum(1 for k, _, _ in found if k == "dividend_not_applied")
            ctx.notes.append(f"dividend_not_applied: {named} named, {before_history} more that went ex on or before "
                             "its security's first served bar (it adjusts no served bar), not named")
        return n

    # ── Shares ────────────────────────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _shares(con: duckdb.DuckDBPyConnection, found: list, live: bool = False) -> int:
        # A cover class goes to the spine row of its trading symbol, else (no symbol, the filing's one class) to the
        # CIK's one Tier A row. Not to an ADR's: the cover counts the issuer's ordinary shares and the bar is the ADS
        # (one TSM ADS is five shares), so the count stays under ``class:`` and the ADR has no cover shares.
        # shortcut: an ADR gets no market cap from the store at all; once a source of its ADS ratio (or its ADS count)
        # is read, divide the ordinary count by the ratio and map it to the ADR's row.
        # A count of 0 (an unissued class) or dated after its filing (a typo, as ``_dei``) is no count (prices plan
        # 16 Nov 2026, P2: 71 zero covers, 4 dated after their filing), nor a cover_* issue.
        con.execute("""CREATE OR REPLACE TEMP TABLE _cover AS
            WITH one AS (SELECT cik, any_value(security_id) AS security_id, any_value(security_type) AS security_type
                         FROM stg_spine WHERE tier = 'A' GROUP BY cik HAVING count(*) = 1),
                 classes AS (SELECT accession, count(*) AS n FROM stg_sec_cover GROUP BY accession),
                 m AS (SELECT c.*, s.security_id AS by_symbol,
                              coalesce(s.security_id, CASE WHEN c.symbol IS NULL AND k.n = 1 THEN o.security_id END)
                                  AS spine_id,
                              CASE WHEN s.security_id IS NOT NULL THEN s.security_type
                                   WHEN c.symbol IS NULL AND k.n = 1 THEN o.security_type END AS spine_type
                       FROM (SELECT * FROM stg_sec_cover WHERE shares > 0
                                                        AND (filed IS NULL OR as_of IS NULL OR as_of <= filed)) c
                       JOIN classes k USING (accession)
                       LEFT JOIN stg_spine s ON s.cik = c.cik AND s.ticker = replace(upper(c.symbol), '.', '-')
                       LEFT JOIN one o ON o.cik = c.cik)
            SELECT *, CASE WHEN spine_id IS NOT NULL AND spine_type IS DISTINCT FROM 'adr' THEN spine_id
                           ELSE 'class:' || cik || ':' || coalesce(nullif(class_member, ''), 'common')
                      END AS security_id
            FROM m""")
        # The company facts history (13F plan decision L): the issuer's undimensioned cover count, so a single-class
        # issuer's only: the CIK's one Tier A row and not an ADR (as ``_cover``), no cover filing of the CIK with
        # two classes, and no day the facts give two counts for (a multi-class issuer's classes reported apart). A
        # day a cover row serves for the security stays the cover's; of one day's counts the newest filing's wins (a
        # 10-Q/A restating a count). Two counts of one day in one filing are a multi-class issuer's classes. A count
        # dated after its filing is a typo (measured 16 Nov 2026: 2033-10-31 in a 10-Q filed 2023-11-08, 76 of 37,992
        # values of 727 companies) and would be the "newest" count for years: left out.
        con.execute("""CREATE OR REPLACE TEMP TABLE _dei AS
            WITH one AS (SELECT cik, any_value(security_id) AS security_id, any_value(security_type) AS security_type,
                                any_value(ticker) AS ticker
                         FROM stg_spine WHERE tier = 'A' GROUP BY cik HAVING count(*) = 1),
                 multi AS (SELECT cik FROM stg_sec_cover GROUP BY cik, accession HAVING count(*) > 1
                           UNION SELECT cik FROM stg_sec_dei GROUP BY cik, accession, as_of
                                 HAVING count(DISTINCT shares) > 1)
            SELECT o.security_id, o.ticker, d.* FROM stg_sec_dei d JOIN one o USING (cik)
            WHERE o.security_type IS DISTINCT FROM 'adr' AND d.shares > 0 AND (d.filed IS NULL OR d.as_of <= d.filed)
              AND NOT EXISTS (SELECT 1 FROM multi m WHERE m.cik = d.cik)
              AND NOT EXISTS (SELECT 1 FROM _cover c WHERE c.security_id = o.security_id AND c.as_of = d.as_of)
            QUALIFY row_number() OVER (PARTITION BY d.cik, d.as_of
                                       ORDER BY d.filed DESC NULLS LAST, d.accession DESC) = 1""")
        n = _create(con, "shares_class", f"""
            SELECT c.security_id, 'outstanding' AS measure, c.as_of, c.shares AS value, c.symbol, c.cik,
                   nullif(c.class_member, '') AS class_member, '{COVER}' AS source, c.accession AS source_ref,
                   c.filed, c.source_as_of, c.fetched_at, c.run_id
            FROM _cover c
            UNION ALL
            SELECT d.security_id, 'outstanding', d.as_of, d.shares, d.ticker, d.cik, NULL, '{DEI}', d.accession,
                   d.filed, d.source_as_of, d.fetched_at, d.run_id
            FROM _dei d
            UNION ALL
            SELECT coalesce(s.security_id, y.security_id), 'float', y.source_as_of, y.float_shares, y.ticker, y.cik,
                   NULL, '{YAHOO}', NULL, NULL, y.source_as_of, y.fetched_at, y.run_id
            FROM stg_yahoo_float y LEFT JOIN stg_spine s ON s.ticker = y.ticker AND s.cik IS NOT DISTINCT FROM y.cik
            WHERE y.float_shares IS NOT NULL
            UNION ALL
            SELECT coalesce(s.security_id, t.security_id), 'float', t.source_as_of, t.float_shares, t.ticker, t.cik,
                   NULL, '{TV}', NULL, NULL, t.source_as_of, t.fetched_at, t.run_id
            FROM stg_tv_float t LEFT JOIN stg_spine s ON s.ticker = t.ticker AND s.cik IS NOT DISTINCT FROM t.cik
            WHERE t.float_shares IS NOT NULL""", live)
        for cik, symbol in con.execute(
                "SELECT DISTINCT cik, symbol FROM _cover WHERE symbol IS NOT NULL AND by_symbol IS NULL").fetchall():
            found.append(("cover_class_unmapped", f"{cik}:{symbol}", "no spine ticker of the CIK is this symbol"))
        # arg_max skips a fact with no date (its context had none): then the largest count.
        for sid, forms, shares in con.execute(
                "SELECT spine_id, string_agg(DISTINCT form, ', '), coalesce(arg_max(shares, as_of), max(shares)) "
                "FROM _cover WHERE spine_type = 'adr' GROUP BY spine_id ORDER BY 1").fetchall():
            found.append(("cover_adr_ordinary", sid, f"{forms} cover counts {shares:,.0f} ordinary shares, not the "
                                                     "ADSs: no market cap from it"))
        return n

    # ── The WRDS difference report ────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _wrds_report(con: duckdb.DuckDBPyConnection) -> int:
        """``wrds_price_diff``: one row per ``wrds_history.COMPARISONS`` entry (zero sessions when a side has none)."""
        con.execute(HRET_SQL)
        parts = _report_parts()
        as_of = ("(SELECT max(source_as_of) FROM (SELECT source_as_of FROM stg_wrds_secd "
                 "UNION ALL SELECT source_as_of FROM stg_wrds_dsf))")
        return _create(con, "wrds_price_diff",
                       f"SELECT comparison, {as_of} AS as_of, securities, sessions, close_differs, max_close_diff, "
                       "return_differs, max_return_diff, first_session, last_session FROM ("
                       + parts + ")")

    # ── Views ─────────────────────────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _views(con: duckdb.DuckDBPyConnection) -> None:
        built = "(SELECT max(built_at) FROM serving_schema_version)"
        con.execute("CREATE OR REPLACE VIEW security_symbol_now AS SELECT security_id, symbol FROM security_symbol "
                    "QUALIFY row_number() OVER (PARTITION BY security_id ORDER BY valid_to IS NULL DESC, "
                    "valid_from DESC NULLS LAST) = 1")
        con.execute(f"""CREATE OR REPLACE VIEW price_bars_daily AS
            SELECT n.symbol AS ticker, b.session_date, b.open * coalesce(a.split_factor, 1) AS open,
                   b.high * coalesce(a.split_factor, 1) AS high, b.low * coalesce(a.split_factor, 1) AS low,
                   b.close * coalesce(a.split_factor, 1) AS close, b.close * coalesce(a.tr_factor, 1) AS adj_close,
                   b.volume / coalesce(a.split_factor, 1) AS volume, CAST(NULL AS DOUBLE) AS split_ratio,
                   'prices/adj_factor' AS adj_source, b.source, {built} AS fetched_at, b.run_id, {built} AS run_at
            FROM price_bar_daily b JOIN security_symbol_now n USING (security_id)
            {factor_join('a', 'b.security_id', 'b.session_date')}
            WHERE b.security_id NOT LIKE 'index:%'""")
        con.execute(f"""CREATE OR REPLACE VIEW price_actions AS
            SELECT n.symbol AS ticker, c.ex_date, CASE WHEN c.action = 'cash_dividend' THEN 'dividend'
                   ELSE 'split' END AS action,
                   CASE WHEN c.action = 'cash_dividend' THEN c.amount * coalesce(a.split_factor, 1)
                        ELSE c.ratio END AS value,
                   c.ex_date AS session_date, c.source, {built} AS fetched_at, c.run_id, {built} AS run_at
            FROM corporate_action c JOIN security_symbol_now n USING (security_id)
            {factor_join('a', 'c.security_id', 'c.ex_date')}
            WHERE c.applied""")
        con.execute(f"""CREATE OR REPLACE VIEW index_levels_daily AS
            SELECT '^GSPC' AS symbol, session_date, open, high, low, close, volume, source, {built} AS fetched_at,
                   run_id, {built} AS run_at
            FROM price_bar_daily WHERE security_id = 'index:SPX'""")

    # ── Issues ────────────────────────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _issues(con: duckdb.DuckDBPyConnection, have: dict[str, int], live: bool = False,
                alpaca: list | None = None) -> list[tuple[str, str, str]]:
        found: list[tuple[str, str, str]] = []
        newest = con.execute(NEWEST_STOCK_SQL).fetchone()[0]
        if newest is not None:
            # The Tier A names the store keeps (review S1 of #382): an untyped or excluded Tier A name is left out of
            # the store on purpose, so its missing bar is no finding.
            tier_a = ("SELECT s.security_id, s.ticker FROM stg_spine s WHERE s.tier = 'A' "
                      "AND s.ticker IN (SELECT ticker FROM _universe_ticker) AND NOT EXISTS (SELECT 1 FROM {t} x "
                      "WHERE x.security_id = s.security_id AND x.session_date = ?{has}) ORDER BY s.security_id")
            for sid, ticker in con.execute(tier_a.format(t="price_bar_daily", has=""), [newest]).fetchall():
                found.append(("tier_a_no_bar", sid, f"{ticker}: no bar on {newest}"))
            adr = set(r[0] for r in con.execute("SELECT security_id FROM stg_spine WHERE security_type = 'adr' "
                                                "AND security_id IS NOT NULL").fetchall())
            bars_now = set(r[0] for r in con.execute(
                "SELECT security_id FROM price_bar_daily WHERE session_date = ?", [newest]).fetchall())
            # A row with no cap (an ADR's, a zero count's) is no market cap.
            for sid, ticker in con.execute(tier_a.format(t="market_cap_daily", has=" AND x.market_cap IS NOT NULL"),
                                           [newest]).fetchall():
                if sid not in adr:
                    found.append(("tier_a_no_shares", sid, f"{ticker}: no shares for {newest}"))
                elif sid in bars_now:
                    found.append(("adr_no_ratio", sid, f"{ticker}: an ADR, no ADS ratio read, so no market cap"))
            # A fund of the universe with no bar, by ticker: no spine id need exist (review M3 of #382).
            for (ticker,) in con.execute(
                    "SELECT u.ticker FROM _universe_etf u WHERE NOT EXISTS ("
                    "SELECT 1 FROM price_bar_daily b WHERE b.session_date = ? AND ({sym} = u.tic OR "
                    "b.security_id IN (SELECT s.security_id FROM stg_spine s WHERE {spine} = u.tic) OR "
                    "b.security_id IN (SELECT gid FROM _etf_tic_series e WHERE e.tic = u.tic AND e.pick = 1))) "
                    "ORDER BY 1".format(sym=universe.norm("b.symbol"), spine=universe.norm("s.ticker")),
                    [newest]).fetchall():
                found.append(("universe_etf_no_bar", ticker, f"{ticker}: no bar on {newest}"))
        # Two series on one fund ticker: one is stored, the rest named (review D1 of #420).
        for tic, picked, n, names in con.execute(
                "SELECT tic, arg_min(gid, pick), count(*), string_agg(gid, ', ' ORDER BY pick) FROM _etf_tic_series "
                "GROUP BY tic HAVING count(*) > 1 ORDER BY tic").fetchall():
            found.append(("universe_etf_ticker_shared", tic, f"{tic}: {n} recent Compustat series carry the "
                          f"ticker ({names}); stored {picked}, the one priced most recently, then the larger dollar "
                          "volume"))
        con.execute(f"""CREATE OR REPLACE TEMP TABLE _ret AS
            SELECT b.security_id, b.session_date, b.close * coalesce(a.split_factor, 1) AS split_close,
                   b.close * coalesce(a.tr_factor, 1) AS tr_close, b.source,
                   lag(b.session_date) OVER w AS prev_day,
                   lag(b.close * coalesce(a.split_factor, 1)) OVER w AS prev_split,
                   lag(b.close * coalesce(a.tr_factor, 1)) OVER w AS prev_tr
            FROM price_bar_daily b {factor_join('a', 'b.security_id', 'b.session_date')}
            WHERE b.security_id NOT LIKE 'index:%' AND b.close > 0
            WINDOW w AS (PARTITION BY b.security_id ORDER BY b.session_date)""")
        for sid, day, ratio, kind in con.execute(f"""
                SELECT r.security_id, r.session_date, r.split_close / r.prev_split,
                       CASE WHEN t.security_type IN ('warrant', 'unit') THEN 'price_gap_warrant'
                            ELSE 'price_gap_no_action' END
                FROM _ret r LEFT JOIN (SELECT security_id, any_value(security_type) AS security_type FROM stg_spine
                                       WHERE security_id IS NOT NULL GROUP BY 1) t USING (security_id)
                WHERE r.prev_split > 0 AND date_diff('day', r.prev_day, r.session_date) <= {GAP_DAYS}
                  AND abs(ln(r.split_close / r.prev_split)) >= ln({GAP_FACTOR})
                  AND NOT EXISTS (SELECT 1 FROM corporate_action c WHERE c.security_id = r.security_id
                                  AND c.action IN ('split', 'stock_dividend') AND c.ex_date > r.prev_day
                                  AND c.ex_date <= r.session_date)
                  -- a split only CRSP records explains the gap: it is the split_only_crsp (or, applied,
                  -- split_applied_crsp) issue instead
                  AND NOT EXISTS (SELECT 1 FROM _crsp_only_split c WHERE c.security_id = r.security_id
                                  AND c.ex_date > r.prev_day AND c.ex_date <= r.session_date)
                  {f"AND {incremental.where(f'r.session_date + INTERVAL {SPLIT_SAME_DAYS} DAY', 'r.security_id')}"
                   if live else ""}
                ORDER BY 1, 2""").fetchall():
            found.append((kind, f"{sid}:{day}", f"split-adjusted close x{ratio:.3f}, no split"))
        found += split_ratio_unexplained(con, live)
        # Alpaca's previous adjusted close is close_all / (1 + all_return). The allowance is its exact rounding
        # bound, a hair wider (1e-6 of it) for the float error of a row that sits on it; none at a previous close of
        # half a cent or less, where the bound has no meaning and the flat 1 bp stays.
        prev = "a.close_all / nullif(1 + a.all_return, 0)"
        allowance = (f"CASE WHEN {prev} > {HALF_CENT} THEN {HALF_CENT} * (a.close_all + {prev}) "
                     f"/ ({prev} * ({prev} - {HALF_CENT})) * (1 + 1e-6) ELSE 0 END")
        for sid, day, ours, theirs in con.execute(f"""
                SELECT r.security_id, r.session_date, r.tr_close / r.prev_tr - 1, a.all_return
                FROM _ret r JOIN _alp a ON a.security_id = r.security_id AND a.session_date = r.session_date
                WHERE r.prev_tr > 0 AND a.all_return IS NOT NULL
                  AND date_diff('day', r.prev_day, r.session_date) <= 5
                  AND abs((r.tr_close / r.prev_tr - 1) - a.all_return) > greatest({TOLERANCE}, {allowance})
                ORDER BY 1, 2""").fetchall():
            found.append(("adjustment_differs", f"{sid}:{day}", f"ours {ours:.6f}, alpaca {theirs:.6f}"))
        # The tester's close check: every history bar of a session Alpaca has, either source (a chunked build found
        # them chunk by chunk, ``Chunked.report``).
        found += alpaca_differs(con, live) if alpaca is None else alpaca
        newest_of = ("SELECT security_id, value FROM shares_class WHERE measure = '{m}' AND source = '{s}' "
                     "QUALIFY row_number() OVER (PARTITION BY security_id ORDER BY as_of DESC, fetched_at DESC) = 1")
        for sid, fl, out in con.execute(f"""
                WITH f AS ({newest_of.format(m='float', s=YAHOO)} UNION ALL {newest_of.format(m='float', s=TV)}),
                     o AS (SELECT o.security_id, o.value * coalesce(a2.split_factor, 1)
                                  / coalesce(a1.split_factor, 1) AS value
                           FROM (SELECT * FROM shares_class WHERE measure = 'outstanding'
                                 QUALIFY row_number() OVER (PARTITION BY security_id ORDER BY as_of DESC) = 1) o
                           {factor_join('a1', 'o.security_id', 'o.as_of')}
                           -- No period has a NULL ``valid_to`` (``ADJ_SQL``), so a2 is always empty: factor 1, the
                           -- newest basis being the stored one.
                           LEFT JOIN adj_factor a2 ON {period('a2', 'o.security_id', "DATE '9999-12-31'")})
                SELECT f.security_id, max(f.value), any_value(o.value) FROM f JOIN o USING (security_id)
                GROUP BY f.security_id HAVING max(f.value) > {FLOAT_OVER} * any_value(o.value) ORDER BY 1""").fetchall():
            found.append(("float_above_outstanding", sid, f"float {fl:,.0f} over outstanding {out:,.0f}"))
        for sid, y, u in con.execute(f"""
                SELECT y.security_id, y.value, t.value FROM ({newest_of.format(m='float', s=YAHOO)}) y
                JOIN ({newest_of.format(m='float', s=TV)}) t USING (security_id)
                WHERE abs(y.value - t.value) > {FLOAT_DISAGREE} * greatest(y.value, t.value) ORDER BY 1""").fetchall():
            found.append(("float_sources_disagree", sid, f"yahoo {y:,.0f}, tradingview {u:,.0f}"))
        # shortcut: flagged only, the cap stays; if avo wants it, withhold a cover cap beyond a factor of two from
        # Yahoo (the universe then falls back as for a name with no shares).
        for sid, cover, as_of, yahoo, day in con.execute(f"""
                WITH y AS (SELECT coalesce(s.security_id, y.security_id) AS security_id,
                                  y.shares_outstanding AS yahoo, y.source_as_of
                           FROM stg_yahoo_float y
                           LEFT JOIN stg_spine s ON s.ticker = y.ticker AND s.cik IS NOT DISTINCT FROM y.cik
                           WHERE y.shares_outstanding > 0
                           QUALIFY row_number() OVER (PARTITION BY coalesce(s.security_id, y.security_id)
                                                      ORDER BY y.source_as_of DESC, y.fetched_at DESC) = 1)
                SELECT y.security_id, m.shares, m.shares_as_of, y.yahoo, m.session_date
                FROM y ASOF JOIN (SELECT * FROM market_cap_daily WHERE shares_source IN ('{COVER}', '{DEI}')) m
                    ON m.security_id = y.security_id AND y.source_as_of >= m.session_date
                WHERE abs(m.shares - y.yahoo) > {SHARES_DISAGREE} * greatest(m.shares, y.yahoo)
                ORDER BY 1""").fetchall():
            found.append(("shares_disagree_yahoo", sid, f"cover {cover:,.0f} (as of {as_of}, moved over the splits "
                                                        f"since), yahoo {yahoo:,.0f} on {day}"))
        return found

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        cols = ["security_id", "session_date", "open", "high", "low", "close", "volume", "source"]
        # On the live copy only the rebuilt rows can differ from the live file's.
        added, removed = stage.compare_live(con, "price_bar_daily", cols,
                                            incremental.where("session_date") if incremental.active(ctx) else "")
        newest = con.execute(NEWEST_STOCK_SQL).fetchone()[0]
        n_issues = len(ctx.pending.get(NAME, []))
        ctx.notes.append(f"{n_issues} build issues found")
        return {"dataset": NAME, "result": "changed" if added or removed else "unchanged",
                "source_as_of": (newest or ctx.as_of or self.default_as_of()).isoformat(),
                "rows": stage.count(con, "price_bar_daily"), "added": added, "removed": removed, "coverage": None}

    def after_swap(self, ctx: base.RunContext) -> None:
        found = ctx.pending.get(NAME)
        if found is None:
            return
        sc = ctx.pending.get(NAME + ":scope")
        ops.sync_issues(NAME, ISSUE_KINDS, found, run_id=ctx.run_id, keep=sc.keep if sc is not None else None)


ADJ_SQL = f"""
    WITH ev AS (
        SELECT security_id, ex_date,
               product(CASE WHEN action = 'cash_dividend' THEN 1.0 ELSE 1.0 / ratio END) AS split_mult,
               product(CASE WHEN action = 'cash_dividend' THEN 1.0 - amount / close_before ELSE 1.0 / ratio END)
                   AS tr_mult,
               count(*) AS n
        FROM _act_final WHERE applied AND action IN {APPLIED} GROUP BY ALL)
    SELECT security_id, lag(ex_date) OVER (PARTITION BY security_id ORDER BY ex_date) AS valid_from,
           ex_date AS valid_to,
           product(split_mult) OVER (PARTITION BY security_id ORDER BY ex_date DESC
                                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS split_factor,
           product(tr_mult) OVER (PARTITION BY security_id ORDER BY ex_date DESC
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS tr_factor,
           CAST(n AS INTEGER) AS events
    FROM ev ORDER BY security_id, ex_date"""

# The symbols of the served bars, and of a history bar on a session whose winner has none (#363): CRSP's bar carries no
# symbol (a delisted PERMNO's ticker can be another listing's today), so a Compustat-only name whose sessions CRSP all
# wins keeps Compustat's ``tic``. Not on a session Alpaca won: Compustat writes the current ``tic`` on every past day,
# which would pull a new ticker's start back in time (review of #364).
SYMBOL_SQL = """
    WITH b AS (SELECT security_id, symbol, cik, session_date, source FROM price_bar_daily
               UNION ALL SELECT h.security_id, h.symbol, h.cik, h.session_date, h.source FROM _hist_all h
               WHERE NOT EXISTS (SELECT 1 FROM price_bar_daily w WHERE w.security_id = h.security_id
                                 AND w.session_date = h.session_date AND w.symbol IS NOT NULL)),
    p AS (SELECT security_id, symbol, any_value(cik) AS cik, min(session_date) AS lo,
                 arg_max(source, session_date) AS source
          FROM b WHERE symbol IS NOT NULL AND security_id NOT LIKE 'index:%' GROUP BY ALL)
    SELECT security_id, symbol, cik, lo AS valid_from,
           lead(lo) OVER (PARTITION BY security_id ORDER BY lo) AS valid_to, source FROM p
    UNION ALL
    SELECT security_id, ticker, cik, NULL, NULL, 'spine/security' FROM stg_spine
    WHERE tier = 'A' AND security_id NOT IN (SELECT security_id FROM p)"""

# The issuer CIK of each security a cap is computed for: the spine's, and a Compustat class the spine lacks (BRK-A)
# is its issuer's through the gvkey of the classes it holds.
ISSUER_SQL = """
    WITH gv AS (SELECT gvkey, any_value(cik) AS cik FROM stg_spine WHERE nullif(gvkey, '') IS NOT NULL
                AND cik IS NOT NULL GROUP BY gvkey HAVING count(DISTINCT cik) = 1)
    SELECT DISTINCT security_id, cik FROM stg_spine
    UNION ALL
    SELECT DISTINCT d.gvkey || ':' || d.iid, gv.cik FROM stg_wrds_secd d JOIN gv USING (gvkey)
    WHERE d.gvkey || ':' || d.iid NOT IN (SELECT security_id FROM stg_spine WHERE security_id IS NOT NULL)"""

MARKET_CAP_SQL = f"""
    WITH o AS (SELECT security_id, as_of, value, source FROM shares_class WHERE measure = 'outstanding'
               QUALIFY row_number() OVER (PARTITION BY security_id, as_of ORDER BY fetched_at DESC) = 1),
         -- The lowest-priority servable history bar with shares, per session: one hash aggregate (#372's rule).
         h AS (SELECT security_id, session_date,
                      arg_min(shares_outstanding, row(priority, series)) AS shares_outstanding,
                      arg_min(source, row(priority, series)) AS source FROM _hist_all
               WHERE shares_outstanding > 0 AND {HIST_SERVED} GROUP BY security_id, session_date),
         sec AS ({ISSUER_SQL}),
         b AS (SELECT b.*, coalesce(s.cik, b.cik) AS issuer, h.shares_outstanding AS hist_shares,
                      h.source AS hist_source FROM price_bar_daily b
               LEFT JOIN sec s USING (security_id)
               LEFT JOIN h ON h.security_id = b.security_id AND h.session_date = b.session_date
               WHERE b.security_id NOT LIKE 'index:%' AND b.close IS NOT NULL /*near*/),
         -- The bar's own shares, else a WRDS source's of that session (an Alpaca bar Compustat also has), else the
         -- newest cover on or before the session.
         -- A bar's own count of 0 (a SPAC unit's Compustat ``cshoc``) or below is none, as in ``h``.
         j AS (SELECT b.security_id, b.session_date, b.issuer, b.close,
                      CASE WHEN b.shares_outstanding > 0 THEN b.shares_outstanding ELSE b.hist_shares END AS own,
                      CASE WHEN b.shares_outstanding > 0 THEN b.source ELSE b.hist_source END AS bar_source,
                      coalesce(b.shares_outstanding <= 0, false) AS zero_count,
                      o.value AS cover, o.as_of AS cover_as_of, o.source AS cover_source
               FROM b ASOF LEFT JOIN o ON o.security_id = b.security_id AND b.session_date >= o.as_of),
         -- A company facts count older than DEI_MAX_AGE_DAYS gives no cap: its issuer may have stopped tagging it
         -- undimensioned (a second class), so it is not taken as today's.
         s AS (SELECT j.*, CASE WHEN own IS NOT NULL THEN own
                                WHEN cover_source = '{DEI}'
                                     AND date_diff('day', cover_as_of, session_date) > {DEI_MAX_AGE_DAYS} THEN NULL
                                ELSE cover * coalesce(a1.split_factor, 1) / coalesce(a2.split_factor, 1) END AS shares
               FROM j {factor_join('a1', 'j.security_id', 'j.session_date')}
               {factor_join('a2', 'j.security_id', 'j.cover_as_of')}),
         -- No cap for an ADR (#711): Compustat's count, as the cover's, is the issuer's ordinary shares and the
         -- close is the ADS's. shortcut: until an ADS ratio is read; then divide instead (``adr_no_ratio``).
         -- A bar whose own count is 0 and that no other count serves has no cap either (``zero_count``). Both keep
         -- their row, cap and shares NULL and the reason in ``shares_source``: the store narrows nothing (S18).
         a AS (SELECT s.*, s.security_id IN (SELECT security_id FROM stg_spine
                                             WHERE security_type = 'adr' AND security_id IS NOT NULL) AS adr
               FROM s WHERE shares IS NOT NULL OR zero_count),
         c AS (SELECT security_id, session_date, issuer AS cik, close,
                      CASE WHEN NOT adr THEN shares END AS shares,
                      CASE WHEN adr THEN 'adr_no_ratio' WHEN shares IS NULL THEN 'zero_count'
                           WHEN own IS NOT NULL THEN bar_source ELSE cover_source END AS shares_source,
                      CASE WHEN adr OR shares IS NULL THEN NULL
                           WHEN own IS NOT NULL THEN session_date ELSE cover_as_of END AS shares_as_of,
                      CASE WHEN NOT adr THEN close * shares END AS market_cap, coalesce(issuer, security_id) AS iss
               FROM a),
         -- Each class of the issuer at its newest cap on or before the session, if at most ISSUER_WITHIN_DAYS old:
         -- a class with no bar that day (GOOG on a day GOOGL traded) still counts; a row with no cap is none.
         -- ``k`` carries the first and last session each class has a cap for, so a class is joined only to the
         -- sessions where its newest cap can still be in the window (#1144): a class that last priced in 2015 was
         -- otherwise joined to every 2026 session of its siblings, carried through the ASOF join and only then
         -- dropped by ``i``'s filter. Dropping it before the join is the same answer by construction, because the
         -- ASOF join finds nothing before ``lo`` and ``i`` keeps nothing after ``hi`` + the window.
         k AS (SELECT iss, security_id AS cls, min(session_date) AS lo, max(session_date) AS hi
               FROM c WHERE market_cap IS NOT NULL GROUP BY ALL),
         g AS (SELECT c.security_id, c.session_date, k.cls FROM c JOIN k USING (iss)
               WHERE c.session_date >= k.lo
                 AND c.session_date <= k.hi + INTERVAL {{within}} DAY),
         p AS (SELECT g.security_id, g.session_date, x.market_cap, x.session_date AS cap_day
               FROM g ASOF LEFT JOIN (SELECT * FROM c WHERE market_cap IS NOT NULL) x
                    ON x.security_id = g.cls AND g.session_date >= x.session_date),
         i AS (SELECT security_id, session_date,
                      sum(market_cap) FILTER (WHERE date_diff('day', cap_day, session_date) <= {{within}})
                          AS issuer_market_cap
               FROM p GROUP BY ALL)
    -- LEFT JOIN, not JOIN: ``k`` now holds only the classes with a cap, so an issuer with none has no ``i`` row.
    -- On the old ``k`` every row's own class was in it, so the inner join dropped nothing; this keeps that true
    -- (the store narrows nothing, S18) and leaves ``issuer_market_cap`` NULL, which is what the filter's empty
    -- sum gave before.
    SELECT c.*, i.issuer_market_cap FROM c LEFT JOIN i USING (security_id, session_date)"""

REVISION_SQL = f"""
    SELECT coalesce(s.security_id, r.security_id) AS security_id, r.session_date, r.ticker AS symbol, r.open, r.high,
           r.low, r.close, r.volume, '{ALPACA_BARS}' AS source, r.fetched_at, r.run_id, r.revised_at, r.revised_by
    FROM stg_alpaca_bar_revisions r LEFT JOIN stg_spine s ON s.ticker = r.ticker AND s.cik IS NOT DISTINCT FROM r.cik"""


# The served history bars: one per session of a ``_hist_all`` security, Compustat's (priority 1) before CRSP's.
HIST_BARS = (f"SELECT {', '.join(c for c, _ in PRICE_BAR)} FROM (SELECT * FROM _hist_all h "
             f"WHERE {HIST_FIRST.format(where='WHERE ' + HIST_SERVED)})")


def _hist_counts(con: duckdb.DuckDBPyConnection) -> tuple[list[int], dict[str, int]]:
    """Over ``_secd_listed`` and ``_hist_all``: the rows and securities the dated exchange rule lists that today's code
    would not and the reverse, and Compustat's day returns per rule (the build's notes)."""
    moved = con.execute("SELECT count(*) FILTER (WHERE listed AND NOT listed_today), count(DISTINCT gvkey || iid) "
                        "FILTER (WHERE listed AND NOT listed_today), count(*) FILTER (WHERE listed_today AND NOT "
                        "listed), count(DISTINCT gvkey || iid) FILTER (WHERE listed_today AND NOT listed) "
                        f"FROM _secd_listed WHERE {secd.PRICED_USD} "
                        "AND datadate <= getvariable('rc_build_date')").fetchone()
    basis = con.execute(f"SELECT return_basis, count(*) FROM _hist_all WHERE source = '{wrds_history.COMPUSTAT}' "
                        "AND return_basis IS NOT NULL GROUP BY ALL").fetchall()
    return [int(n) for n in moved], {b: int(n) for b, n in basis}


# Each WRDS source's own day return against the store's (its closes, the store's factors), for the difference report.
HRET_SQL = f"""CREATE OR REPLACE TEMP TABLE _hret AS
    WITH d AS (SELECT security_id, ex_date, sum(amount) AS amount FROM corporate_action
               WHERE applied AND action = 'cash_dividend' GROUP BY ALL),
    x AS (SELECT h.source, h.security_id, h.series, h.session_date, h.own_return, h.return_basis,
                 h.close * coalesce(a.split_factor, 1) AS sc,
                 coalesce(d.amount, 0) * coalesce(a.split_factor, 1) AS dv
          FROM _hist_all h {factor_join('a', 'h.security_id', 'h.session_date')}
          LEFT JOIN d ON d.security_id = h.security_id AND d.ex_date = h.session_date WHERE h.close > 0),
    y AS (SELECT *, lag(sc) OVER w AS prev_sc, lag(session_date) OVER w AS prev_day FROM x
          -- per series: two series of one aliased fund price the same sessions, and each return is its own series'
          -- (review F3 of #654: otherwise which one is the previous row depends on the row order)
          WINDOW w AS (PARTITION BY source, security_id, series ORDER BY session_date))
    -- The economic day return: the close plus the dividend over the previous close, in one share basis.
    SELECT source, security_id, session_date, own_return, return_basis, (sc + dv) / prev_sc - 1 AS ours FROM y
    WHERE prev_sc > 0 AND own_return IS NOT NULL AND date_diff('day', prev_day, session_date) <= 7"""


def _report_parts() -> str:
    """One row per ``wrds_history.COMPARISONS`` entry over ``_hist_all``, ``_hret`` and ``_alp`` (zero sessions when a
    side has none), without ``as_of``: the difference report's counts."""
    side = {"crsp": f"SELECT security_id, session_date, close FROM _hist_all WHERE source = '{wrds_history.CRSP}'",
            "compustat": ("SELECT security_id, session_date, close FROM _hist_all "
                          f"WHERE source = '{wrds_history.COMPUSTAT}'"),
            "alpaca": "SELECT security_id, session_date, close FROM _alp"}
    pair = ("SELECT '{name}' AS comparison, count(DISTINCT x.security_id) AS securities, count(*) AS sessions, "
            f"count(*) FILTER (WHERE abs(x.close - y.close) > greatest({TOLERANCE} * y.close, {HALF_CENT})) "
            "AS close_differs, "
            "max(abs(x.close - y.close) / y.close) AS max_close_diff, CAST(NULL AS INTEGER) AS return_differs, "
            "CAST(NULL AS DOUBLE) AS max_return_diff, min(x.session_date) AS first_session, "
            "max(x.session_date) AS last_session "
            "FROM ({x}) x JOIN ({y}) y USING (security_id, session_date) WHERE y.close > 0")
    own = ("SELECT '{name}', count(DISTINCT security_id), count(*), CAST(NULL AS INTEGER), CAST(NULL AS DOUBLE), "
           f"count(*) FILTER (WHERE abs(ours - own_return) > {TOLERANCE}), max(abs(ours - own_return)), "
           "min(session_date), max(session_date) FROM _hret WHERE source = '{source}' AND {basis}")
    parts = []
    for name in wrds_history.COMPARISONS:
        if name.endswith("_returns"):
            source = wrds_history.CRSP if name.startswith("crsp") else wrds_history.COMPUSTAT
            parts.append(own.format(name=name, source=source, basis="true"))
        else:
            x, y = name.split("_vs_")
            parts.append(pair.format(name=name, x=side[x], y=side[y]))
    return " UNION ALL ".join(parts)


def split_ratio_unexplained(con: duckdb.DuckDBPyConnection, live: bool = False) -> list[tuple[str, str, str]]:
    """``split_ratio_unexplained`` over the served ``corporate_action`` and the raw closes of ``price_bar_daily``.

    An applied split carries its ratio; the raw close of the last served bar before its ex-date and of the first on
    or after it step by that ratio (``close_after / close_before`` is 1/ratio), apart from the day's own return. A
    pair SPLIT_MOVE_FACTOR or more away from that is named. A span with a second applied split in it is left alone:
    the move there is the product of the two ratios, so this rule has nothing to say about either one.
    """
    con.execute(f"""CREATE OR REPLACE TEMP TABLE _split_span AS
        WITH s AS (SELECT security_id, ex_date, ratio FROM corporate_action
                   WHERE action IN ('split', 'stock_dividend') AND applied AND ratio > 0 AND ex_date IS NOT NULL),
             b AS (SELECT security_id, session_date, close FROM price_bar_daily WHERE close > 0)
        SELECT s.*, p.session_date AS day_before, p.close AS close_before,
               n.session_date AS day_after, n.close AS close_after,
               (SELECT count(*) FROM s o WHERE o.security_id = s.security_id
                AND o.ex_date > p.session_date AND o.ex_date <= n.session_date) AS splits_in_span
        FROM s
        ASOF LEFT JOIN b p ON p.security_id = s.security_id AND s.ex_date > p.session_date
        ASOF LEFT JOIN b n ON n.security_id = s.security_id AND s.ex_date <= n.session_date
        WHERE p.session_date IS NOT NULL AND n.session_date IS NOT NULL
          AND date_diff('day', p.session_date, n.session_date) <= {GAP_DAYS}""")
    return [("split_ratio_unexplained", f"{sid}:{day}",
             f"ratio {ratio:.4f} expects the raw close to move x{1 / ratio:.4f}; it moved x{move:.4f} "
             f"from {before:.4f} on {day_before} to {after:.4f} on {day_after}: named, not dropped")
            for sid, day, ratio, move, before, after, day_before, day_after in con.execute(f"""
                SELECT security_id, ex_date, ratio, close_after / close_before, close_before, close_after,
                       day_before, day_after
                FROM _split_span
                WHERE splits_in_span = 1
                  AND abs(ln(close_after / close_before * ratio)) >= ln({SPLIT_MOVE_FACTOR})
                  {f"AND {incremental.where('ex_date', 'security_id')}" if live else ""}
                ORDER BY 1, 2""").fetchall()]


def alpaca_differs(con: duckdb.DuckDBPyConnection, live: bool = False) -> list[tuple[str, str, str]]:
    """``alpaca_close_differs``: every ``_hist_all`` bar of a session Alpaca has, either source, whose close differs."""
    return [("alpaca_close_differs", f"{sid}:{day}:{source}", f"{source.split('/')[-1]} {close:.4f}, alpaca {alp:.4f}")
            for sid, day, source, close, alp in con.execute(f"""
                SELECT h.security_id, h.session_date, h.source, h.close, a.close FROM _hist_all h
                JOIN _alp a ON a.security_id = h.security_id AND a.session_date = h.session_date
                WHERE a.close > 0 AND abs(h.close - a.close) > greatest({TOLERANCE} * a.close, {HALF_CENT})
                  {f"AND {incremental.where('h.session_date', 'h.security_id')}" if live else ""}
                ORDER BY 1, 2, 3""").fetchall()]


def _append(con: duckdb.DuckDBPyConnection, table: str, select: str) -> None:
    names = ", ".join(f'"{c}"' for c, _ in SCHEMAS[table])
    con.execute(f"INSERT INTO {table} ({names}) SELECT {names} FROM ({select})")


def _lit(value: str) -> str:
    """A SQL string literal of a security id or gvkey (a chunk's bound)."""
    return "'" + value.replace("'", "''") + "'"


def _spill(con: duckdb.DuckDBPyConnection) -> int:
    return int(con.execute("SELECT coalesce(sum(size), 0) FROM duckdb_temporary_files()").fetchone()[0])


class Chunked:
    """A whole build of the WRDS history in chunks of securities (#654; review of 10 Nov 2026, F1-F4).

    The identity stays whole and is built first, over the WRDS years read through views (``wrds_history.build``):
    ``_universe``, ``_permno_link``, ``_gvkey_alias``, the ETF series. A chunk is one contiguous range of
    ``_universe``'s security ids (``_bucket``): the Compustat series it reads (``_bgid``: its own ``gvkey:iid`` ids,
    and the series aliased to one of its ids, never a series aliased to another chunk's) and the PERMNOs linked to it
    (``_bpermno``) are staged as TEMP tables under the staging names, ``_secd_listed`` and ``_hist_all`` are made from
    them, and every row is cut to the chunk's securities. Every history computation is per security, so a chunk
    computes exactly its securities' rows; what spans securities is whole: the issuer cap (looped by issuer instead,
    ``caps``), the factors, the symbols and the issues, which read the served tables.

    Two passes over the chunks: ``bars`` (the bars, the WRDS actions, and the few history rows the symbols and the
    caps still need, kept as a narrow ``_hist_all``), and ``report`` (the difference report and the Alpaca close
    check, which need the factors that only the whole actions give)."""

    def __init__(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection, n: int):
        self.ctx, self.con, self.n = ctx, con, n
        ids = [r[0] for r in con.execute("SELECT DISTINCT security_id FROM _universe WHERE security_id IS NOT NULL "
                                         "ORDER BY security_id").fetchall()]
        # shortcut: equal counts of securities, not of rows; weigh by rows if the step log shows one chunk spilling
        # far more than the others.
        size = max(1, -(-len(ids) // n))
        self.ranges = [(ids[i], ids[min(i + size, len(ids)) - 1]) for i in range(0, len(ids), size)] or [("", "")]
        self.log: list[str] = []

    def _stage(self, lo: str, hi: str) -> None:
        con, w = self.con, wrds_history
        con.execute("CREATE OR REPLACE TEMP TABLE _bucket AS SELECT DISTINCT security_id FROM _universe "
                    f"WHERE security_id BETWEEN {_lit(lo)} AND {_lit(hi)}")
        con.execute("""CREATE OR REPLACE TEMP TABLE _bgid AS
            SELECT security_id AS gid FROM _bucket WHERE security_id NOT IN (SELECT gid FROM _gvkey_alias)
            UNION SELECT gid FROM _gvkey_alias WHERE security_id IN (SELECT security_id FROM _bucket)""")
        con.execute("""CREATE OR REPLACE TEMP TABLE _bpermno AS
            SELECT permno FROM _permno_link WHERE security_id IN (SELECT security_id FROM _bucket)
            UNION SELECT substr(security_id, 8) FROM _bucket WHERE security_id LIKE 'permno:%'""")
        not_gvkey = ", ".join(f"'{p}'" for p in incremental.NOT_GVKEY)
        glo, ghi = con.execute(f"SELECT min(split_part(gid, ':', 1)), max(split_part(gid, ':', 1)) FROM _bgid "
                               f"WHERE split_part(gid, ':', 1) NOT IN ({not_gvkey})").fetchone()
        # The range lets the Parquet reader skip the row groups of other gvkeys (the files are sorted by gvkey).
        series = ("false" if glo is None else
                  f"gvkey BETWEEN {_lit(glo)} AND {_lit(ghi)} AND gvkey || ':' || iid IN (SELECT gid FROM _bgid)")
        for table, where in (("secd", series), ("sec_divid", series),
                             ("dsf", "permno IN (SELECT permno FROM _bpermno)")):
            name = w.STAGING[table]
            con.execute(f"CREATE OR REPLACE TEMP TABLE {name} AS SELECT * FROM {name}{incremental.WHOLE} WHERE {where}")
        con.execute(BUILD_HIST_SQL.format(crsp=w.CRSP_BARS, comp=w.COMP_BARS, listed=w.SECD_LISTED, yahoo=YAHOO_BARS))
        # A PERMNO linked to two securities is staged in both chunks: each keeps only its own.
        con.execute("DELETE FROM _hist_all WHERE security_id NOT IN (SELECT security_id FROM _bucket)")

    def _passes(self, what: str, step) -> None:
        """Run ``step(lo, hi)`` after staging each chunk, the staging names being TEMP tables meanwhile; then the
        whole-history views again (the report's ``as_of``, ``wrds/prices``' check)."""
        import time
        con = self.con
        names = [wrds_history.STAGING[t] for t in wrds_history.YEARLY]
        for name in names:
            con.execute(f"DROP VIEW {name}")
        start, peak, at = time.monotonic(), 0, 0
        for i, (lo, hi) in enumerate(self.ranges):
            self._stage(lo, hi)
            step(lo, hi)
            spill = _spill(con)
            if spill > peak:
                peak, at = spill, i + 1
        for name in names:
            con.execute(f"DROP TABLE IF EXISTS {name}")
            con.execute(f"CREATE OR REPLACE TEMP VIEW {name} AS SELECT * FROM {name}{incremental.WHOLE}")
        self.log.append(f"{what} {time.monotonic() - start:.0f} s, peak spill {peak / 1e9:.1f} GB (chunk {at})")

    def bars(self, serving) -> tuple[int, list[int], dict[str, int]]:
        """Pass 1: ``price_bar_daily`` (the index bars, then each chunk's), the WRDS actions, the notes' counts."""
        con = self.con
        _create(con, "price_bar_daily", _index_levels(con))
        con.execute(f"CREATE OR REPLACE TEMP TABLE _crsp_split_near AS SELECT w.* FROM ({wrds_history.CRSP_SPLITS}) w "
                    "WHERE false")
        moved, basis = [0, 0, 0, 0], {}

        def step(lo: str, hi: str) -> None:
            _append(con, "price_bar_daily", HIST_BARS)
            m, b = _hist_counts(con)
            moved[:] = [x + y for x, y in zip(moved, m)]
            for k, v in b.items():
                basis[k] = basis.get(k, 0) + v
            serving._wrds_actions(con, chunk=True)
            # What the symbols (a history symbol on a session whose bar has none) and the caps (a session's shares when
            # its bar has none) read of the history after the passes: a few rows, so ``_hist_all`` stays narrow.
            keep = f"""SELECT h.* FROM _hist_all h
                       LEFT JOIN (SELECT security_id, session_date, shares_outstanding, symbol FROM price_bar_daily
                                  WHERE security_id BETWEEN {_lit(lo)} AND {_lit(hi)}) w USING (security_id, session_date)
                       WHERE (h.shares_outstanding > 0 AND {HIST_SERVED} AND w.shares_outstanding IS NULL)
                          OR (h.symbol IS NOT NULL AND w.symbol IS NULL)"""
            if con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = '_hist_keep'").fetchone()[0]:
                con.execute(f"INSERT INTO _hist_keep {keep}")
            else:
                con.execute(f"CREATE TEMP TABLE _hist_keep AS {keep}")

        self._passes("bars", step)
        con.execute("DROP TABLE IF EXISTS _secd_listed")
        con.execute("DROP TABLE _hist_all")
        con.execute("ALTER TABLE _hist_keep RENAME TO _hist_all")
        return stage.count(con, "price_bar_daily"), moved, basis

    def caps(self) -> int:
        """``market_cap_daily`` from the served tables, one issuer bucket at a time (review F2): an issuer's classes
        always share a bucket, so its cap counts each of them."""
        import time
        con, n = self.con, self.n
        start = time.monotonic()
        con.execute(f"CREATE OR REPLACE TEMP TABLE _issuer AS {ISSUER_SQL}")
        sql = MARKET_CAP_SQL.format(within=ISSUER_WITHIN_DAYS).replace(ISSUER_SQL, "SELECT * FROM _issuer")
        _create(con, "market_cap_daily", sql.replace("/*near*/", "AND false"))
        peak = 0
        for k in range(n):
            _append(con, "market_cap_daily",
                    sql.replace("/*near*/", f"AND hash(coalesce(s.cik, b.cik, b.security_id)) % {n} = {k}"))
            peak = max(peak, _spill(con))
        self.log.append(f"market cap {time.monotonic() - start:.0f} s, peak spill {peak / 1e9:.1f} GB")
        return stage.count(con, "market_cap_daily")

    def report(self) -> tuple[int, list[tuple[str, str, str]]]:
        """Pass 2: the difference report, summed over the chunks (their securities do not overlap), and the Alpaca
        close check, chunk by chunk."""
        con = self.con
        alpaca: list[tuple[str, str, str]] = []
        parts = _report_parts()

        def step(lo: str, hi: str) -> None:
            con.execute(HRET_SQL)
            if con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = '_report_part'").fetchone()[0]:
                con.execute(f"INSERT INTO _report_part {parts}")
            else:
                con.execute(f"CREATE TEMP TABLE _report_part AS {parts}")
            alpaca.extend(alpaca_differs(con))

        self._passes("report", step)
        as_of = ("(SELECT max(source_as_of) FROM (SELECT source_as_of FROM stg_wrds_secd "
                 "UNION ALL SELECT source_as_of FROM stg_wrds_dsf))")
        n = _create(con, "wrds_price_diff",
                    f"SELECT comparison, {as_of} AS as_of, sum(securities) AS securities, sum(sessions) AS sessions, "
                    "sum(close_differs) AS close_differs, max(max_close_diff) AS max_close_diff, "
                    "sum(return_differs) AS return_differs, max(max_return_diff) AS max_return_diff, "
                    "min(first_session) AS first_session, max(last_session) AS last_session "
                    "FROM _report_part GROUP BY comparison")
        return n, alpaca

    def note(self) -> None:
        self.ctx.notes.append(f"chunked whole build: {len(self.ranges)} chunks of security ids; " + "; ".join(self.log))
        logger.info("prices chunked whole build: %s", "; ".join(self.log))


DATASET = PricesServing()
