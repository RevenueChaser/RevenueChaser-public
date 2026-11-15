"""EDGAR bulk ingest — synthetic zips, no network."""
from __future__ import annotations

import json
import zipfile

import httpx
import pytest

from RevenueChaser.core import edgar_bulk as eb
from RevenueChaser.core import rawstore


def _zip(tmp_path, name, files: dict):
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as zf:
        for fn, payload in files.items():
            zf.writestr(fn, json.dumps(payload))
    return p


def _submissions():
    return {"CIK0000320193.json": {"cik": "320193", "name": "Apple Inc.", "sic": "3571",
                                   "sicDescription": "Electronic Computers"}}


def test_companyfacts_is_gone_with_edgar_facts():
    """#860 stage 2: ``edgar_facts`` lived in ``edgar.duckdb`` and nothing read it, so its ingest went too."""
    assert list(eb.bulk_urls()) == ["submissions.zip"]
    assert not hasattr(eb, "ingest_companyfacts")
    assert "edgar_facts" not in rawstore.MANIFEST and "edgar_companyfacts" not in rawstore.MANIFEST


def test_ingest_submissions(rawstore_tmp_db, tmp_path):
    rawstore.write_rows("sec_exchange_file",
                        [{"ticker": "AAPL", "cik": "320193", "name": "Apple", "exchange": "Nasdaq",
                          "valid_from": None, "status": "present", "source": "sec_exchange", "fetched_at": 1.0,
                          "run_id": "seed", "run_at": 1.0}])
    p = _zip(tmp_path, "submissions.zip", {"CIK0000320193.json": {
        "cik": "320193", "name": "Apple Inc.", "sic": "3571",
        "sicDescription": "Electronic Computers"}})
    out = eb.ingest_submissions(p)
    assert out["matched"] == 1 and out["coverage"] == 1.0
    assert rawstore.get("sec_company_sic", "AAPL")["sic"] == "3571"


def test_ingest_dir_deletes_zips(rawstore_tmp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "OUTPUT_DIR", tmp_path)
    d = eb.bulk_dir()
    _zip(d, "submissions.zip", _submissions())
    out = eb.ingest_dir()
    assert out["submissions.zip"]["ciks"] == 1
    assert not (d / "submissions.zip").exists()


# --- download: a half-written file never replaces a good zip (#168a / P18) ---------

class _Stream:
    """One streamed response: ``chunks`` then, optionally, a read error after ``fail_after`` chunks."""

    def __init__(self, chunks=(b"NEW-",b"ZIP"), status=200, fail_after=None, on_chunk=None):
        self.chunks, self.status = list(chunks), status
        self.fail_after, self.on_chunk = fail_after, on_chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError("bad status", request=httpx.Request("GET", "http://x"),
                                        response=httpx.Response(self.status))

    def iter_bytes(self, size=None):
        for i, chunk in enumerate(self.chunks):
            if self.fail_after is not None and i == self.fail_after:
                raise httpx.ReadError("connection cut")
            if self.on_chunk:
                self.on_chunk(i)
            yield chunk


class _StreamClient:
    def __init__(self, stream=None):
        self.urls: list[str] = []
        self._stream = stream or _Stream()

    def stream(self, method, url):
        self.urls.append(url)
        return self._stream

    def close(self):
        pass


@pytest.fixture
def no_throttle(monkeypatch):
    monkeypatch.setattr(eb.sec_edgar, "_throttle", lambda: None)


