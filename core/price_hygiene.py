"""Shared price-hygiene gates of the screeners (#116): a series a setup cannot be read off, named by one reason.

Each gate is pure: it takes a name's D01 frames (``screen_common.load_bars`` shape: Open/High/Low/Close/Volume,
date-indexed) and returns a reason or None. ``evaluate`` runs them in ``REASONS`` order and returns the first, so a
name is counted once, under its most specific reason. No store read, no provider call.

**The gates drop** (#116 step C, after the flag week): ``decide`` turns a scan's flags into drops per reason, and
every drop is a funnel step the board shows. It drops only while the flagged names stay under ``DROP_MAX_SHARE`` of
the scan (``screen_common.STALE_DROP_MAX_SHARE``'s rule): more than that is a data failure, not a universe of broken
series, so nothing drops, every flagged name is still scored and the board carries a ``note`` step saying the cap
tripped. The reasons also stay in the run stats and on the scored rows, as they did while the gates only flagged.

Of the issue's six gates, ``spac_shell`` is not here: blank-cheque names already leave the universe as an excluded
security type before any bar is read (``screen_common.funnel_steps``, "Excluded security types"). The 8-K half of
``unexplained_jump`` is not either: a jump is explained here only by a corporate action, seen as a nominal move the
split-adjusted series does not repeat.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

REASONS = ("locked", "unexplained_jump", "repeat_jump", "broken_series", "bad_wick")
LABELS = {
    "locked": "Price not moving (5+ identical closes in the last 60 sessions)",
    "unexplained_jump": ("One-day spike over 35 % in the last 60 sessions that reverses within 2 sessions, "
                         "with no corporate action"),
    "repeat_jump": "Two or more one-day moves over 25 % in the last 60 sessions",
    "broken_series": "Gap of more than 10 sessions in the bars",
    "bad_wick": "A bar in the last 60 sessions whose high or low is 1.5x its body",
}
LOCKED_RUN = 5            # consecutive sessions with an identical close
JUMP = 0.35               # unexplained single-session move, on the nominal closes
REPEAT_JUMP = 0.25        # two or more of these in the window
GAP_SESSIONS = 10         # missing sessions in a row, against the bars' own business days
WICK = 1.5                # high / max(open, close), or min(open, close) / low
RECENT = 60               # sessions every gate but ``broken_series`` looks at (#891): a year-old move is no defect
REVERT = 0.8              # share of a spike taken back for it to be a bad print, not a move (#891)
REVERT_SESSIONS = 2       # ... within this many sessions after it
DROP_MAX_SHARE = 0.05     # more of a scan flagged than this is a data failure, and then nothing drops


def locked(nominal: pd.DataFrame) -> str | None:
    close = nominal["Close"].tail(RECENT)
    runs = close.ne(close.shift()).cumsum()
    return "locked" if len(close) and int(close.groupby(runs).size().max()) >= LOCKED_RUN else None


def _moves(frame: pd.DataFrame) -> pd.Series:
    return frame["Close"].pct_change().abs()


def unexplained_jump(nominal: pd.DataFrame, adjusted: pd.DataFrame) -> str | None:
    """A bad print: a nominal move over ``JUMP`` that the adjusted series repeats (no split or other action explains
    it) and then takes back by ``REVERT`` within ``REVERT_SESSIONS``. A move that holds is a real move (#891: two
    years of small caps hold many), not a series a setup cannot be read off. Only a spike in the last ``RECENT``
    sessions counts (#891; the 16 Nov measurement flagged 8.5 % of the universe over the whole bar window)."""
    nominal = nominal.tail(RECENT + 1)
    big = _moves(nominal) > JUMP
    if not big.any():
        return None
    adj = adjusted["Close"].reindex(nominal.index)
    real = big & (adj.pct_change().abs() > JUMP)
    for i in (int(k) for k in real.to_numpy().nonzero()[0]):
        base = adj.iloc[i - 1]
        move = abs(adj.iloc[i] / base - 1)
        after = adj.iloc[i + 1:i + 1 + REVERT_SESSIONS]
        if bool(((after / base - 1).abs() <= (1 - REVERT) * move).any()):
            return "unexplained_jump"
    return None


def repeat_jump(adjusted: pd.DataFrame) -> str | None:
    return "repeat_jump" if int((_moves(adjusted.tail(RECENT + 1)) > REPEAT_JUMP).sum()) >= 2 else None


def broken_series(nominal: pd.DataFrame) -> str | None:
    days = nominal.index
    if len(days) < 2:
        return None
    gaps = pd.Series(days[1:]).reset_index(drop=True)
    prev = pd.Series(days[:-1]).reset_index(drop=True)
    missing = [len(pd.bdate_range(a, b)) - 2 for a, b in zip(prev, gaps)]
    return "broken_series" if max(missing) > GAP_SESSIONS else None


def bad_wick(nominal: pd.DataFrame) -> str | None:
    """A bar of the last ``RECENT`` sessions whose wick runs ``WICK`` times past its body (#891: 12.2 % of the
    universe was flagged over the whole bar window, mostly for prints a year or more old)."""
    nominal = nominal.tail(RECENT)
    body_hi = nominal[["Open", "Close"]].max(axis=1)
    body_lo = nominal[["Open", "Close"]].min(axis=1)
    bad = (nominal["High"] > WICK * body_hi) | (body_lo > WICK * nominal["Low"])
    return "bad_wick" if bool(bad.any()) else None


def evaluate(nominal: pd.DataFrame, adjusted: pd.DataFrame | None = None) -> str | None:
    """The first reason of ``REASONS`` that fires on a name's frames, or None (also for no bars)."""
    if nominal is None or nominal.empty:
        return None
    adjusted = nominal if adjusted is None or adjusted.empty else adjusted
    for gate in (lambda: locked(nominal), lambda: unexplained_jump(nominal, adjusted),
                 lambda: repeat_jump(adjusted), lambda: broken_series(nominal), lambda: bad_wick(nominal)):
        reason = gate()
        if reason:
            return reason
    return None


@dataclass(frozen=True)
class Decision:
    """What a scan does with its flags: ``dropped`` is reason -> the names that leave the board, sorted.

    ``flagged`` is every flag the scan saw (ticker -> reason), ``scanned`` the names it scored over. ``capped`` says
    the cap tripped, and then ``dropped`` is empty: the flagged names keep their cards and the board shows a note
    instead of drops.
    """
    dropped: dict[str, list[str]] = field(default_factory=dict)
    flagged: dict[str, str] = field(default_factory=dict)
    scanned: int = 0
    capped: bool = False

    @property
    def share(self) -> float:
        """The flagged share of the scan; 0.0 when nothing was scanned."""
        return len(self.flagged) / self.scanned if self.scanned else 0.0


def decide(flagged: dict[str, str], scanned: int) -> Decision:
    """The drops a scan's ``flagged`` names earn (#116 step C), under ``DROP_MAX_SHARE``.

    More than ``DROP_MAX_SHARE`` of ``scanned`` flagged (or any flag at all with nothing scanned, where the share
    cannot be tested) drops nothing: a gate whose threshold is wrong must not be able to empty a board overnight.
    Exactly the share still drops, as ``screen_common.stale_names`` reads its own cap. Pure: no store, no network.
    """
    by_reason: dict[str, list[str]] = {}
    for ticker, reason in sorted(flagged.items()):
        by_reason.setdefault(reason, []).append(ticker)
    capped = len(flagged) > DROP_MAX_SHARE * scanned if scanned else bool(flagged)
    return Decision({} if capped else by_reason, dict(flagged), scanned, capped)
