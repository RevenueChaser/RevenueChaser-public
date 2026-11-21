"""v2 step 6 (#1264): the door's two requirement lists, its compose service and its image, as rules.

These are the things that cannot be caught by running the door in CI, because they are about the box: a container
that binds ``0.0.0.0`` on the host network opens 8100 to the home network; one without a cgroup parent is not
capped by ``life-rc-v2.slice`` however carefully that file is written (home-server ``docs/rc-v2-door.md``); and two
requirement files naming one package at different versions mean CI tested a version the box does not run.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOOR_REQS = REPO / "v2" / "door" / "requirements.txt"
REPO_REQS = REPO / "requirements.txt"
COMPOSE = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
DOCKERFILE = (REPO / "v2" / "door" / "Dockerfile").read_text(encoding="utf-8")
# The instruction lines alone, with every ``#`` comment dropped: a rule about what the image *runs* must not be
# satisfied or broken by prose. The comment above ``CMD`` names ``0.0.0.0`` precisely to say why it is not used,
# and a check over the whole file would read that explanation as the offence.
DOCKERFILE_STEPS = "\n".join(
    line for line in DOCKERFILE.splitlines() if not line.lstrip().startswith("#")
)
DOC = (REPO / "docs" / "v2" / "door.md").read_text(encoding="utf-8")

_PIN = re.compile(r"^([A-Za-z0-9._-]+)\s*(==|>=)\s*([0-9][^\s;#]*)", re.M)


def _pins(path: Path) -> dict[str, tuple[str, str]]:
    return {m.group(1).lower(): (m.group(2), m.group(3)) for m in _PIN.finditer(path.read_text(encoding="utf-8"))}


def test_the_doors_requirements_are_pinned_exactly():
    """``v2/README.md`` decision 6: a build reproducible from the merged SHA, so no ``>=`` in the image's list."""
    loose = [name for name, (op, _) in _pins(DOOR_REQS).items() if op != "=="]
    assert not loose, f"the image's requirements must pin exactly: {loose}"


def test_the_two_requirement_lists_never_disagree_about_a_version():
    """CI installs the repository's list; the image installs the door's. A package in both must agree.

    The repository's may be a floor (``>=``) the door's exact pin satisfies, never a floor above it.
    """
    door, repo = _pins(DOOR_REQS), _pins(REPO_REQS)
    for name, (_, exact) in door.items():
        if name not in repo:
            continue
        op, version = repo[name]
        if op == "==":
            assert version == exact, f"{name}: repository pins {version}, the door's image {exact}"
        else:
            assert _parts(exact) >= _parts(version), f"{name}: the door's {exact} is below the repository's {version}"


def _parts(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", version)[:3])


def test_every_package_the_door_imports_is_in_the_images_list():
    """A door that imports a package the image does not install starts in CI and dies on the box."""
    source = "\n".join((REPO / "v2" / "door" / f).read_text(encoding="utf-8")
                       for f in ("app.py", "boards.py", "health.py", "config.py", "proxy.py",
                                 "writelog.py"))
    installed = set(_pins(DOOR_REQS))
    for third_party in ("fastapi", "starlette", "redis", "uvicorn"):
        if re.search(rf"^\s*(import|from)\s+{third_party}\b", source, re.M):
            # starlette arrives with fastapi and is not named separately in a requirements file.
            assert third_party in installed or third_party == "starlette", third_party


def test_the_container_binds_loopback_and_not_every_interface():
    """On the host network ``0.0.0.0`` would open 8100 to the home network, which the ports check calls unknown."""
    assert '"--host", "127.0.0.1"' in DOCKERFILE_STEPS
    assert "0.0.0.0" not in DOCKERFILE_STEPS


def test_the_image_installs_the_doors_list_and_not_the_repositorys():
    assert "v2/door/requirements.txt" in DOCKERFILE
    assert not re.search(r"^COPY requirements\.txt", DOCKERFILE, re.M)
    assert "-r /tmp/door-requirements.txt" in DOCKERFILE


def test_the_image_runs_as_a_user_that_is_not_root():
    assert re.search(r"^USER door$", DOCKERFILE, re.M)


def test_the_web_files_are_built_in_the_image_and_never_on_homesrv():
    """``v2/README.md`` decision 6: homesrv installs no Node. The only npm is a builder stage."""
    assert "FROM node:22-alpine AS web" in DOCKERFILE
    assert "npm ci --ignore-scripts" in DOCKERFILE
    assert "COPY --from=web /build/dist/ v2/web/dist/" in DOCKERFILE


def _door_service() -> str:
    """The ``door:`` block of docker-compose.yml, by indentation."""
    lines = COMPOSE.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "door:")
    out = []
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith("    "):
            break
        out.append(line)
    return "\n".join(out)


