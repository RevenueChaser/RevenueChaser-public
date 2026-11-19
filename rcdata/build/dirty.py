"""What changed since the live serving file was built: the dirty-set contract (#446 step 2).

A build on a copy of the live file (``serving.build(kind, base="live")``, step 1) only pays off when it can say
which rows to reload. That answer has two parts, and this module holds both:

- :func:`full_rebuild_reason` — the cases where no dirty set is safe and the kind must be built whole: a live file
  that is missing or built by another serving schema version (``serving.live_version``), or a dataset that says its
  source restated history (``full_rebuild_reason(ctx)``, e.g. a WRDS monthly refresh, SEC republishing a set).
- :func:`of` — one dataset's dirty set, as a :class:`Dirty`. A dataset declares ``dirty(ctx)``; a dataset that
  declares nothing is :data:`ALL`, which is why this PR changes no behaviour: every kind is still built whole.

A dirty set has two axes, because the tables have two shapes (the classification the incremental steps read):
a **cumulative** table only ever gains rows for new source days, so what is dirty is a *range* of days; a
**restated** table can have an old row changed by new data, so what is dirty is a *key* whose whole history is
rebuilt. A third shape, a chosen list (``my_universe``), narrows to neither and is always built whole. ``Dirty``
carries both axes and is "everything" when it carries neither, so a dataset that forgets to narrow gets the slow,
correct answer rather than a silently partial table.

The signal a dataset's ``dirty`` is meant to read is :func:`changed_partitions`: the Parquet files written after
the live file's build stamp (``serving_schema_version.built_at``). A dataset's own job is only to map a partition
to the keys it touches — never to guess what changed inside one. The stamp is written when the build file opens
(``serving._stamp``), before any dataset reads Parquet, so a partition written while a long build runs is newer
than the stamp and comes out dirty on the next build rather than being lost (test
``test_the_build_stamp_is_the_builds_start_not_its_swap``).

The mtime alone reads two cases as clean when they are not — a copy, an rsync or a restore carrying an old mtime
over, and a partition deleted or renamed after the build. So a kind that builds incrementally writes a **manifest**
into its build file (:data:`MANIFEST_TABLE`: every Parquet file of its datasets with its size and mtime, taken
before any dataset reads), and the next build compares the tree with it file by file (:func:`changes`): a file
whose size or mtime differs, a new one and a missing one are all changed. Only a live file built before the
manifest existed falls back to the mtime against ``built_at`` (one build, the first after this landed).

:func:`plan` is what ``base.build_kind_many`` asks: whether the kind builds on a copy of the live file, and if so
each dataset's dirty set. A kind builds incrementally only when **every** one of its datasets declares ``dirty``;
any other kind is built whole exactly as before, and gets no manifest. A whole build is still forced by a serving
schema version bump, a change of the **shared** build code (:func:`shared_fingerprint`), a dataset's own
``full_rebuild_reason`` (a WRDS monthly snapshot), more than :data:`MAX_DIRTY_SHARE` of the files changed (a
re-extract of everything is faster built whole), and ``RC_BUILD_WHOLE=1`` (the lever by hand).

Build code is a rule too — the extraction and the table rules are code, and a change to them restates rows that no
Parquet file marks as changed — but it is not one rule per kind (#814). One fingerprint for the whole kind made the
first pass after **every** deploy rebuild ``ownership/serve`` from scratch: 2,352 s and a 23.8 GB spill, measured on
homesrv on 12 Nov 2026, above the 20 GB cap the build line itself printed. So the file stores one fingerprint per
dataset (:func:`fingerprints`), over the build files that dataset's code *reaches* (:func:`code_files`, the import
graph inside ``rcdata/build``, stopping at the shared files), and a deploy that touches one dataset restates that
dataset's tables only.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import duckdb

from .. import serving
from . import base

@dataclass(frozen=True)
class Dirty:
    """What of a dataset is dirty: day ranges (cumulative tables) and keys (restated tables).

    Carrying neither means everything (:attr:`all`), which is the safe default: a dataset that narrows nothing is
    built whole, as every dataset is today. ``ranges`` are inclusive ``(first, last)`` day pairs.
    """

    ranges: tuple[tuple[date, date], ...] = ()
    keys: frozenset[str] = frozenset()
    clean: bool = False                     # nothing of the dataset changed: neither axis, and not "everything"

    @property
    def all(self) -> bool:
        return not (self.clean or self.ranges or self.keys)


#: Everything is dirty: what a dataset that declares no ``dirty`` returns, so its tables are built from the whole
#: Parquet tree as they are today.
ALL = Dirty()
#: Nothing is dirty: a keyed dataset none of whose partitions changed.
CLEAN = Dirty(clean=True)

#: How far before the stamp a partition still counts as dirty: one second, for a file system that keeps mtimes to
#: the second (``changed_partitions``). Both sides are UTC epoch seconds (``time.time`` and ``st_mtime``).
MTIME_SLACK_S = 1.0


def live_built_at(kind: str) -> float | None:
    """When the live ``kind`` file's build started (its ``built_at`` stamp), or None when there is no stamp.

    None means "nothing known about this file": every partition is then dirty (:func:`changed_partitions`).
    """
    try:
        with serving.open_read(kind) as con:
            rows = con.execute(f"SELECT built_at FROM {serving.VERSION_TABLE} WHERE kind = ?", (kind,)).fetchall()
    except (serving.ServingFileMissing, duckdb.Error):
        return None
    if len(rows) != 1 or rows[0][0] is None:
        return None
    return float(rows[0][0])


def changed_partitions(since: float | None, under: Path | str | None = None) -> list[Path]:
    """The Parquet files under ``under`` (the whole Parquet root by default) written after ``since``, in path order.

    ``since`` None returns every partition: nothing is known about the live file, so nothing can be called clean.
    A missing directory is empty, not an error — a dataset that has never staged anything has no dirty partition.

    The cutoff is ``since`` less :data:`MTIME_SLACK_S`, because a file system (or an rsync) that keeps mtimes to
    the second truncates one written inside the stamp's own second to before it, which would read as clean. The
    slack re-reads a partition now and then; it never calls a written one clean.
    """
    root = Path(under) if under is not None else base.parquet_root()
    if not root.is_dir():
        return []
    files = sorted(p for p in root.rglob("*.parquet") if p.is_file())
    if since is None:
        return files
    cutoff = since - MTIME_SLACK_S
    return [p for p in files if p.stat().st_mtime > cutoff]


def of(ds: Any, ctx: Any) -> Dirty:
    """``ds``'s dirty set: its own ``dirty(ctx)``, else :data:`ALL`.

    A dataset answers with a :class:`Dirty` (or None for "everything"); any other shape is a mistake in that
    dataset and raises here rather than being read as a narrowing, which would serve a partial table.
    """
    step = getattr(ds, "dirty", None)
    if step is None:
        return ALL
    answer = step(ctx)
    if answer is None:
        return ALL
    if not isinstance(answer, Dirty):
        raise TypeError(f"{getattr(ds, 'name', ds)}.dirty returned {type(answer).__name__}, not a Dirty")
    return answer


def full_rebuild_reason(kind: str, datasets: Iterable[Any] | None = None, ctx: Any = None) -> str | None:
    """Why ``kind`` must be built whole, or None when a build on the live copy is safe.

    ``datasets`` defaults to the kind's own (``base.kind_datasets``); a dataset is asked through its optional
    ``full_rebuild_reason(ctx)``, and the first one that answers wins, named in the reason.
    """
    wanted = serving.SERVING_SCHEMA_VERSION[kind]
    if serving.live_version(kind) != wanted:
        return f"no live {kind} file at serving schema version {wanted}"
    if live_built_at(kind) is None:
        return f"the live {kind} file carries no build stamp"
    for ds in (base.kind_datasets(kind) if datasets is None else datasets):
        step = getattr(ds, "full_rebuild_reason", None)
        if step is None:
            continue
        why = step(ctx)
        if why:
            return f"{ds.name}: {why}"
    return None


# ── The incremental build's plan (#446 steps 3 and 7) ─────────────────────────────────────────────────────────

#: The build file's list of the Parquet files it was built from: ``(path, size, mtime)``, the path relative to the
#: Parquet root. Taken before any dataset reads, so a file written during the build is changed next time.
MANIFEST_TABLE = "build_manifest"
#: The fingerprints of the build code the file was built by (:func:`fingerprints`): one row per dataset, plus the
#: shared one under :data:`SHARED`.
RULES_TABLE = "build_rules"
#: More than this share of a kind's Parquet files changed: built whole, which is then faster than deleting most rows.
MAX_DIRTY_SHARE = 0.5
#: ``RC_BUILD_WHOLE=1`` forces a whole build of every kind (the lever by hand).
WHOLE_ENV = "RC_BUILD_WHOLE"


def incremental(datasets: Iterable[Any]) -> bool:
    """Whether a kind of these datasets builds incrementally: every one declares ``dirty`` (and there is one)."""
    datasets = list(datasets)
    return bool(datasets) and all(getattr(d, "dirty", None) is not None for d in datasets)


def dataset_dir(ds: Any) -> Path:
    """``parquet/<source>/<name>`` of dataset ``<source>/<name>``."""
    return base.parquet_root().joinpath(*str(ds.name).split("/", 1))


def read_dirs(ds: Any) -> list[Path]:
    """The Parquet folders ``ds``'s build reads: its own, and those of another kind's dataset it names in
    ``parquet_reads`` (``wrds/prices`` reads the spine's ``wrds/sec_idhist``), so a change there is seen too."""
    root = base.parquet_root()
    return [dataset_dir(ds), *(root.joinpath(*str(n).split("/", 1)) for n in getattr(ds, "parquet_reads", ()))]


def scan(datasets: Iterable[Any]) -> dict[str, tuple[int, float]]:
    """Every Parquet file of ``datasets``: its path relative to the Parquet root, its size and mtime."""
    root = base.parquet_root()
    out: dict[str, tuple[int, float]] = {}
    for folder in dict.fromkeys(f for d in datasets for f in read_dirs(d)):
        if not folder.is_dir():
            continue
        for p in folder.rglob("*.parquet"):
            try:
                st = p.stat()
            except FileNotFoundError:                 # replaced while listed: the next build sees it
                continue
            if p.is_file():
                out[p.relative_to(root).as_posix()] = (int(st.st_size), float(st.st_mtime))
    return dict(sorted(out.items()))


#: The build files every kind's answer depends on, under ``rcdata/build``: a change to one of them can restate any
#: row of any kind, so they are one fingerprint of their own (:data:`SHARED`) and a dataset's code walk stops at
#: them instead of following them into the registry, which imports every dataset there is.
SHARED_FILES = ("__init__.py", "base.py", "dirty.py")
#: The key of the shared fingerprint's row in :data:`RULES_TABLE`; no dataset is named ``""``.
SHARED = ""
#: ``rcdata/build``, the package that holds the dataset code, and its dotted name.
BUILD_ROOT = Path(__file__).resolve().parent
BUILD_PACKAGE = __name__.rsplit(".", 1)[0]


def _module_file(module: str) -> Path | None:
    """The file of ``module`` when it is a module of the build package, None otherwise.

    None is also the answer for a name that is no module at all (``from . import KIND``) and for one outside the
    package (``core.calendar``, ``rcdata.serving``): the walk stops there either way.
    """
    if module != BUILD_PACKAGE and not module.startswith(BUILD_PACKAGE + "."):
        return None
    rest = module[len(BUILD_PACKAGE):].strip(".")
    if not rest:
        return BUILD_ROOT / "__init__.py"
    folder = BUILD_ROOT.joinpath(*rest.split("."))
    for p in (folder.with_name(folder.name + ".py"), folder / "__init__.py"):
        if p.is_file():
            return p
    return None


def _imported(path: Path, module: str) -> list[str]:
    """The module names ``path``'s import statements name, relative ones resolved against ``module``.

    Every ``import`` of the file is read, including one inside a function, because a build reaches that code too.
    A ``from X import a, b`` also offers ``X.a`` and ``X.b``, since a name there may be a submodule;
    :func:`_module_file` sorts out which of them is one.
    """
    is_package = path.name == "__init__.py"
    parts = module.split(".") if is_package else module.split(".")[:-1]
    out: list[str] = []
    for node in ast.walk(ast.parse(path.read_bytes())):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            anchor = ".".join(parts[:len(parts) - (node.level - 1)]) if node.level else ""
            if node.level and not anchor:                       # above the package: nothing of ours
                continue
            head = f"{anchor}.{node.module}" if anchor and node.module else (anchor or node.module or "")
            if head:
                out += [head, *(f"{head}.{a.name}" for a in node.names)]
    return out


def home_modules(ds: Any) -> list[str]:
    """The modules ``ds`` belongs to: the one its class is defined in, and the one that holds the dataset object.

    They are usually the same file, but not always — ``spine/wrds`` defines one class that several of the spine's
    datasets are built from, and each of those lives in a module of its own whose constants (its name, its schema,
    its SQL) are as much its rules as the class is. Both are walked, so neither is missed.
    """
    out = [type(ds).__module__]
    for name, module in list(sys.modules.items()):
        if name in out or _module_file(name) is None:
            continue
        try:
            held = any(value is ds for value in vars(module).values())
        except Exception:                                   # a module that will not be read is not a home
            continue
        if held:
            out.append(name)
    return [name for name in out if _module_file(name) is not None]


def reaches(start: Iterable[str]) -> set[Path]:
    """Every build file the modules ``start`` reach: what they import, on and on, inside ``rcdata/build`` and
    stopping at :data:`SHARED_FILES` (which every dataset reaches, and which the registry would otherwise carry the
    walk back out of into every dataset there is)."""
    shared = {BUILD_ROOT / n for n in SHARED_FILES}
    seen: dict[str, Path] = {}
    queue = list(start)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        found = _module_file(name)
        if found is None or found in shared:
            continue
        seen[name] = found
        queue += _imported(found, name)
    return set(seen.values())


def code_files(ds: Any) -> list[Path]:
    """The files whose bytes are ``ds``'s own build rules: the ones of its own package(s) that its code **reaches**.

    The package is the boundary this has always had — a kind's fingerprint was every Python file in the packages
    that held its datasets — and it stays one here, so this narrows what a code change restates and never widens
    it (#814). A file of another package that a dataset reads (``ownership/common`` names through
    ``spine/security``) is outside it today as it was before; what changes is that a dataset no longer answers for
    the files of its **own** package that its code never reaches: ``ownership/serve`` is not restated by an edit to
    ``ownership/regsho``, which is the 2,352 s rebuild the issue measured.

    Two datasets built from one class, in one module, do share a fingerprint — they share the code, so a change to
    it restates both, which is the answer.

    A dataset whose modules are not in the package at all (a test's stand-in) answers for every build file, which
    is the slow, safe answer rather than a wrong narrow one.
    """
    homes = home_modules(ds)
    if not homes:
        return sorted(BUILD_ROOT.rglob("*.py"))
    folders = {_module_file(name).parent for name in homes}
    return sorted(p for p in reaches(homes) if p.parent in folders)


def _digest(paths: Iterable[Path], *, head: bytes = b"") -> str:
    h = hashlib.sha256()
    h.update(head)
    for p in paths:
        h.update(p.name.encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def shared_fingerprint() -> str:
    """The fingerprint of the code every kind's rows depend on: :data:`SHARED_FILES` and ``rcdata/serving.py``.

    The code that decides what a build on the live copy reloads is a rule too: a fix to it must reach the rows it
    built wrongly, which only a whole build revisits (review of #554).
    """
    paths = [BUILD_ROOT / n for n in SHARED_FILES]
    serving_file = getattr(sys.modules.get(serving.__name__), "__file__", None)
    if serving_file:
        paths.append(Path(serving_file))
    return _digest(sorted(p for p in paths if p.is_file()))


def dataset_fingerprint(ds: Any) -> str:
    """The fingerprint of one dataset's own build code (:func:`code_files`) and of its ``rules_state()`` — a switch
    read from the environment that changes what it serves (``RC_UW_PRELIMINARY``). A change to either restates rows
    that no Parquet file marks as changed."""
    state = getattr(ds, "rules_state", None)
    head = f"{ds.name}={state()}".encode() + b"\0" if state is not None else b""
    return _digest(code_files(ds), head=head)


def fingerprints(datasets: Iterable[Any]) -> dict[str, str]:
    """What :data:`RULES_TABLE` holds: the shared fingerprint under :data:`SHARED`, and one per dataset.

    One fingerprint per kind is what made the first pass after **every** deploy rebuild ``ownership/serve`` whole —
    2,352 s and a 23.8 GB spill, measured on homesrv on 12 Nov 2026 (#814). A deploy that touches one dataset's
    code now restates that dataset's tables and leaves the rest of the kind on its dirty set.
    """
    return {SHARED: shared_fingerprint(), **{d.name: dataset_fingerprint(d) for d in datasets}}


def rules_fingerprint(datasets: Iterable[Any]) -> str:
    """The whole kind's fingerprint: every entry of :func:`fingerprints` in one hash. What the file stores is the
    entries, not this; it is the one number for "did any of this kind's build code change"."""
    h = hashlib.sha256()
    for name, value in sorted(fingerprints(datasets).items()):
        h.update(name.encode() + b"\0" + value.encode() + b"\0")
    return h.hexdigest()


def _live_rows(kind: str, sql: str) -> list[tuple] | None:
    try:
        with serving.open_read(kind) as con:
            return con.execute(sql).fetchall()
    except (serving.ServingFileMissing, duckdb.Error):
        return None


def live_manifest(kind: str) -> dict[str, tuple[int, float]] | None:
    rows = _live_rows(kind, f"SELECT path, size, mtime FROM {MANIFEST_TABLE}")
    return None if rows is None else {p: (int(s), float(m)) for p, s, m in rows}


def live_rules(kind: str) -> dict[str, str] | None:
    """The fingerprints the live file was built by, None when it holds none — a file written before this landed
    carries the one-column table of its day, which this read refuses rather than reading as a changed dataset."""
    rows = _live_rows(kind, f"SELECT dataset, fingerprint FROM {RULES_TABLE}")
    return None if not rows else {str(d): str(f) for d, f in rows}


def changes(kind: str, current: dict[str, tuple[int, float]]) -> tuple[Path, ...] | None:
    """The Parquet files changed since the live file was built, as absolute paths: changed, new or gone.

    Against the live file's manifest when it has one; otherwise (a file built before the manifest) the files of
    ``current`` written after its ``built_at`` — no gone file can be seen then. None when neither is known."""
    root = base.parquet_root()
    live = live_manifest(kind)
    if live is not None:
        out = {p for p, stat in current.items() if live.get(p) != stat} | (set(live) - set(current))
        return tuple(root / p for p in sorted(out))
    since = live_built_at(kind)
    if since is None:
        return None
    cutoff = since - MTIME_SLACK_S
    return tuple(root / p for p, (_, mtime) in current.items() if mtime > cutoff)


def keys_of(changed: Iterable[Path], under: Path, field_name: str = "cik") -> frozenset[str]:
    """The ``<field>=<value>`` values of the changed files under ``under`` (``cik=789019/part-0.parquet``)."""
    out = set()
    for p in changed:
        try:
            rel = p.relative_to(under)
        except ValueError:
            continue
        for part in rel.parts[:-1]:
            if part.startswith(field_name + "="):
                out.add(part.split("=", 1)[1])
    return frozenset(out)


def keyed(ctx: Any, ds: Any, field_name: str = "cik") -> Dirty:
    """A dataset partitioned by ``<field>=<key>``: the keys of its changed partitions, :data:`CLEAN` for none."""
    changed = getattr(ctx, "changed", None)
    if changed is None:
        return ALL
    keys = keys_of(changed, dataset_dir(ds), field_name)
    return Dirty(keys=keys) if keys else CLEAN


@dataclass
class Plan:
    """What ``build_kind_many`` does for an incremental kind: ``reason`` None builds on the live copy."""

    reason: str | None
    dirty: dict[str, Dirty]
    manifest: dict[str, tuple[int, float]]
    rules: dict[str, str]
    changed: tuple[Path, ...] | None
    #: The datasets whose own build code changed since the live file was built (#814): their tables are restated
    #: whole on the live copy, the rest of the kind keeps its dirty set.
    recoded: tuple[str, ...] = ()
    #: The live file had no manifest, so ``changed`` came from its ``built_at``: no gone file is in it, and a
    #: keyed dataset adds the keys the live file serves that have no partition any more (``common.dirty_ciks``).
    fallback: bool = False
    memo: dict[str, Any] = field(default_factory=dict)       # what the datasets of one build share (their keys)

    def note(self) -> str:
        if self.reason:
            return f"built whole: {self.reason}"
        n = len(self.changed or ())
        if "note" in self.memo:                         # a kind that words its own dirty set (``prices``)
            return f"built on the live file: {n} Parquet file(s) changed, {self.memo['note']}"
        keys = self.memo.get("ciks")
        if keys is None:
            keys = set().union(*(d.keys for d in self.dirty.values())) if self.dirty else set()
        return (f"built on the live file: {n} Parquet file(s) changed, {len(keys)} key(s) dirty"
                + (f", restated for new build code: {', '.join(self.recoded)}" if self.recoded else ""))


def plan(kind: str, ctx: Any, datasets: Iterable[Any] | None = None) -> Plan | None:
    """The build plan of ``kind``; None when the kind does not build incrementally (built whole, as before)."""
    datasets = list(base.kind_datasets(kind) if datasets is None else datasets)
    if not incremental(datasets):
        return None
    current = scan(datasets)
    rules = fingerprints(datasets)
    fallback = live_manifest(kind) is None
    changed = changes(kind, current)
    ctx.changed = changed
    reason = None
    if os.getenv(WHOLE_ENV, "").strip() == "1":
        reason = f"{WHOLE_ENV}=1"
    if reason is None:
        reason = full_rebuild_reason(kind, datasets, ctx)
    held = live_rules(kind)
    audited = audit_dirty(kind, datasets)
    recoded: tuple[str, ...] = ()
    if reason is None and held is not None:
        # A live file built before the fingerprints existed is trusted once: it was built by the code just before
        # them. The shared code reaches every row of every kind, so only that one is still a whole build (#814);
        # a dataset whose own code changed has its tables restated and leaves the others their dirty set.
        if held.get(SHARED) != rules[SHARED]:
            reason = f"the shared build code changed since the live {kind} file was built"
        else:
            recoded = tuple(d.name for d in datasets if held.get(d.name) != rules[d.name])
    if reason is None and changed is None:
        reason = f"nothing is known of what the live {kind} file was built from"
    if reason is None and current and len(changed) > MAX_DIRTY_SHARE * len(current):
        reason = f"{len(changed)} of {len(current)} Parquet files changed"
    sets: dict[str, Dirty] = {}
    if reason is None:
        for d in datasets:
            # A recoded dataset is everything of itself on purpose, which its build reloads table by table; the
            # guard below is for a keyed dataset that could not say what changed, which is not an answer.
            sets[d.name] = ALL if d.name in recoded else of(d, ctx)
            if sets[d.name].all and getattr(d, "dirty_keyed", False) and d.name not in recoded:
                reason = f"{d.name}: no narrower dirty set"
                sets = {}
                break
    if reason is None:
        # A key an earlier audit found a difference for is dirty until it is rebuilt (#446 step 5).
        for d in datasets:
            extra = audited.get(d.name) or frozenset()
            if extra and d.name in sets and not sets[d.name].all:
                sets[d.name] = Dirty(ranges=sets[d.name].ranges, keys=sets[d.name].keys | extra)
    if reason is not None:
        recoded = ()
    return Plan(reason, sets, current, rules, changed, recoded, fallback)


def audit_dirty(kind: str, datasets: Iterable[Any]) -> dict[str, frozenset[str]]:
    """Per dataset, the keys an earlier audit of one of its tables found a difference for (``audit.DIRTY``).

    Empty for a live file that has no such table, which is every file built before the audit landed."""
    from . import audit
    try:
        with serving.open_read(kind) as con:
            return {d.name: audit.dirty_keys(con, getattr(d, "tables", ())) for d in datasets}
    except (serving.ServingFileMissing, duckdb.Error):
        return {}


def write_manifest(con: duckdb.DuckDBPyConnection, p: Plan) -> None:
    """Write ``p``'s manifest and rules fingerprint into the build file (over what a live copy carried)."""
    con.execute(f"CREATE OR REPLACE TABLE {MANIFEST_TABLE} (path TEXT, size BIGINT, mtime DOUBLE)")
    if p.manifest:
        paths = list(p.manifest)
        con.execute(f"INSERT INTO {MANIFEST_TABLE} SELECT unnest(?), unnest(?), unnest(?)",
                    (paths, [p.manifest[x][0] for x in paths], [p.manifest[x][1] for x in paths]))
    con.execute(f"CREATE OR REPLACE TABLE {RULES_TABLE} (dataset TEXT, fingerprint TEXT)")
    names = sorted(p.rules)
    con.execute(f"INSERT INTO {RULES_TABLE} SELECT unnest(?), unnest(?)",
                (names, [p.rules[n] for n in names]))
