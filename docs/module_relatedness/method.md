# The parts that work, as run

Everything here was run from scratch scripts on homesrv ([`reproduce.md`](reproduce.md)); none of it is repository
code yet, except the builder change of §3.

## 1. The word method (company to company)

After Hoberg and Phillips, "Text-Based Network Industries and Endogenous Product Differentiation" (JPE 2016): two
companies are related to the degree that their 10-K product descriptions use the same uncommon words.

1. **Text.** Each company's stored 10-K business section (`rcdata.read.filing_texts(ciks, "business")`), page
   furniture stripped (lines that are only a page number, "Table of Contents", "PART I", "Item 1 ..."), whitespace
   collapsed. 5,020 universe companies have one of at least 300 characters; 378 million characters in all.
2. **Competition passages cut out.** Every passage under a "Competition" heading (§2) is removed first, because the
   test is built from those passages and a rival's name would otherwise be a rare shared word.
3. **Words.** Lower-case words of three or more letters (`(?<![A-Za-z])[a-z][a-z\-]{2,}\b`, no lower-casing, so a
   capitalised name is not a word), used by at least 2 companies and by at most 25% of them (`min_df=2`,
   `max_df=0.25`; the 25% cut is the paper's). 53,927 words.
4. **Weights.** Sublinear TF-IDF, L2-normalised rows (`TfidfVectorizer(sublinear_tf=True, norm="l2")`). The paper's
   binary rule (a word is there or not) scores 12 points lower on our test.
5. **Similarity.** Cosine: `X @ X.T`. 5,020 x 5,020 in about 90 seconds, under a 3 GB memory cap.

Output today: a dense float32 matrix in scratch. Not decided: how many neighbours to keep per company, and where
the rows live.

## 2. Named rivals (the test list; also a list worth showing)

1. **Passage.** In the business section, every line that is a heading "Competition", "Competitors" or "Competitive
   Conditions / Landscape / Environment / Position"; the passage runs to the next heading-like line (a short line
   that starts with a capital and has no sentence end), at most 6,000 characters. 3,769 of 5,308 companies have one
   (10-K 3,018 of 3,983; 20-F 682 of 960; 40-F 65 of 90); 4,301 passages; 126 end at the cap.
2. **Reader.** DeepSeek Flash (`deepseek-v4-flash`, temperature 0, prompt `rivals-pilot-1`), one call per passage,
   JSON: each organisation named as a competitor, the complete sentence or bullet that names it, and the basis as
   the passage words it: `same_product`, `in_house` (builds it for its own use), `partner_customer_supplier`,
   `unclear`.
3. **Guard.** A row is kept only if the name is literally in the passage, the sentence is literally in the passage,
   and the name is inside that sentence. 16,650 names returned, 16,592 kept. 54 passages answered with something
   that was not JSON and are lost (not looked into).
4. **Name to company.** Against the spine's names, cleaned of legal suffixes: exact; else the passage's own alias
   ("Advanced Micro Devices, Inc., or AMD"); else a prefix that fits exactly one spine company. No hand-made table.
   Of 16,019 rows: one universe company 5,429 (exact 4,894, prefix 799, alias 20), a spine company outside the
   universe 284, several candidates 174, unresolved 10,132.
5. **The list.** `same_product` rows resolved to a universe company: 5,159 directed pairs, 1,179 naming companies,
   1,610 named, 244 pairs named in both directions.

Known faults: of 30 audited prefix matches 3 were wrong (all "Tencent Holdings" taken for Tencent Music); the
unresolved names include universe companies under brand or former names (Google 56 times, IBM, Facebook, AWS),
which need the SEC's former-names list, not in the store; the model sometimes returns categories ("credit unions")
that then stay unresolved; a 10-K "competitor" is wider than "sells the same product" (NVDA names Amazon and
Microsoft for in-house chips; the `in_house` basis catches these: 68 rows).

## 3. Business lines and their share of revenue

**In the builder** (RevenueChaser-public #1048 / PR #1050, #1066 / PR #1068, #1070 / PR #1071, all live):
`sec/filings` fetches each annual report's definition linkbase (`*_def.xml`, or the `.xsd` when the linkbase is
embedded in it), and `segment_revenue.report_tables` names the report tables in which a row's member stands on
its axis. `rcdata.read.segment_sets(rows, total)` returns the member sets that one table declares together and that
sum to revenue within 2%, the set with the most members first. Coverage after the backfill: `report_tables` on 3,506
of 3,512 filings.

Why: a filing lists parents and children on one axis (Amazon: {Product, Service} on the income statement and seven
finer members in the segment note), so the flat list sums to twice the revenue; the linkbase says which members
belong to one table.

**The choice among several usable sets** (scratch rule "R3", used for §4 of the results; not in the repository):
the business-axis table set, unless one of its member names is a common geographic name, then the product-axis
table set; if no table set, the older flat rule (a (source, axis) set that sums within 2%, SEC before WRDS); else
the company is one line. "Common geographic name" = a name at least 10 companies put on the XBRL geographic axis
(153 names). **That 10 is a judgement value without a source; it waits on avo** ([`open.md`](open.md)). Two other
choices were measured and the test could not tell them apart (60.2 against 59.5).

Result: 2,519 companies on lines (business-axis table set 1,064, product-axis 1,190, flat rule 265), 7,253 lines;
2,789 companies whole. AMZN: Online Stores 37.6%, Third-Party Seller Services 24.0%, Amazon Web Services 18.0%,
Advertising 9.6%, Subscription Services 6.9%, Physical Stores 3.1%, Other Services 0.8%. AAPL: iPhone 53.1%, Services
25.8%, Mac 7.9%, Wearables, Home and Accessories 7.4%, iPad 5.8%. MSFT: Productivity and Business Processes 42.2%,
Intelligent Cloud 41.5%, More Personal Computing 16.3%. DIS: Entertainment 45.0%, Experiences 38.3%, Sports 18.7%.

Limits: a reported segment is often wider than one business (META "Family of Apps" 98.9%, NVDA "Compute and
Networking" 89.6%); labels come from XBRL member names ("I Phone", "Wearables Homeand Accessories").

## 4. One sentence per business line (adds 2.6 points to the word method)

1. **Excerpts** (a script, no model): from the stored whole annual report, per line: the text under up to two
   headings equal to the line name (1,500 characters each), up to six sentences where the name is followed by a
   verb such as includes, consists of, provides, sells, and up to eight other sentences naming the line; 3,500
   characters at most; sentences inside the Competition passages left out. Found for 5,677 of 7,253 lines.
2. **Writer.** DeepSeek Flash, temperature 0, prompt `line-sells-1`: one sentence of at most 40 words, what the
   line sells and to whom, only from the excerpts, empty when they do not say. 5,689 calls in about 25 minutes at 6
   in parallel; 837 empty answers; 4,819 lines described.
3. **Vector.** The board's embedding model (`BAAI/bge-small-en-v1.5`, fastembed) on the sentence. A line without a
   sentence uses a company-level sentence written the same way from the first 2,000 characters of the section.
4. **Company to company.** Directed and revenue-weighted: `rel(A -> B) = sum over A's lines of share x max over
   B's lines of cosine`. Added to the word method as a plain sum of row-standardised matrices.

The weak link is step 1, not the writer: AMZN's "Amazon Web Services" got executive biographies as excerpts because
the report says "AWS", and the writer rightly returned nothing. A third of the lines (2,410) have no description.
EVREN was tried as the writer first and gave one answer per 40-75 seconds at the one-request-at-a-time rule.
