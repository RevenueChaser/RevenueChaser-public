"""Real SEC bytes, trimmed, against what the parsers say they read (#1161, the third part of #896 step 3).

Every other test of these parsers feeds them bytes written in Python (``ownership_fixture``,
``sec_sections_cases``). That catches a mistake in our code and nothing at all in the source: a header the SEC
renames, a member it drops, a column it moves is invisible to CI until a live run fails. The samples under
``fixtures/sec_samples/`` are cut from the newest raw file of each data set the store holds -- every member kept,
each one cut to its header line and 50 rows, which is exactly the part a parser reads for its columns. 208 KB for
nine data sets; ``manifest.json`` names each one's raw file, its bytes, the trim and the SEC URL. No request goes
to sec.gov from here: the samples are files in the tree.

What each kind of test can and cannot say:

- A **member** test compares the names the parser's own constant lists (``nport.MEMBERS``, ``ftd.NEEDED``, ...)
  against the real zip, so a member the SEC drops fails here.
- A **column** test does the same for the columns, and for the two sets whose hand-written fixture claims to carry
  "the columns of <a real set>" it compares that claim to the real header, in order. That is the one place where a
  rename cannot hide: the fixture would keep passing on its own.
- A **parse** test runs the real parser over the real bytes. It proves the shape the parser asserts is the shape
  the file has.

A column list written out in this file -- N-CEN's, because its columns live inside its SQL rather than in a
constant -- guards the source, not our code: if the parser stops reading a column and this list keeps it, the test
still passes. The drift that matters here is the SEC's.

``test_a_trimmed_zip_keeps_every_member_of_the_set_it_was_cut_from`` is why the rest can be trusted, and it has
already earned its place: the first N-CEN sample held 40 members where its own trim counted 46, and one of the six
it had quietly dropped was ``SECURITY_EXCHANGE.tsv``, which ``spine/ncen.py:51`` reads. Nothing was wrong with the
data -- the sampler capped a zip at 40 members -- but an incomplete sample reads exactly like the SEC dropping a
member, so the count is checked before any member test is believed.
"""
from __future__ import annotations

import gzip
import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from ..build.fundamentals import sec_index
from ..build.ownership import form345_sets, ftd, nport, sec13f_sets
from ..build.spine import ncen, sec_tickers, sec_tickers_mf
from . import ownership_fixture

SAMPLES = Path(__file__).parent / "fixtures" / "sec_samples"
ZIPS = {
    "13f_sets": "13f_sets/01sep2024-30nov2024_form13f.zip",
    "form345_sets": "form345_sets/2026q3_form345.zip",
    "fsds": "fsds/2026q3.zip",
    "ftd": "ftd/cnsfails202610b.zip",
    "ncen": "ncen/2025q4.zip",
    "nport": "nport/2026q3_nport.zip",
}
# The members each parser names, from its own constant where it has one.
PARSER_MEMBERS = {
    "13f_sets": tuple(f"{m}.tsv" for m in sec13f_sets.MEMBERS),
    "form345_sets": tuple(f"{m}.tsv" for m in form345_sets.MEMBERS),
    "ncen": ncen.FILES,
    "nport": tuple(f"{m}.tsv" for m in nport.MEMBERS),
    "fsds": ("sub.txt", "num.txt"),
    "ftd": ("cnsfails202610b.txt",),
}
# ``fsds._select`` refuses a set without one of these (rcdata/build/fundamentals/fsds.py:142).
FSDS_NUM = ("adsh", "tag", "ddate", "qtrs", "uom", "value")
FSDS_SUB = ("adsh", "cik", "form", "filed")
# N-CEN names its columns inside ``Ncen._series`` and ``Ncen._filers`` (rcdata/build/spine/ncen.py:183-211), not in
# a constant this test could read, so they are written out here.
NCEN_COLUMNS = {
    "SUBMISSION.tsv": ("ACCESSION_NUMBER", "CIK", "FILING_DATE", "REPORT_ENDING_PERIOD"),
    "FUND_REPORTED_INFO.tsv": ("ACCESSION_NUMBER", "FUND_ID", "SERIES_ID", "FUND_NAME", "IS_ETF", "IS_INDEX",
                               "IS_MULTI_INVERSE_INDEX", "IS_MONEY_MARKET", "IS_FUND_OF_FUND",
                               "DAILY_AVG_NET_ASSETS", "MONTHLY_AVG_NET_ASSETS"),
    "SECURITY_EXCHANGE.tsv": ("FUND_ID", "FUND_TICKER_SYMBOL", "FUND_EXCHANGE"),
}


def _manifest() -> list[dict]:
    return json.loads((SAMPLES / "manifest.json").read_text())


def _members(name: str) -> dict[str, str]:
    """``{base name: member path}`` of a sample zip (one real set nests its members in a folder)."""
    with zipfile.ZipFile(SAMPLES / ZIPS[name]) as z:
        return {Path(m).name: m for m in z.namelist()}


def _header(name: str, member: str, delim: str = "\t") -> tuple[str, ...]:
    with zipfile.ZipFile(SAMPLES / ZIPS[name]) as z:
        with z.open(_members(name)[member]) as f:
            line = f.readline().decode("utf-8", "replace")
    return tuple(line.rstrip("\r\n").split(delim))


