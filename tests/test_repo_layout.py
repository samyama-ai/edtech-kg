"""The repo as a published artefact — layout, packaging, and no template left in it.

This repo shipped for a week with `name = "{{KG_SLUG}}-kg"` in `pyproject.toml`,
which made `pip install -e .` fail before it started — step two of the README's
own quick start. Six more files carried template placeholders, `LICENSE` among
them, in a public repo.

None of it was caught because nothing looked at the repo as a thing someone
else installs and reads. These tests do that — edtech-kg#17, #6, #26.
"""

from __future__ import annotations

import ast
import os
import pathlib
import re
import subprocess
import sys
import tempfile
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
        for line in _prose_stripped(body, name):
            for hit in set(placeholder.findall(line)):
                found.append(f"{name}: {hit}")
    assert not found, (
        f"template placeholders still in the repo: {sorted(found)}. This is a "
        f"public repo; a reader sees them before they see anything else.")


def test_a_placeholder_in_a_markdown_heading_is_not_stripped_as_a_comment():
    """The hole the guard had, in the file type most likely to carry one.

    `#` opens a comment in Python and a HEADING in Markdown. Stripping it for
    every file type meant `# The {KG_NAME} Benchmarks` — written with real
    braces — was skipped, in a guard whose own docstring says it still catches
    headings. A placeholder in a heading is the most visible one there is.
    """
    heading = "# The {{%s}} Benchmarks" % "KG_NAME"
    assert _prose_stripped(heading, "benchmarks/README.md") == [heading], (
        "a Markdown heading was stripped as a comment — a placeholder in the "
        "largest text on the page would ship unnoticed")

    # Still stripped where `#` really is a comment, which is the reason the
    # stripping exists: prose ABOUT a placeholder must not trip the guard.
    comment = "# a %s in a comment" % ("{{%s}}" % "KG_NAME")
    assert _prose_stripped(comment, "etl/x.py") == []
    assert _prose_stripped(comment, ".github/workflows/ci.yml") == []

    # And a placeholder in a VALUE is caught in every file type.
    value = 'NAME = "{{%s}}-kg"' % "KG_SLUG"
    assert _prose_stripped(value, "etl/x.py") == [value]


def test_the_package_metadata_is_valid_enough_to_install():
    """`pip install -e .` failed outright: `project.name` must be a PEP 508
    identifier and `{{KG_SLUG}}-kg` is not one, so setuptools rejected the file
    before reading anything else.

    Checked by building the metadata rather than by pattern-matching the name,
    because the ways a pyproject can be invalid are not enumerable — and the
    failure this guards against was a *category* error in one field, not a typo.

    Built IN-PROCESS rather than through `pip install --dry-run`. Even with
    `--no-deps`, an editable install uses build isolation and reaches the index
    to fetch the backend, so the test failed on an offline or network-
    restricted runner for a reason that has nothing to do with the metadata —
    and CI is exactly such a runner. The backend rejects `{{KG_SLUG}}-kg`
    before parse either way, which is the failure this exists to catch.
    """
    from setuptools import build_meta

    with tempfile.TemporaryDirectory() as out:
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            written = build_meta.prepare_metadata_for_build_wheel(out)
        except Exception as exc:  # noqa: BLE001 - the category is the point
            raise AssertionError(
                f"the packaging metadata does not build, so `pip install -e .` "
                f"cannot work — the README tells readers to run it as step "
                f"two: {type(exc).__name__}: {exc}") from exc
        finally:
            os.chdir(cwd)

        metadata = (pathlib.Path(out) / written / "METADATA").read_text(errors="replace")

    name = next((line.split(":", 1)[1].strip() for line in metadata.splitlines()
                 if line.lower().startswith("name:")), None)
    assert name == "edtech-kg", (
        f"the built metadata names this package {name!r}. `project.name` must "
        f"be a PEP 508 identifier — the template's brace-wrapped slug was not, "
        f"and setuptools rejected the file before reading anything else.")