def _door_steps() -> str:
    """The ``door:`` block with every ``#`` comment line dropped: what the service declares, without the prose."""
    return "\n".join(line for line in _door_service().splitlines() if not line.lstrip().startswith("#"))


def test_the_door_joins_the_slice_that_caps_its_memory():
    """A unit calling ``docker compose up`` does not cap the container; the cgroup parent is what binds the slice."""
    assert "cgroup_parent: life-rc-v2.slice" in _door_service()


def test_the_door_runs_on_the_host_network():
    assert "network_mode: host" in _door_service()
    assert "ports:" not in _door_service(), "a ports mapping is meaningless on the host network"


def test_the_doors_only_mount_is_the_artifacts_folder_and_it_is_read_only():
    service = _door_service()
    mounts = [line.strip(" -\"") for line in service.splitlines() if ":/data/" in line or ":/srv/" in line]
    assert mounts, "the door needs the artifacts folder"
    assert all(m.endswith(":ro") for m in mounts), mounts
    assert "RC_CACHE_DIR" in service
    assert "read_only: true" in service


def test_the_door_can_read_the_artifacts_root_it_is_given():
    """The image's own uid does not exist on the host, so reading the mount takes the owning group.

    Measured on homesrv 21 Nov 2026: the container runs as ``uid=100(door)`` and the artifacts root is
    ``1001:1001`` mode ``2770``, so ``ls /data/cache`` was "Permission denied", the ``artifacts`` probe was red and
    ``/api/v1/health`` answered 503 while ``/api/v1/version`` was fine. The service therefore joins that gid as a
    supplementary group. It must not get there by running as root or as the dashboard's own user instead: the
    mount stays ``:ro``, so the group's write bit is unusable, and that is the whole point of the narrow fix.
    """
    service = _door_service()
    assert "group_add:" in service, "the door cannot read a 2770 artifacts root without its group"
    assert "RC_ARTIFACTS_GID" in service, "the gid is a per-host value, not a constant in the image"
    # The instruction lines alone. A rule about what the service *is granted* must not be broken by prose: the
    # comment above ``group_add`` says the container runs as an "unprivileged" user, and a check over the whole
    # block reads that explanation as the offence. (It did, on the first push of this test.)
    steps = _door_steps()
    assert "user: root" not in steps and 'user: "0' not in steps
    assert "privileged" not in steps


def test_the_real_store_is_never_reachable_from_the_container():
    """``core/config.py`` creates all four roots at import; the two the door does not use point at the tmpfs."""
    service = _door_service()
    assert "RC_STORE_DIR: /tmp/" in service
    assert "RC_EDGAR_DOCS_DIR: /tmp/" in service
    assert ".store" not in service


def test_the_doc_states_the_values_the_code_owns():
    """The repository's rule: a doc that states a value the code owns is compared against the code."""
    from RevenueChaser.v2.door import config
    assert f"{config.PROBE_BUDGET_S:g} s" in DOC.replace("**", ""), "the probe budget in the doc is not the code's"
    assert config.API_PREFIX in DOC
    port = re.search(r'"--port", "(\d+)"', DOCKERFILE).group(1)
    assert f"127.0.0.1:{port}" in DOC, f"the doc does not name the port the image binds ({port})"
