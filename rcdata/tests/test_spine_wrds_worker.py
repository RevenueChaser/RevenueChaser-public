"""``wrds_worker.py`` as a real subprocess under this interpreter, with a stub ``wrds`` package on PYTHONPATH (no
network): one login for several queries, chunked answers streamed whole to gzip JSON lines, a failed query answered
while the connection stays, and a failed login answered before the worker ends."""
from __future__ import annotations

import gzip
import json
import sys
from datetime import date

import pytest

from revenuechaser.rcdata.build.spine import wrds

STUB = '''
import datetime, json, os, pandas as pd
LOG = os.environ["RC_WRDS_STUB_LOG"]

class Connection:
    def __init__(self, wrds_username=None):
        print("Loading library list...", flush=True)       # what the real wrds.Connection prints on stdout
        with open(LOG, "a") as fh:
            fh.write(json.dumps({"login": wrds_username, "figi_key": "OPENFIGI_API_KEY" in os.environ}) + "\\n")
        if wrds_username == "refused":
            raise RuntimeError("PAM authentication failed for user refused at wrds-pgdata.wharton.upenn.edu")
        if wrds_username == "asks":
            input("Enter your WRDS username: ")             # a prompt: there is no person on this stdin
        print("Done", flush=True)

    def raw_sql(self, sql, chunksize=None, return_iter=False):
        print("running", sql, flush=True)
        if "boom" in sql:
            raise ValueError("relation comp.boom does not exist")
        frames = [pd.DataFrame({"GVKEY": ["001", "002"], "efffrom": [pd.Timestamp("2020-01-02"), pd.NaT],
                                "exchg": [11.0, float("nan")]}),
                  pd.DataFrame({"GVKEY": ["003"], "efffrom": [datetime.date(2021, 3, 4)], "exchg": [14.0]})]
        assert return_iter and chunksize
        return iter(frames)

    def close(self):
        pass
'''


@pytest.fixture
def stub(tmp_path, monkeypatch):
    pkg = tmp_path / "stub" / "wrds"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(STUB, encoding="utf-8")
    log = tmp_path / "logins.jsonl"
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "stub"))
    monkeypatch.setenv("RC_WRDS_STUB_LOG", str(log))
    monkeypatch.setenv(wrds.PYTHON_ENV, sys.executable)
    monkeypatch.setenv("RC_WRDS_NO_TTY", "1")              # a developer's terminal must never become the prompt
    monkeypatch.setenv("OPENFIGI_API_KEY", "must-not-reach-the-worker")
    return tmp_path, log


def _lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(x) for x in fh]


def test_one_login_for_several_queries_and_chunks_streamed_whole(stub, monkeypatch):
    tmp, log = stub
    monkeypatch.setenv("WRDS_USERNAME", "avo")
    w = wrds.Worker()
    try:
        a, b = tmp / "a.jsonl.gz", tmp / "b.jsonl.gz"
        assert w.query("SELECT * FROM comp.sec_idhist", a) == 3
        assert w.query("SELECT * FROM comp.co_hgic", b) == 3
        with pytest.raises(wrds.base.SourceError, match="comp.boom"):
            w.query("SELECT * FROM comp.boom", tmp / "c.jsonl.gz")
        assert w.query("SELECT * FROM comp.company", tmp / "d.jsonl.gz") == 3     # the connection stays
    finally:
        w.close()
    assert _lines(a) == [{"gvkey": "001", "efffrom": "2020-01-02", "exchg": "11"},
                         {"gvkey": "002", "efffrom": None, "exchg": None},
                         {"gvkey": "003", "efffrom": "2021-03-04", "exchg": "14"}]
    assert not (tmp / "c.jsonl.gz").exists() and not list(tmp.glob("*.tmp"))
    assert log.read_text().splitlines() == ['{"login": "avo", "figi_key": false}']   # one login, no foreign keys
    import duckdb
    rows = duckdb.connect().execute(wrds.raw_rows(a, [("gvkey", "TEXT"), ("efffrom", "DATE"),
                                                      ("exchg", "INTEGER")])).fetchall()
    assert rows == [("001", date(2020, 1, 2), 11), ("002", None, None), ("003", date(2021, 3, 4), 14)]


def test_a_failed_login_is_answered_and_the_worker_ends(stub, monkeypatch):
    tmp, _ = stub
    monkeypatch.setenv("WRDS_USERNAME", "refused")
    w = wrds.Worker()
    try:
        with pytest.raises(wrds.LoginFailed, match="PAM authentication failed") as e:
            w.query("SELECT 1", tmp / "a.jsonl.gz")
        with pytest.raises(wrds.LoginFailed, match="gone|ended"):
            w.query("SELECT 1", tmp / "b.jsonl.gz")
    finally:
        w.close()
    assert w.proc.returncode == 2
    assert "wharton" not in str(e.value) and "refused" not in str(e.value).split(":", 1)[1]   # no user, no host