def test_the_declared_dependencies_are_ones_something_imports():
    """The template declared `samyama`, `requests`, `rich`, `click` and
    `fastmcp`. Nothing imported any of them: `click` came from a placeholder
    loader and `fastmcp` from a placeholder MCP server.

    A dependency list nobody needs is its own false claim — it says the package
    cannot run without five things it never used, and it makes the install
    heavier than the code. Optional extras are exempt: `mcp` names `fastmcp`
    deliberately, for a server that is documented as not yet built.

    Both directions are asserted, and the second is the one with teeth going
    forward. With `dependencies = []`, `declared - imported` is empty by
    construction — it passes without examining anything, which is the vacuous
    pass CONTRIBUTING.md names. The converse cannot go vacuous: any
    third-party module the code imports must be declared.

    Distribution names and import names are compared directly. That holds for
    everything here today and is not true in general — `PyYAML` imports as
    `yaml` — so the day they diverge this needs an alias map rather than a
    louder assertion.
    """
    pyproject = (ROOT / "pyproject.toml").read_text()
    block = re.search(r"^dependencies = \[(.*?)\]", pyproject, re.M | re.S)
    assert block, "no dependencies field"
    declared = {re.match(r"[A-Za-z0-9_.-]+", d.strip().strip('"\'')).group(0).lower()
                for d in block.group(1).split(",") if d.strip().strip('"\'')}

    # Parsed, not pattern-matched. The line regex this used to run also
    # matched English: a docstring reading "import the catalogue first" put
    # `the` into the set. That was invisible while the set was only ever
    # subtracted FROM, and became six phantom dependencies the moment it was
    # used in the other direction.
    imported = set()
    for name in tracked():
        if not name.endswith(".py"):
            continue
        try:
            tree = ast.parse((ROOT / name).read_text(errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0].lower() for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0].lower())

    unused = declared - imported
    assert not unused, (
        f"declared but imported by nothing: {sorted(unused)}. Move it to an "
        f"optional extra or drop it.")

    # The direction that stays meaningful when the list is empty.
    first_party = {d.name for d in ROOT.iterdir() if (d / "__init__.py").exists()}
    first_party |= {p.stem for p in ROOT.glob("*.py")} | {"__future__"}
    extras = set()
    for group in re.findall(r"^\w[\w-]* = \[(.*?)\]",
                            pyproject.split("[project.optional-dependencies]")[-1],
                            re.M | re.S):
        for item in group.split(","):
            item = item.strip().strip('"\'')
            if item:
                extras.add(re.match(r"[A-Za-z0-9_.-]+", item).group(0).lower())

    undeclared = sorted(
        imported - set(sys.stdlib_module_names) - first_party - declared - extras)
    assert not undeclared, (
        f"imported but declared nowhere: {undeclared}. An install that "
        f"succeeds and then fails on import is worse than one that refuses.")


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


def _prose_stripped(body: str, name: str) -> list[str]:
    """The lines a placeholder would actually ship in.

    A `{{KG_NAME}}` inside a comment or a docstring is prose ABOUT the
    placeholder, not one — and this repo now carries several such passages,
    because the removal is the thing being explained. The first version of this
    guard flagged all of them, including its own docstring, which made it fail
    on the commit that fixed the defect.

    What it still catches is the case that matters: a placeholder in a value, a
    heading, or anything that executes or gets read. Headings are load-bearing
    in that sentence — see the gating below, which is what makes it true.
    """
    lines = body.splitlines()
    skip = set()
    # Markdown is the exception, and it is the whole of this gate. `#` opens a
    # comment in Python, YAML, TOML and shell, but it opens a HEADING in
    # Markdown — so stripping it everywhere skipped a placeholder sitting in
    # the largest text on the page, in the file type most likely to carry one,
    # inside a guard whose own docstring claims it still catches headings.
    #
    # The cost is that Markdown prose ABOUT a placeholder now trips this. For a
    # public repo that is the safer direction: a false positive is one
    # rewording, a false negative is a template placeholder on the front page.
    if not name.endswith(".md"):
        for i, line in enumerate(lines):
            if line.lstrip().startswith(("#", "//")):
                skip.add(i)
    if name.endswith(".py"):
        try:
            tree = ast.parse(body)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                doc = ast.get_docstring(node, clean=False) if isinstance(
                    node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                           ast.AsyncFunctionDef)) else None
                if doc is None:
                    continue
                first = node.body[0]
                skip.update(range(first.lineno - 1, (first.end_lineno or first.lineno)))
    return [line for i, line in enumerate(lines) if i not in skip]
