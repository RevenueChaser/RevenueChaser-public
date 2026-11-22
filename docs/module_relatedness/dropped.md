# Tried and dropped

Each line: what, the number that dropped it, where the full table is.

| tried | result | see |
|---|---|---|
| The existing theme builder, NMF on profile tags | seed ARI 0.82 at k=60 (no k reached the 0.90 floor); 55% of companies in one coarse theme | `results.md` §6 |
| The existing theme builder, k-means on bge-small company vectors | seed ARI 0.54; AAPL and MSFT in a semiconductor theme; agreement with the NMF run 0.07 at coarse | `results.md` §6 |
| Any fixed cut of 162 groups from text vectors | 21-26% of rivals share a group (GICS sub-industry: 52%); the same vectors as a nearest-112 list hold 42-43% | `results.md` §2 |
| bge-small vectors of the section's first 2,000 characters | 42.2% at 112, level with GICS mates in random order | `results.md` §1 |
| GICS in front of or beside the text | every form lowers the word method's score (59.2-66.6 against 67.1) | `results.md` §1 |
| Line text from Item 1 headings equal to the line name, plus an in-text window | 60.2% against 67.1% at company level; random chunks of the section do as well as the section | `results.md` §3 |
| Line text from the whole report by pattern (defining sentences, heading bodies) | 55.3%; the sentences come from revenue-recognition notes and share accounting words across industries | `results.md` §3 |
| A split search for parents and children (two parts that each sum to revenue) | not unique: Amazon's product members split at least three ways; replaced by the linkbase | `method.md` §3 |
| "Drop a set if any member name is on the geographic axis somewhere" | the vocabulary is dirty (1,377 names, 840 used by one company); it dropped Amazon's and Alphabet's sets | `method.md` §3 |
| EVREN as the writer of 5,677 line sentences | 40-75 seconds per call at one request at a time; about 117 hours | `method.md` §4 |
| Thematic ETF themes as the source of the groups | withdrawn on avo's word: the board relates companies by business from SEC text; fund themes are the ETF lane's list and only a test here | `open.md` |

Things measured on the way that are not methods:

- All four GICS levels are in the spine (`gsector` 11 values, `ggroup` 25, `gind` 74, `gsubind` 162; filled for 98%
  of the universe); `core/universe.py` hands the boards two.
- `segment_revenue` before the linkbase: SEC product axis, 2,322 companies, 1,326 summing within 2%, 270 at about
  twice the total; WRDS business axis, 3,810 companies, 3,456 within 2%, 2,093 with one segment.
- A line's name is a heading of the Item 1 section for 21-36% of line revenue, and a heading or a defining sentence
  somewhere in the whole report for about half of the lines.