def test_a_prompt_with_no_person_is_a_failed_login_not_a_hang(stub, monkeypatch):
    tmp, _ = stub
    monkeypatch.setenv("WRDS_USERNAME", "asks")
    w = wrds.Worker()
    try:
        with pytest.raises(wrds.LoginFailed, match="EOFError"):
            w.query("SELECT 1", tmp / "a.jsonl.gz")
    finally:
        w.close()


def test_a_line_out_of_protocol_kills_the_worker_and_is_a_failed_login(stub, monkeypatch, tmp_path):
    """Whatever reaches the protocol pipe that is not an answer ends the worker: never read past it."""
    monkeypatch.setenv("WRDS_USERNAME", "avo")
    w = wrds.Worker()
    import io
    w.proc.stdout = io.StringIO("Loading library list...\n{\"ok\": true, \"rows\": 1}\n")
    try:
        with pytest.raises(wrds.LoginFailed, match="out of protocol"):
            w.query("SELECT 1", tmp_path / "a.jsonl.gz")
        with pytest.raises(wrds.LoginFailed):
            w.query("SELECT 1", tmp_path / "b.jsonl.gz")
    finally:
        w.close()


def test_no_user_name_is_a_failed_login_before_the_worker_starts(monkeypatch):
    monkeypatch.delenv("WRDS_USERNAME", raising=False)
    monkeypatch.setenv(wrds.PYTHON_ENV, sys.executable)
    with pytest.raises(wrds.LoginFailed, match="WRDS_USERNAME"):
        wrds.Worker()


def test_the_worker_does_not_import_the_revenuechaser_package():
    text = wrds.WORKER.read_text(encoding="utf-8")
    assert "revenuechaser" not in text.split('"""', 2)[2] and "import wrds" in text


def test_an_error_masks_the_user_name_as_a_word_not_inside_other_words(monkeypatch):
    """Delta-2 N4: user "ab" is masked where it stands alone, not inside "table" or "abc"."""
    from revenuechaser.rcdata.build.spine import wrds_worker
    monkeypatch.setenv("WRDS_USERNAME", "ab")
    text = wrds_worker._error(RuntimeError('role "ab" cannot read table abc; user ab'))
    assert text == 'RuntimeError: role "<user>" cannot read table abc; user <user>'


def test_the_worker_env_keeps_the_tls_and_library_paths_and_drops_other_keys(monkeypatch):
    """Delta-2 N2: the server's PostgreSQL TLS may need SSL_CERT_FILE / SSL_CERT_DIR / LD_LIBRARY_PATH; no other
    key of the builder reaches the third-party venv."""
    for k, v in {"SSL_CERT_FILE": "/etc/ssl/c.pem", "SSL_CERT_DIR": "/etc/ssl/certs", "LD_LIBRARY_PATH": "/opt/lib",
                 "OPENFIGI_API_KEY": "k", "PGSSLMODE": "require"}.items():
        monkeypatch.setenv(k, v)
    env = wrds.worker_env()
    assert {"SSL_CERT_FILE", "SSL_CERT_DIR", "LD_LIBRARY_PATH", "PGSSLMODE"} <= set(env)
    assert "OPENFIGI_API_KEY" not in env


def test_an_error_is_masked_before_it_is_cut_and_whatever_the_case(monkeypatch):
    """Delta-3 nit 4: a name across the 300-character cut leaves no part of itself; "SecretUser" is masked too."""
    from revenuechaser.rcdata.build.spine import wrds_worker
    monkeypatch.setenv("WRDS_USERNAME", "secretuser")
    text = wrds_worker._error(RuntimeError("x" * 280 + " secretuser can not log in"))
    assert len(text) <= 300 and "secre" not in text
    assert wrds_worker._error(RuntimeError("role SecretUser denied")) == "RuntimeError: role <user> denied"


# ── #1574: the answer is read through a server-side cursor, not pulled whole into the client ──────────────────
# These run the worker's own functions in this process with a stand-in connection: the subprocess tests above
# cover the ``raw_sql`` path end to end, and no SQLAlchemy or database is needed to pin the decisions here.

