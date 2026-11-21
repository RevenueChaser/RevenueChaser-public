"""#407: the Value Chain splitter residue, re-measured against ``ours-2`` and fixed in ``ours-3`` where it is real.

The issue was written on 4 Nov 2026 against ``main`` ``99396da``, which is **before** ``ours-2`` (#847). Both of
its cases have to be re-read against the rule as it stands, and they do not come out the same way:

- **(a) the 20-F cross-reference start.** Still real, but much narrower than the issue says. Its premise -- "the
  20-F start pattern has no title guard" -- is stale: ``START_PATTERNS_2``'s 20-F branch requires
  "information on the company|group" after the number, and a reference introduced by "see", "under", "refer to"
  or a quote is thrown out on both paths (``_words_before_ref`` on the pattern path, ``_ref_ours_2`` on the line
  path). What survives is a cross-reference written as its **own line** with no such word in front of it. Fixed
  in ``ours-3`` by ``_own_heading_after``.
- **(b) a tiny Item 1 losing to a later mention.** Not fixed, on purpose, and the tests below pin which way it
  goes rather than asserting a direction nobody has evidence for. Passing over a start whose body is under
  ``_BODY_MIN`` was *measured* as the right answer on TIGO and EC, where the short start was an index block the
  contents check missed. Length cannot tell that block from a genuinely short real Item 1, so (b) needs a
  distinguisher that does not exist yet.

**What these tests cannot do.** The filings are not in this tree and no test fetches one: an SEC request needs the
owner's word. So each input is the shape the issue describes, built here. A passing run says the rule now answers
that shape correctly, not that the real ADR filings cut correctly -- that is the ``--reslice-dry-run`` on the
stored corpus, which needs homesrv and is this issue's remaining step.

Red on the merge-base: ``sec_sections.OURS_3`` does not exist there, so every case that names it fails at
``getattr``. The ``ours-2`` cases are **characterisation** and pass on the base too, which is the point of them:
they are what says (a)'s premise is stale and (b) is unchanged.
"""
from __future__ import annotations

import pytest

from RevenueChaser.rcdata import sec_sections

from .sec_sections_cases import BODY

OURS_1, OURS_2 = sec_sections.OURS_1, sec_sections.OURS_2
OURS_3 = sec_sections.OURS_3

RISK = "Our business faces many risks that could harm us. " * 300
ITEM_4_BODY = "We operate three segments and sell through distributors. " * 400


def _cut(text: str, version: str, form: str = "20-F"):
    return sec_sections.cut_item(text, form, version=version)


def _twenty_f(crossref_line: str) -> str:
    """A 20-F whose Item 3 carries ``crossref_line`` on its own line, with the real Item 4 further down."""
    return ("Item 3. Key Information\n" + RISK + "\n" + crossref_line + "\n" + RISK
            + "\nItem 4. Information on the Company\n" + ITEM_4_BODY
            + "\nItem 5. Operating and Financial Review and Prospects\n" + BODY)


# ── (a) the shape a reference word already covers: stale premise, nothing to fix ───────────────────────────────

@pytest.mark.parametrize("line", [
    "See Item 4. Information on the Company for a description of our operations.",
    "Refer to Item 4. Information on the Company below.",
    "“Item 4. Information on the Company” describes this in full.",
])
def test_a_reference_word_or_a_quote_before_the_heading_is_already_thrown_out_by_ours_2(line):
    """So the issue's "the 20-F start has no title guard" is not what is left of case (a)."""
    item, quality = _cut(_twenty_f(line), OURS_2)
    assert quality == "ok", quality
    assert item.startswith(ITEM_4_BODY[:40]), "the real Item 4 is the start"
    assert "Our business faces many risks" not in item


# ── (a) what is actually left: the bare line, which no guard sees ──────────────────────────────────────────────

BARE = "Item 4. Information on the Company contains a fuller description of these operations."


def test_ours_2_starts_inside_the_risk_factors_on_a_bare_cross_reference_line_and_calls_it_ok():
    """The measurement that says case (a) is real. Every guard passes: not a contents entry, no page number after
    it, no reference word or quote in front of it, and the body behind it is far over ``_BODY_MIN``. And the label
    is ``ok``, because the only check that could have said otherwise -- ``_holds_another_item`` -- skips the
    heading of the slice's **own** item number, which is exactly the heading inside this slice.
    """
    item, quality = _cut(_twenty_f(BARE), OURS_2)
    assert sec_sections.base(quality) == "ok", quality
    assert "Our business faces many risks" in item, "the slice ran through the risk factors"
    assert "Item 4. Information on the Company" in item, "and swallowed the real heading"


def test_ours_3_passes_the_bare_cross_reference_over_and_starts_at_the_real_heading():
    item, quality = _cut(_twenty_f(BARE), OURS_3)
    assert quality == "ok", quality
    assert item.startswith(ITEM_4_BODY[:40])
    assert "Our business faces many risks" not in item
    assert "Item 4. Information on the Company" not in item


def test_the_guard_is_the_same_item_s_own_heading_further_down_and_nothing_else():
    text = _twenty_f(BARE)
    first = next(sec_sections._LINE_START_2["20-F"].finditer(text))
    assert sec_sections._own_heading_after(text, first, "20-F") is True
    real = [m for m in sec_sections._LINE_START_2["20-F"].finditer(text)][-1]
    assert sec_sections._own_heading_after(text, real, "20-F") is False, "the real heading has none after it"


