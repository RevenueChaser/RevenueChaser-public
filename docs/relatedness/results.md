# Results

## The test

A company's own 10-K names its competitors (Item 1, "Competition"). From 4,301 such passages of 3,769 companies an
LLM extracted the named organisations with the sentence that names them; a name is kept only when it is literally in
the passage and inside its quoted sentence ([`method.md`](method.md) §2). Rows whose sentence says the rival sells
the same product, resolved to a universe company: **5,159 directed pairs from 1,179 naming companies**.

Score of a method: for each naming company, the share of its named rivals among the *k* companies the method ranks
nearest; the mean over naming companies. 5,020 companies have a stored business section; 1,172 of the naming
companies are among them. A GICS sub-industry has 110 other companies on average, so **k = 112 is the column to
compare with GICS**; the whole sub-industry, whatever its size, holds 52.4%.

What the test cannot do: it is recall only (it cannot call a near company wrong); the namers are 22% of the
universe and heavy in pharma (the most named: PFE 93, MRK 92, AZN 84, NVS 82); the largest companies name nobody
(AMZN, MSFT, GOOGL, TSLA, WMT, JPM, LLY).

The named pairs against GICS, as a fact about the pairs: same sub-industry 52%, industry 57%, industry group 78%,
sector 86%.

## 1. Company level (top 10 / 30 / 112)

| method | 10 | 30 | 112 |
|---|---|---|---|
| GICS sub-industry mates, random order | 11.8% | 26.6% | 42.4% |
| GICS industry-group mates, random order | 3.1% | 8.9% | 31.5% |
| bge-small vector of the section's first 2,000 characters | 16.7% | 27.2% | 42.2% |
| one LLM sentence "what is sold, to whom" per company, embedded | 23.5% | 37.0% | 52.1% |
| **words of the whole business section (the word method)** | **41.7%** | **54.2%** | **67.1%** |
| word method, the binary rule of Hoberg and Phillips | 31.1% | 42.6% | 55.2% |
| word method + the company sentence | 41.4% | 55.7% | 68.8% |
| only companies of the same GICS industry group, ordered by text | 38.8% | 50.8% | 59.2% |
| GICS sub-industry mates first, then the rest, by text | 34.3% | 46.5% | 66.6% |
| text with sub-industry and group as two more equal votes | 34.4% | 46.6% | 63.4% |