def test_the_manifest_names_every_sample_in_the_tree_and_no_other():
    named = {e["sample"] for e in _manifest()}
    held = {str(p.relative_to(SAMPLES)) for p in SAMPLES.rglob("*") if p.is_file()} - {"manifest.json"}
    assert named == held


def test_every_manifest_entry_says_where_its_bytes_came_from():
    for e in _manifest():
        assert e["raw_file"] and e["trim"], e
        assert e["sample_bytes"] == (SAMPLES / e["sample"]).stat().st_size, e["sample"]


def test_a_trimmed_zip_keeps_every_member_of_the_set_it_was_cut_from():
    """The member tests below are only as good as this: a sample that quietly lost a member would read as the SEC
    having dropped one. The trim states the count it kept, so compare the two."""
    for e in _manifest():
        if not e["trim"].startswith("zip: "):
            continue
        counted = re.search(r"\d+", e["trim"])
        assert counted, f"{e['dataset']}: the trim states no member count ({e['trim']!r})"
        with zipfile.ZipFile(SAMPLES / e["sample"]) as z:
            held = len(z.namelist())
        assert held == int(counted[0]), f"{e['dataset']}: trim counted {counted[0]}, sample holds {held}"


@pytest.mark.parametrize("name", sorted(PARSER_MEMBERS))
def test_every_member_the_parser_names_is_in_the_real_set(name):
    missing = [m for m in PARSER_MEMBERS[name] if m not in _members(name)]
    assert not missing, f"{name}: {', '.join(missing)} not in {ZIPS[name]}"


@pytest.mark.parametrize("member", sorted(nport.OPTIONAL))
def test_the_columns_the_nport_loader_reads_are_in_the_real_set(member):
    header = _header("nport", f"{member}.tsv")
    missing = [c for c in nport.OPTIONAL[member] if c not in header]
    assert not missing, f"N-PORT {member}: {', '.join(missing)}"


@pytest.mark.parametrize("member", sorted(NCEN_COLUMNS))
def test_the_columns_the_ncen_sql_reads_are_in_the_real_set(member):
    header = _header("ncen", member)
    missing = [c for c in NCEN_COLUMNS[member] if c not in header]
    assert not missing, f"N-CEN {member}: {', '.join(missing)}"


def test_the_columns_the_fails_to_deliver_loader_needs_are_in_the_real_file():
    header = _header("ftd", "cnsfails202610b.txt", delim="|")
    missing = [c for c in ftd.NEEDED if c not in header]
    assert not missing, ", ".join(missing)


def test_the_columns_the_financial_statement_sets_require_are_in_the_real_set():
    num, sub = _header("fsds", "num.txt"), _header("fsds", "sub.txt")
    assert not [c for c in FSDS_NUM if c not in num], f"num.txt: {num}"
    assert not [c for c in FSDS_SUB if c not in sub], f"sub.txt: {sub}"


def test_the_hand_written_13f_set_fixture_is_the_real_sets_header():
    """``ownership_fixture.set_zip`` says it writes "the columns of 01jun2026-31aug2026_form13f.zip", and every
    13F test reads that claim rather than a filing. Measured against the real set, each member's columns are its
    whole header in its own order, so this is an equality: a column the SEC renames, drops, adds or moves fails
    here, where the fixture's own tests would keep passing for ever."""
    for member, claimed in ownership_fixture.SET_COLUMNS.items():
        real = _header("13f_sets", f"{member}.tsv")
        assert claimed == real, f"13F {member}: the fixture writes {claimed}, the real set has {real}"


def test_the_hand_written_insider_set_fixture_names_only_real_columns():
    """``F345_COLUMNS`` keeps the columns the insider parser reads and leaves the rest of each member out, in its
    own order, so it cannot be compared as a header. What it can say: every column it names is in the real set.
    A rename fails here; a column the SEC adds does not, which is the right answer for a deliberate subset."""
    for member, claimed in ownership_fixture.F345_COLUMNS.items():
        real = _header("form345_sets", f"{member}.tsv")
        missing = [c for c in claimed if c not in real]
        assert not missing, f"insider {member}: {', '.join(missing)} not in the real set"


def test_the_daily_index_parser_reads_the_real_index():
    text = gzip.decompress((SAMPLES / "daily_index/master.20210201.idx.gz").read_bytes()).decode("latin-1")
    rows = sec_index.parse(text)
    assert rows, "no filing read from the real index"
    assert all(set(r) == {"cik", "company", "form", "filed", "accession"} for r in rows)
    assert all(r["filed"] == "2021-02-01" for r in rows), {r["filed"] for r in rows}
    assert all(r["cik"].isdigit() and r["company"] and r["form"] for r in rows)


@pytest.mark.parametrize("sample, module, key", [
    ("company_tickers_exchange/2026-11-19.json.gz", sec_tickers, "ticker"),
    ("company_tickers_mf/2026-11-16.json.gz", sec_tickers_mf, "class_id"),
])
def test_the_sec_ticker_file_parses_as_the_builder_expects(sample, module, key):
    body = json.load(io.TextIOWrapper(gzip.open(SAMPLES / sample), encoding="utf-8"))
    rows = module.parse(body)
    assert rows, sample
    assert all(r[key] for r in rows), sample
    assert all(r["cik"].isdigit() for r in rows), sample
