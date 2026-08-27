"""The repo as a published artefact — layout, packaging, and no template left in it.

This repo shipped for a week with `name = "{{KG_SLUG}}-kg"` in `pyproject.toml`,
which made `pip install -e .` fail before it started — step two of the README's
own quick start. More files carried template placeholders, `LICENSE` among
them, in a public repo.

None of it was caught because nothing looked at the repo as a thing someone
else installs and reads. These tests do that — edtech-kg#17, #6, #26.
"""

from __future__ import annotations

import ast
import os
import tomllib
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


#: Read from `pyproject.toml`, never restated. A second copy of this list is
#: how the packaging test comes to agree with itself rather than with the file
#: that decides what ships.
CONFIGURED_PACKAGES = tomllib.loads(
    (ROOT / "pyproject.toml").read_text(encoding="utf-8")
)["tool"]["setuptools"]["packages"]["find"]["include"]


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
        # `os.chdir` is process-global, so it changes the working directory for
        # every other test in the run. The restore is in a `finally` for that
        # reason — a raise here would otherwise leave the whole suite pointed
        # at a different directory, and the failures that followed would be in
        # tests that have nothing to do with packaging.
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

        metadata = (Path(out) / written / "METADATA").read_text(errors="replace")

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
    # Scoped to the optional-dependencies TABLE, not to everything after its
    # heading. Splitting on the heading and reading to the end of the file
    # swept in every later array — `[tool.setuptools.packages.find]`'s
    # `include`, and anything added below it — so an unrelated entry silently
    # counted as a declared extra and excused an undeclared import.
    tail = pyproject.split("[project.optional-dependencies]")
    extras = set()
    if len(tail) > 1:
        # Up to the next table header, wherever that is.
        block = re.split(r"^\[", tail[1], maxsplit=1, flags=re.M)[0]
        for group in re.findall(r"^\w[\w-]* = \[(.*?)\]", block, re.M | re.S):
            for item in group.split(","):
                item = item.strip().strip('"\'')
                # `.group(0)` on a miss is an AttributeError, from inside the
                # check that exists to produce a readable failure.
                found = re.match(r"[A-Za-z0-9_.-]+", item)
                if found:
                    extras.add(found.group(0).lower())

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
    # Anchored to a SECTION, not to a word that happens to appear in one.
    #
    # Two of these were bare substring tests and neither guarded anything:
    # `"red" in flat` is satisfied by "shared", "learned" and "measured", and
    # `"engine" in flat` by the `SAMYAMA_REQUIRE_ENGINE` variable in a code
    # block three sections away. Deleting the whole of "Break your own fix
    # before asking for review" and the whole of "Engine version" left this
    # test green — a guard that provably does not guard, in the file that
    # names the vacuous pass as the thing to watch for.
    #
    # A heading AND a phrase from the body, because a heading with nothing
    # under it is the other way to satisfy this.
    for heading, phrase, why in (
        ("## size", "500", "the file-size limit review enforces"),
        ("## what a pr body should contain", "closes #",
         "the only thing that closes an issue on merge"),
        ("## break your own fix before asking for review", "confirm red",
         "breaking your own fix to see a test fail"),
        ("## engine version", "one engine build",
         "which engine build the figures were measured against"),
    ):
        assert heading in flat, (
            f"CONTRIBUTING.md has no {heading!r} section, so it does not cover "
            f"{why}")
        assert phrase in flat, (
            f"CONTRIBUTING.md's {heading!r} section no longer says {phrase!r}, "
            f"which is how it covers {why}")


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


def test_the_short_meeting_set_is_the_same_in_every_place_it_appears():
    """It appears in four files, and a correction reached one of them.

    `demo/demo.py` states it twice, `README.md` once and `demo/README.md`
    once. Adding the missing question to one left three quoting a set that no
    longer exists — the drift this repo keeps finding, in a string a presenter
    copies before a meeting.
    """
    # The GIF is recorded from a DIFFERENT and shorter set, on a line carrying
    # `--auto`. That one is meant to differ, so it is excluded rather than
    # forced to agree — a test that flattens two deliberate sets into one
    # would be demanding a bug.
    quoted = set()
    for name in ("demo/demo.py", "README.md", "demo/README.md"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            if "--auto" in line:
                continue
            quoted |= set(re.findall(r"--only ([\d,]+)", line))

    assert len(quoted) == 1, (
        f"the short-meeting set is quoted as {sorted(quoted)} across the repo "
        f"— a presenter copying one of them runs a different demo")


def test_the_short_meeting_set_runs_the_question_its_pitch_depends_on():
    """The pitch is "fail Algebra 1 and courses close off — and they are not
    the subjects anyone expects". The second half is Q16, and the set ran the
    first half and stopped."""
    from demo.demo import QUESTIONS

    text = (ROOT / "demo" / "README.md").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines()
             if "--only" in line and "--auto" not in line]
    chosen = [int(n) for n in re.findall(r"--only ([\d,]+)", lines[0])[0].split(",")]

    assert 16 in chosen, (
        "Q16 is missing, so the demo makes a claim about subjects and never "
        "shows them")
    assert {QUESTIONS[i]["tier"] for i in chosen} == {1, 2, 3, 4, 5}, (
        "the set no longer reaches every tier, which is what the page claims "
        "of it")


def test_every_module_the_readme_tells_you_to_run_is_packaged():
    """`include` listed `etl*` and `mcp_server*` and not `demo*`.

    So `pip install -e .` shipped the MCP stub — which returns nothing — and
    left out the demo, which is the thing this repo exists to show. `README.md`
    tells a reader to install and then run `python -m demo.demo`, and from
    outside the repo root that raised `ModuleNotFoundError`. From inside it the
    working directory hides the omission, which is why nothing caught it.

    Derived from the README rather than from a list here: a `python -m` line
    added to the quick start later is covered the day it is added, and a list
    in this file would agree with itself instead.
    """
    import re
    import setuptools

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    invoked = {match.split(".")[0]
               for match in re.findall(r"python -m ([a-z_][a-z0-9_.]*)", readme)}
    assert invoked, "no `python -m` line found in the README to check"

    packaged = set(setuptools.find_packages(
        where=str(ROOT), include=CONFIGURED_PACKAGES))

    missing = sorted(name for name in invoked
                     if (ROOT / name / "__init__.py").is_file()
                     and name not in packaged)
    assert not missing, (
        f"the README tells a reader to run {missing} after installing, and "
        f"`pip install .` does not ship them — from any directory other than "
        f"the repo root that is a ModuleNotFoundError. Add them to "
        f"`[tool.setuptools.packages.find] include`.")
