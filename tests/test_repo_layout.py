"""The repo as a published artefact — layout, packaging, and no template left in it.

This repo shipped for a week with `name = "{{KG_SLUG}}-kg"` in `pyproject.toml`,
which made `pip install -e .` fail before it started — step two of the README's
own quick start. Six more files carried template placeholders, `LICENSE` among
them, in a public repo.

None of it was caught because nothing looked at the repo as a thing someone
else installs and reads. These tests do that — edtech-kg#17, #6, #26.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The layout every `*-kg` repo shares, so that anyone who has seen one can
# navigate this one without being told.
EXPECTED_DIRS = ("etl", "schema", "docs", "benchmarks", "mcp_server", "demo", "tests")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return [n for n in out.stdout.split("\0") if n]


def test_no_tracked_file_still_carries_a_template_placeholder():
    """`{{KG_NAME}}`, `{{KG_SLUG}}`, `{{YEAR}}` — the repo template's markers.

    Eight files still held one, including `LICENSE`, whose copyright year was
    literally `{{YEAR}}`. Matched as `{{IDENTIFIER}}` rather than as a list of
    the three known names, because the template can add a fourth and the point
    is that no placeholder ships, not that these three do not.

    f-strings produce `{{` legitimately, so the pattern requires the closing
    `}}` with nothing but an upper-case identifier between — which no f-string
    brace-escape looks like.
    """
    placeholder = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")
    found = []
    for name in tracked():
        path = ROOT / name
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for hit in set(placeholder.findall(body)):
            found.append(f"{name}: {hit}")
    assert not found, (
        f"template placeholders still in the repo: {sorted(found)}. This is a "
        f"public repo; a reader sees them before they see anything else.")


def test_the_package_metadata_is_valid_enough_to_install():
    """`pip install -e .` failed outright: `project.name` must be a PEP 508
    identifier and `{{KG_SLUG}}-kg` is not one, so setuptools rejected the file
    before reading anything else.

    Checked by building the metadata rather than by pattern-matching the name,
    because the ways a pyproject can be invalid are not enumerable — and the
    failure this guards against was a *category* error in one field, not a typo.
    """
    out = subprocess.run([sys.executable, "-m", "pip", "install", "-e", ".", "--dry-run",
                          "--no-deps", "--quiet"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, (
        f"`pip install -e .` cannot resolve this package — the README tells "
        f"readers to run it as step two:\n{out.stderr[-1200:]}")


def test_the_declared_dependencies_are_ones_something_imports():
    """The template declared `samyama`, `requests`, `rich`, `click` and
    `fastmcp`. Nothing imported any of them: `click` came from a placeholder
    loader and `fastmcp` from a placeholder MCP server.

    A dependency list nobody needs is its own false claim — it says the package
    cannot run without five things it never used, and it makes the install
    heavier than the code. Optional extras are exempt: `mcp` names `fastmcp`
    deliberately, for a server that is documented as not yet built.
    """
    pyproject = (ROOT / "pyproject.toml").read_text()
    block = re.search(r"^dependencies = \[(.*?)\]", pyproject, re.M | re.S)
    assert block, "no dependencies field"
    declared = {re.match(r"[A-Za-z0-9_.-]+", d.strip().strip('"\'')).group(0).lower()
                for d in block.group(1).split(",") if d.strip().strip('"\'')}

    imported = set()
    for name in tracked():
        if not name.endswith(".py"):
            continue
        for line in (ROOT / name).read_text(errors="replace").splitlines():
            found = re.match(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", line)
            if found:
                imported.add(found.group(1).lower())

    unused = declared - imported
    assert not unused, (
        f"declared but imported by nothing: {sorted(unused)}. Move it to an "
        f"optional extra or drop it.")


@pytest.mark.parametrize("name", EXPECTED_DIRS)
def test_the_shared_layout_is_present(name):
    """Same seven directories as every sibling `*-kg` repo."""
    assert (ROOT / name).is_dir(), f"{name}/ is missing from the shared layout"


@pytest.mark.parametrize("name", EXPECTED_DIRS)
def test_no_directory_in_the_layout_is_silently_empty(name):
    """An empty directory reads as "nothing to do here", which is the opposite
    of what an empty one means. `benchmarks/` and `mcp_server/` hold nothing but
    a README today, and each README says so and names the issue tracking it —
    that is the honest state, and it is not the same as being absent.
    """
    entries = [p for p in (ROOT / name).iterdir() if p.name != "__pycache__"]
    assert entries, f"{name}/ is empty — say what lands there, or remove it"


def test_the_contributing_notes_carry_the_rules_that_cost_rounds():
    """#26 asked for the PR standard in writing. These four are the ones whose
    absence is measurable in this repo's own history, so a CONTRIBUTING that
    omits any of them is decorative."""
    doc = (ROOT / "CONTRIBUTING.md").read_text(errors="replace")
    flat = " ".join(doc.split()).lower()
    for phrase, why in (
        ("500", "the file-size limit review enforces"),
        ("closes #", "the only thing that closes an issue on merge"),
        ("red", "breaking your own fix to see a test fail"),
        ("engine", "which engine build the figures were measured against"),
    ):
        assert phrase in flat, f"CONTRIBUTING.md does not cover {why}"