def test_a_20_f_with_one_heading_and_no_cross_reference_is_cut_the_same_by_both_versions():
    """``ours-3`` adds a guard, so the one thing it must not do is move an ordinary filing."""
    text = ("Item 3. Key Information\n" + RISK + "\nItem 4. Information on the Company\n" + ITEM_4_BODY
            + "\nItem 5. Operating and Financial Review and Prospects\n" + BODY)
    assert _cut(text, OURS_3) == _cut(text, OURS_2)


def test_a_10_k_is_cut_the_same_by_both_versions_on_the_shared_shapes():
    """The guard is written for both forms but the shape is a 20-F's; a 10-K must not move either."""
    text = ("Item 1. Business\n" + BODY + "\nItem 1A. Risk Factors\n" + RISK)
    assert _cut(text, OURS_3, form="10-K") == _cut(text, OURS_2, form="10-K")
    ran_on = "part one Item 1 - Business of the registrant follows.\n\nItem 1. Business\n" + BODY
    assert _cut(ran_on, OURS_3, form="10-K") == _cut(ran_on, OURS_2, form="10-K")


def test_a_run_in_heading_named_again_in_its_own_first_sentence_is_not_a_second_heading():
    """The guard looks beyond ``MIN_ITEM_CHARS`` for exactly this reason: a filer who repeats his own heading in
    the section's first paragraph has not written two headings, and ``ours-3`` must not pass over the real one."""
    text = ("Item 3. Key Information\n" + RISK + "\nItem 4. Information on the Company\n"
            + "Item 4. Information on the Company is set out below. " + ITEM_4_BODY
            + "\nItem 5. Operating and Financial Review and Prospects\n" + BODY)
    item, quality = _cut(text, OURS_3)
    assert quality == "ok", quality
    assert item.startswith("Item 4. Information on the Company is set out below.")


# ── (b) not fixed: pinned as it is, so a later round knows what it is changing ──────────────────────────────────

def test_b_a_short_start_is_still_passed_over_for_a_later_long_one_in_every_version():
    """#407 case (b) reads this as a defect; TIGO and EC measured it as the right answer. Both readings are of the
    same rule, and nothing here decides between them -- this pins the behaviour so that a round which does decide
    has to change a test and say why. ``_BODY_MIN`` is 4,000, so the first body is under it on purpose.
    """
    text = ("Item 1. Business\n" + "A small real section. " * 100 + "\nItem 2. Properties\nland\n\n"
            + "Item 1. Business\n" + BODY + "\nItem 1A. Risk Factors\n" + RISK)
    for version in (OURS_2, OURS_3):
        item, quality = _cut(text, version, form="10-K")
        assert quality == "ok", (version, quality)
        assert item.startswith(BODY[:40]), version
        assert "A small real section." not in item, version


def test_b_the_distinguisher_case_b_would_need_does_not_exist_in_the_rule_today():
    """Both inputs below are "a start whose body is under ``_BODY_MIN``, with a longer one after it". One reads as
    an index block (case (b)'s measured counter-example) and one as a genuinely short real section (case (b)'s
    complaint). The rule answers them identically, which is the whole of why (b) is still open.

    **The first version of this test failed, and the failure was the fixture's and not the rule's.** It gave the
    index block the filler ``"Business 3. Properties 7. "``, which names Item 2 inside the slice, so
    :func:`_holds_another_item` labelled it ``overrun`` while the other input was ``ok`` -- a difference my own
    text put there, about item words in the filler, not about the thing under test. Neither filler names an item
    now, and the test asserts that, so it cannot drift back into measuring my prose.
    """
    index_filler = "Segment overview, page 3, and the fuller description follows. " * 60
    real_filler = "We make one product and sell it. " * 70
    for filler in (index_filler, real_filler):
        assert not sec_sections._LINE_END_2.search(filler), "the filler must not name an item of its own"
    def _built(filler):
        return ("Item 1. Business\n" + filler + "\nItem 2. Properties\nland\n\n"
                + "Item 1. Business\n" + BODY + "\nItem 1A. Risk Factors\n" + RISK)
    index_block, real_short = _built(index_filler), _built(real_filler)
    got = [_cut(index_block, OURS_3, form="10-K"), _cut(real_short, OURS_3, form="10-K")]
    assert got[0][1] == got[1][1], "the label cannot tell them apart"
    assert all(item.startswith(BODY[:40]) for item, _ in got), "and neither can the cut: both take the later start"


# ── the version is declared and reachable, and the boards have not moved onto it ────────────────────────────────

def test_ours_3_is_declared_and_reachable_like_any_other_version():
    assert OURS_3 in sec_sections.VERSIONS
    assert sec_sections.rule(OURS_3).version == OURS_3
    assert sec_sections.rule(OURS_3).caps is False
    with pytest.raises(ValueError):
        sec_sections.rule("ours-4")


def test_no_board_and_no_layer_reads_ours_3_yet():
    """Moving a pin onto it re-cuts ``chain_filings`` and restales every Relatedness profile, which is a paid
    model run: that is its own change, with the owner's before/after look."""
    from RevenueChaser.module_value_chain import splitter
    assert splitter.VERSION == OURS_2, "the pin moves with a re-slice, not with this PR"
    assert sec_sections.DEFAULT_VERSION == OURS_1


def test_ours_3_shares_ours_2_s_aif_cutter_and_signal_sets_rather_than_restating_them():
    two, three = sec_sections.rule(OURS_2), sec_sections.rule(OURS_3)
    assert three.aif_business is two.aif_business and three.aif_business_q is two.aif_business_q
    assert three.item_signals == two.item_signals and three.aif_signals == two.aif_signals
    assert three.slice_item is not two.slice_item, "the item cutter is the one thing that differs"