class _Conn:
    """A SQLAlchemy connection as ``_stream`` uses one: options recorded, a transaction that must be open."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.options, self.closed, self.in_tx, self.tx_closed = {}, False, False, False

    def execution_options(self, **kw):
        self.options.update(kw)
        return self

    def begin(self):
        conn = self

        class _Tx:
            def __enter__(self):
                conn.in_tx = True
                return self

            def __exit__(self, *exc):
                conn.in_tx, conn.tx_closed = False, True
                return False

        return _Tx()

    def close(self):
        self.closed = True


class _Engine:
    def __init__(self, conn):
        self.conn, self.connects = conn, 0

    def connect(self):
        self.connects += 1
        return self.conn


class _Wrds:
    """``wrds.Connection``: ``connection`` is the shared SQLAlchemy connection, which carries ``engine``."""

    def __init__(self, conn):
        self.connection = type("_Shared", (), {"engine": _Engine(conn)})()
        self.raw_sql_calls = []

    def raw_sql(self, sql, chunksize=None, return_iter=False):
        self.raw_sql_calls.append(sql)
        return iter([[{"GVKEY": "001"}]])


@pytest.fixture
def worker_module():
    from revenuechaser.rcdata.build.spine import wrds_worker
    return wrds_worker


def test_the_read_asks_for_a_server_side_cursor_on_a_connection_of_its_own(worker_module, monkeypatch, tmp_path):
    """The whole point of #1574: ``stream_results`` is asked for, on a fresh connection inside a transaction.

    The engine is AUTOCOMMIT, under which a psycopg2 named cursor dies at the end of each statement, so the read
    must hold a transaction; and it must not change the isolation level of the shared connection, so it opens one
    of its own and closes it again.
    """
    conn = _Conn(chunks=[[{"GVKEY": "001"}], [{"GVKEY": "002"}]])
    con = _Wrds(conn)
    seen = {}

    def fake_chunks(c, sql):
        seen["conn"], seen["sql"], seen["in_tx"] = c, sql, c.in_tx
        return iter(c.chunks)

    monkeypatch.setattr(worker_module, "_read_sql_chunks", fake_chunks)
    out = tmp_path / "a.jsonl.gz"
    assert worker_module._write(con, "SELECT * FROM crsp.dsf_v2", str(out)) == 2

    assert conn.options == {"isolation_level": "READ COMMITTED", "stream_results": True}
    assert con.connection.engine.connects == 1 and seen["conn"] is conn
    assert seen["in_tx"] is True, "a named cursor under AUTOCOMMIT needs a transaction held open for the read"
    assert conn.tx_closed and conn.closed, "the read's own connection is closed again"
    assert con.raw_sql_calls == [], "raw_sql pulls the whole result set: it must not be the normal path"
    assert _lines(out) == [{"gvkey": "001"}, {"gvkey": "002"}]


def test_the_package_answers_where_there_is_no_cursor_to_be_had(worker_module, monkeypatch, tmp_path):
    """The cursor is an optimisation, never the reason a fetch fails, in both ways it can be absent.

    A driver that refuses it at the first fetch, and a ``wrds`` whose connection is not a SQLAlchemy one, both
    fall back to the package's own read and answer exactly as before #1574.
    """
    conn = _Conn(chunks=[])
    refused = _Wrds(conn)

    def refuse(c, sql):
        def gen():
            raise RuntimeError('cursor "c_1" does not exist')
            yield  # pragma: no cover
        return gen()

    monkeypatch.setattr(worker_module, "_read_sql_chunks", refuse)
    out = tmp_path / "b.jsonl.gz"
    assert worker_module._write(refused, "SELECT 1", str(out)) == 1
    assert refused.raw_sql_calls == ["SELECT 1"]
    assert _lines(out) == [{"gvkey": "001"}]
    assert conn.closed, "the read's own connection is closed even when its first fetch raised"

    class _NoEngine:
        connection = None

        def __init__(self):
            self.raw_sql_calls = []

        def raw_sql(self, sql, chunksize=None, return_iter=False):
            self.raw_sql_calls.append(sql)
            return iter([[{"GVKEY": "001"}]])

    plain = _NoEngine()
    out2 = tmp_path / "b2.jsonl.gz"
    assert worker_module._write(plain, "SELECT 1", str(out2)) == 1
    assert plain.raw_sql_calls == ["SELECT 1"]
    assert _lines(out2) == [{"gvkey": "001"}]


def test_a_failure_after_the_first_rows_is_raised_and_leaves_no_file(worker_module, monkeypatch, tmp_path):
    """Only the first fetch may fall back; a query that dies mid-stream is the query's own failure."""
    con = _Wrds(_Conn(chunks=[]))

    def die_late(c, sql):
        def gen():
            yield [{"GVKEY": "001"}]
            raise RuntimeError("connection reset")
        return gen()

    monkeypatch.setattr(worker_module, "_read_sql_chunks", die_late)
    out = tmp_path / "c.jsonl.gz"
    with pytest.raises(RuntimeError, match="connection reset"):
        worker_module._write(con, "SELECT 1", str(out))
    assert not out.exists() and not list(tmp_path.glob("*.tmp"))
    assert con.raw_sql_calls == [], "a half-written answer is not retried with the whole-result read"