Leak checks of the word method (the test's pairs come from the Competition passages): passages left in 46.6 / 59.2
/ 71.7; passages cut out 42.0 / 54.4 / 67.5; passages cut out and lower-case words only, so no company or brand
name is a word: 41.7 / 54.2 / 67.1 (the row above).

## 2. Fixed groups (one cut of 162 groups, the number of GICS sub-industries)

Score here: the share of a namer's rivals that share a group with it; "price" is the share of all company pairs
that share a group.

| grouping | recall | price |
|---|---|---|
| GICS sector (11) | 83.7% | 12.87% |
| GICS industry group (25) | 75.4% | 6.26% |
| GICS industry (74) | 58.6% | 3.09% |
| GICS sub-industry (162) | 52.4% | 2.25% |
| bge vectors, whole companies, k-means | 20.6% | 0.79% |
| bge vectors, lines where a heading gives text, k-means | 25.7% | 0.95% |
| the same, average linkage (one group holds 13%) | 47.5% | 8.30% |

The same vectors as a nearest-112 list hold 42-43%. Cutting groups loses most of what the vectors know.

## 3. Business-line level with the word method (top 10 / 30 / 112)

Company-to-company similarity taken as the closest pair of lines; a line without text uses its company's section.

| line text from | all 1,172 namers | namers with 2+ own-text lines |
|---|---|---|
| (company level, the bar) | 41.7 / 54.2 / 67.1 | 46-47 / 61 / 75 |
| headings of Item 1 equal to the line name, else a 1,500-character window | 34.8 / 46.6 / 60.2 | 33.3 / 48.1 / 65.7 |
| the same, own-text lines only | 26.7 / 37.6 / 50.4 | 26.2 / 39.7 / 56.4 |
| whole report: defining sentences and heading bodies, by pattern | 26.8 / 38.8 / 55.3 | 19.2 / 33.4 / 56.6 |
| control: the company's own section cut into as many random chunks | | 44.0 / 58.4 / 74.2 |
| control: line texts shuffled between companies | | 0.7 / 1.2 / 2.8 |

The chunk control says the loss is not "a maximum over several units": random slices of the section do as well as
the section; the line texts are worse descriptions than a slice.

## 4. Business lines described by one LLM sentence each (top 10 / 30 / 112)

| reading | all namers | namers with 2+ described lines (442) |
|---|---|---|
| word method (the bar) | 41.7 / 54.2 / 67.1 | 46.7 / 60.7 / 73.8 |
| line sentences alone, closest pair | 23.9 / 37.2 / 54.4 | 27.7 / 43.7 / 61.9 |
| line sentences alone, revenue-weighted A to B | 24.6 / 37.7 / 55.3 | 29.7 / 45.5 / 64.4 |
| word method + line sentences, closest pair | 41.7 / 56.1 / 69.6 | 47.1 / 63.1 / 76.5 |
| **word method + line sentences, revenue-weighted** | **41.9 / 56.8 / 69.7** | 47.4 / 64.4 / 76.2 |

No shuffle or chunk control was run for this table.

## 5. What the lists look like

Word method, nearest ten: NVDA: AMD, ARM, QCOM, SHAZ, NBIS, AMBA, CDNS, MSFT, CEVA, OSS. IREN: CORZ, HUT, CIFR,
SLNH, HIVE, SHAZ, KEEL, VIP, MARA, AIB. WMT: BJ, DG, PSMT, COST, DLTR, OLLI, ACI, HD, DDS, VLGEA. JPM: PNC, USB,
FITB, TFC, COF, WFC, GS, BAC, CFG, RF. CRWD: S, RPD, PANW, ZS, NTSK, QLYS, TENB, RBRK, DDOG, NICE. AMZN: APPS, ROKU,
RUM, NWS, CPNG, PUBM, APP, U, IBTA, XYZ, with cosines of 0.11-0.14 against 0.2-0.4 for the others: a company of
many businesses, taken whole, matches nobody well.

LLM-described lines, nearest lines: IREN "AI Cloud Services": BTBT Cloud Services, WYFI Cloud Services, HIVE High
Performance Computing. AMZN "Advertising": NYT Advertising, EVC Digital Advertising, CNVS Advertising Technology.
MSFT "More Personal Computing": DELL Client Solutions, AMD Client and Gaming, CRSR. DIS "Experiences": H, PRKS
Admission, MGM Casino. Weak: AAPL "iPhone" (FNGR, BCO, STM), AMZN "Online Stores". AMZN "Amazon Web Services" has no
sentence (the report calls it "AWS"; the excerpts held executive biographies).

## 6. The two old theme runs (`module_relatedness/themes.py`, 17 Nov)

| | embedding (k-means on bge-small) | NMF (TF-IDF profile tags) |
|---|---|---|
| fine / medium / coarse | 60 / 30 / 25 | 60 / 30 / 25 |
| seed stability (ARI, fine) | 0.54 | 0.82 |
| largest coarse | 19% | 55% |
| smallest fine | 11 | 8 |

Agreement between the two (ARI): fine 0.25, medium 0.19, coarse 0.07. Neither was cut over. Code defects found by
the review and still in `themes.py` at the time of writing: medium and coarse are Ward merges of fine centroids;
`rebalance_coarses` clusters on a Jaccard matrix that is all ones; the tag `rank` fed to the namer is alphabetical;
`cutover_materialize` refuses only an empty run.