def test_download_all_builds_the_urls_from_the_sec_base_at_call_time(tmp_path, monkeypatch, no_throttle):
    monkeypatch.setattr(eb, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(eb.sec_edgar, "SEC_WWW_BASE", "http://127.0.0.1:9")
    client = _StreamClient()
    eb.download_all(client)
    assert client.urls == ["http://127.0.0.1:9/Archives/edgar/daily-index/bulkdata/submissions.zip"]


def test_download_all_uses_the_real_sec_host_by_default(tmp_path, monkeypatch, no_throttle):
    monkeypatch.setattr(eb, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(eb.sec_edgar, "SEC_WWW_BASE", "https://www.sec.gov")
    client = _StreamClient()
    eb.download_all(client)
    assert client.urls[0] == "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"


def test_download_streams_into_a_part_file_and_replaces_only_at_the_end(tmp_path, no_throttle):
    dest = tmp_path / "submissions.zip"
    dest.write_bytes(b"OLD-ZIP")
    part = tmp_path / "submissions.zip.part"
    seen = []

    def _check(i):
        seen.append((i, dest.read_bytes(), part.exists()))

    eb.download("http://x/submissions.zip", dest, _StreamClient(_Stream(on_chunk=_check)))
    assert seen and all(old == b"OLD-ZIP" and has_part for _, old, has_part in seen), seen
    assert dest.read_bytes() == b"NEW-ZIP"
    assert not part.exists()


def test_a_download_cut_off_midway_keeps_the_previous_zip_byte_identical(tmp_path, no_throttle):
    dest = tmp_path / "submissions.zip"
    dest.write_bytes(b"OLD-ZIP")
    with pytest.raises(httpx.ReadError):
        eb.download("http://x/submissions.zip", dest, _StreamClient(_Stream(fail_after=1)))
    assert dest.read_bytes() == b"OLD-ZIP"
    assert not (tmp_path / "submissions.zip.part").exists()   # the half file is cleaned up


def test_an_error_status_keeps_the_previous_zip_and_leaves_no_part(tmp_path, no_throttle):
    dest = tmp_path / "submissions.zip"
    dest.write_bytes(b"OLD-ZIP")
    with pytest.raises(httpx.HTTPStatusError):
        eb.download("http://x/submissions.zip", dest, _StreamClient(_Stream(status=503)))
    assert dest.read_bytes() == b"OLD-ZIP"
    assert list(tmp_path.glob("*.part")) == []


def test_a_first_download_that_fails_leaves_nothing_behind(tmp_path, no_throttle):
    dest = tmp_path / "submissions.zip"
    with pytest.raises(httpx.ReadError):
        eb.download("http://x/submissions.zip", dest, _StreamClient(_Stream(fail_after=0)))
    assert list(tmp_path.iterdir()) == []


# --- ingest_dir: a zip is deleted only after its ingest ran to the end ---------------

def test_ingest_dir_with_a_limit_keeps_the_zip(rawstore_tmp_db, tmp_path, monkeypatch):
    """``limit`` stops the ingest early, so the rest of the archive would be lost with the zip."""
    monkeypatch.setattr(eb, "OUTPUT_DIR", tmp_path)
    d = eb.bulk_dir()
    _zip(d, "submissions.zip", _submissions())
    eb.ingest_dir(limit=1)
    assert (d / "submissions.zip").is_file()


def test_ingest_dir_keeps_a_zip_whose_ingest_raised(rawstore_tmp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "OUTPUT_DIR", tmp_path)
    d = eb.bulk_dir()
    (d / "submissions.zip").write_bytes(b"this is not a zip (a truncated download)")
    with pytest.raises(zipfile.BadZipFile):
        eb.ingest_dir()
    assert (d / "submissions.zip").read_bytes().startswith(b"this is not a zip")


def test_ingest_dir_with_delete_false_never_deletes(rawstore_tmp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "OUTPUT_DIR", tmp_path)
    d = eb.bulk_dir()
    _zip(d, "submissions.zip", _submissions())
    eb.ingest_dir(delete=False)
    assert (d / "submissions.zip").is_file()


def test_the_cli_keeps_the_zip_when_asked_to_stop_early(rawstore_tmp_db, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(eb, "OUTPUT_DIR", tmp_path)
    d = eb.bulk_dir()
    _zip(d, "submissions.zip", _submissions())
    assert eb.main(["--ingest", "--limit", "1"]) == 0
    assert (d / "submissions.zip").is_file()
    eb.main(["--ingest"])
    assert not (d / "submissions.zip").exists()       # the full ingest then removes it


def test_the_module_doc_says_when_a_zip_is_deleted():
    doc = " ".join((eb.__doc__ or "").split())
    assert "only after" in doc and "never" in doc
