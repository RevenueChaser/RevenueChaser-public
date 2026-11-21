"""v2 step 7b (#1303): the design contract is one file, and it cannot drift from what it describes.

`v2/design/CONTRACT.md` is what avo approved: one versioned design for both surfaces (web and the Android app).
Two things make a contract file useless over time — a token value that no longer matches the token file the build
actually reads, and a component list that `parity.json` has quietly diverged from. Both are checked here, over
**source** (the contract, the token file, the parity file), never over a list kept inside this test.

Contract section 13 states these four checks; this module is them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

V2 = Path(__file__).resolve().parents[1]
CONTRACT = V2 / "design" / "CONTRACT.md"
PARITY = V2 / "parity.json"
TOKENS = V2 / "web" / "src" / "theme" / "tokens.css"


@pytest.fixture(scope="module")
def contract() -> str:
    return CONTRACT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parity() -> dict:
    return json.loads(PARITY.read_text(encoding="utf-8"))


def _section(text: str, start: str, end: str) -> str:
    """The body between two headings. Raises rather than returning an empty string on a renamed heading."""
    head = text.index(start)
    tail = text.index(end, head)
    return text[head:tail]


def _css_block(css: str, selector: str) -> dict[str, str]:
    i = css.index(selector)
    open_brace = css.index("{", i)
    close_brace = css.index("}", open_brace)
    body = css[open_brace:close_brace]
    return {k: v.strip() for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;}]+)", body)}


def _contract_rows(text: str, section_start: str, section_end: str, columns: int) -> list[tuple[str, ...]]:
    """Every data row of the markdown tables in a section, as tuples of its first `columns` cells."""
    rows: list[tuple[str, ...]] = []
    for line in _section(text, section_start, section_end).splitlines():
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < columns or cells[0] in {"Token", "id"}:
            continue
        rows.append(tuple(cells[:columns]))
    return rows


def test_the_contract_and_the_parity_seed_exist():
    """Both files are the deliverable of step 7b; steps 8 and 18 read them."""
    assert CONTRACT.is_file(), CONTRACT
    assert PARITY.is_file(), PARITY


def test_contract_version_is_the_same_in_both_files(contract, parity):
    stated = re.search(r"contract_version:\s*(\d+)", contract)
    assert stated, "the contract states no contract_version"
    assert int(stated.group(1)) == parity["contract_version"]
    assert parity["contract"] == "v2/design/CONTRACT.md"


def test_every_colour_token_in_the_contract_has_the_value_the_token_file_gives_it(contract):
    """Section 2.2 quotes the token file. A value edited in one place and not the other fails here."""
    css = TOKENS.read_text(encoding="utf-8")
    dark = _css_block(css, ":root{")
    light = _css_block(css, ':root[data-theme="light"]')
    rows = _contract_rows(contract, "### 2.2 Colour tokens", "### 2.3 Two notes", 3)
    assert len(rows) == len(light), (len(rows), len(light))
    for name, dark_value, light_value in rows:
        token = name.strip("`")
        assert token in dark and token in light, token
        assert dark_value.strip("`") == dark[token], token
        assert light_value.strip("`") == light[token], token


def test_the_contract_omits_no_colour_token_the_token_file_defines(contract):
    css = TOKENS.read_text(encoding="utf-8")
    light = _css_block(css, ':root[data-theme="light"]')
    named = {name.strip("`") for name, _, _ in _contract_rows(contract, "### 2.2 Colour tokens", "### 2.3 Two notes", 3)}
    assert set(light) - named == set()


def test_every_scale_token_in_the_contract_has_the_value_the_token_file_gives_it(contract):
    css = TOKENS.read_text(encoding="utf-8")
    dark = _css_block(css, ":root{")
    light = _css_block(css, ':root[data-theme="light"]')
    scale = {k: v for k, v in dark.items() if k not in light}
    rows = _contract_rows(contract, "### 2.1 Scale tokens", "### 2.2 Colour tokens", 2)
    assert len(rows) == len(scale), (len(rows), len(scale))
    for name, value in rows:
        token = name.strip("`")
        assert token in scale, token
        assert value.strip("`") == scale[token], token


def test_the_parity_file_is_seeded_from_the_contracts_component_list(contract, parity):
    """Section 9 is the list step 8 builds and step 18 implements; `parity.json` is that list, not another one."""
    rows = _contract_rows(contract, "## 9. The component list", "## 10. The chart contract", 3)
    assert len(rows) >= 30, len(rows)
    in_contract = {r[0].strip("`"): (r[1].strip("`"), r[2].strip("`")) for r in rows}
    in_parity = {c["id"]: (c["web"], c["android"]) for c in parity["components"]}
    assert in_parity == in_contract


def test_no_component_is_web_only(parity):
    """The reason the seed exists: a component with nothing on the phone is a contract gap, found before the APK."""
    assert [c["id"] for c in parity["components"] if not c.get("android", "").strip()] == []
    assert [c["id"] for c in parity["components"] if not c.get("web", "").strip()] == []


def test_every_component_has_a_distinct_id_and_a_distinct_counterpart(parity):
    ids = [c["id"] for c in parity["components"]]
    assert len(ids) == len(set(ids))
    android = [c["android"] for c in parity["components"]]
    assert len(android) == len(set(android))


def test_the_contract_states_the_touch_sizes_of_both_surfaces(contract):
    """Section 5 is the one place a size is stated for web and for the phone; a screen never decides its own."""
    web, phone = _section(contract, "### 5.1 Web", "## 6. The frame").split("### 5.2 Android")
    assert "44 px" in web and "36 px" in web  # the target, and avo's bookmark exception
    assert "36 dp" in phone and "48 dp" in phone and "411 × 806 dp" in phone
