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
import re
import subprocess
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
    """`{{KG_NAME}}`, `{{KG_SLUG}}`, `{{YEAR}}` — the template's markers.

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
        # BINARIES skipped. `errors="replace"` means a `.gif` never raises —
        # it decodes to mojibake and gets scanned, which is slow and can only
        # produce a false positive. A NUL byte in the first block is what
        # `git` itself uses.
        try:
            if b"\0" in path.read_bytes()[:8000]:
                continue
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


@pytest.mark.parametrize("name", EXPECTED_DIRS)
def test_the_shared_layout_is_present(name):
    """Same seven directories as every sibling `*-kg` repo."""
    assert (ROOT / name).is_dir(), f"{name}/ is missing from the shared layout"


@pytest.mark.parametrize("name", EXPECTED_DIRS)


def test_no_directory_in_the_layout_is_silently_empty(name):
    """An empty directory reads as "nothing to do here", the opposite of
    what it means. `benchmarks/` and `mcp_server/` hold only a README, and
    each says so and names the issue tracking it.
    """
    entries = [p for p in (ROOT / name).iterdir() if p.name != "__pycache__"]
    assert entries, f"{name}/ is empty — say what lands there, or remove it"


def test_the_contributing_notes_carry_the_rules_that_cost_rounds():
    """#26 asked for the PR standard in writing. These four are the ones whose
    absence is measurable in this repo's own history, so a CONTRIBUTING that
    omits any of them is decorative."""
    doc = (ROOT / "CONTRIBUTING.md").read_text(errors="replace")
    flat = " ".join(doc.split()).lower()
    # Anchored to a SECTION, not to a word that appears in one. Two of these
    # were bare substrings and neither guarded anything: `"red"` is satisfied
    # by "shared", "learned" and "measured", `"engine"` by
    # SAMYAMA_REQUIRE_ENGINE three sections away — deleting both sections left
    # this green. A heading AND a phrase from the body, because a heading with
    # nothing under it is the other way to pass.
    for heading, phrase, why in (
        ("## size", "500", "the file-size limit review enforces"),
        ("## what a pr body should contain", "closes #",
         "the only thing that closes an issue on merge"),
        ("## break your own fix before asking for review", "confirm red",
         "breaking your own fix to see a test fail"),
        ("## engine version", "one engine build",
         "which engine build the figures were measured against"),
    ):
        # The heading must END there. `"## size" in flat` is satisfied by
        # `## Sizing the demo`, so a renamed section could keep the guard
        # green while the section it names is gone. `(?!\w)` says the next
        # character does not continue the word — a body starting `**500` or
        # `- the` is fine, `## sizing` is not.
        assert re.search(re.escape(heading) + r"(?!\w)", flat), (
            f"CONTRIBUTING.md has no {heading!r} section, so it does not cover "
            f"{why}")
        assert phrase in flat, (
            f"CONTRIBUTING.md's {heading!r} section no longer says {phrase!r}, "
            f"which is how it covers {why}")


def _prose_stripped(body: str, name: str) -> list[str]:
    """The lines a placeholder would actually ship in.

    A `{{KG_NAME}}` inside a comment or docstring is prose ABOUT the
    placeholder, and this repo carries several such passages because the
    removal is what is being explained — the first version of this guard
    flagged them all, including its own docstring, and failed on the commit
    that fixed the defect.

    What it catches is the case that matters: a placeholder in a value or a
    heading. Headings are load-bearing there — see the gating below.
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

    assert quoted, (
        "no `--only` set is quoted anywhere in the repo, so this check read "
        "nothing — it reported 'quoted as []' as though that were a conflict")
    assert len(quoted) == 1, (
        f"the short-meeting set is quoted as {sorted(quoted)} across the repo "
        f"— a presenter copying one of them runs a different demo")


def test_the_short_meeting_set_runs_the_question_its_pitch_depends_on():
    """The pitch is "fail Algebra 1 and courses close off — and they are not
    the subjects anyone expects". The second half is Q16, and the set ran the
    first half and stopped."""
    from demo.demo import QUESTIONS, chosen as parse_only

    text = (ROOT / "demo" / "README.md").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines()
             if "--only" in line and "--auto" not in line]
    assert lines, (
        "demo/README.md no longer shows a non-`--auto` `--only` line, so this "
        "check read nothing — `lines[0]` was an IndexError where a message "
        "belongs")
    quoted = re.findall(r"--only ([\d,]+)", lines[0])
    assert quoted, f"no `--only` numbers on {lines[0]!r}"

    # Parsed by the DEMO'S OWN function, not by indexing QUESTIONS directly.
    # `--only` is 0-based — `chosen()` refuses anything outside
    # `0..len(QUESTIONS)-1` and the CLI help says so — but a test that indexes
    # the list itself is asserting that convention rather than reading it, and
    # would go quietly wrong the day the numbering changed. This way the test
    # and the CLI cannot disagree.
    chosen = parse_only(quoted[0])

    assert 16 in chosen, (
        "Q16 is missing, so the demo makes a claim about subjects and never "
        "shows them")
    assert {QUESTIONS[i]["tier"] for i in chosen} == {1, 2, 3, 4, 5}, (
        "the set no longer reaches every tier, which is what the page claims "
        "of it")


def test_no_module_leaves_a_helper_or_constant_behind():
    """Splitting a file leaves residue, and `pyflakes` cannot see it.

    Unused module-level FUNCTIONS and CONSTANTS are flagged by no linter this
    repo runs. Three splits in three rounds each left something behind,
    invisible to a green suite and a clean style run. `_`-prefixed names and
    `pytest_*` hooks are exempt.
    """
    import ast

    sources = {name: (ROOT / name).read_text(encoding="utf-8", errors="replace")
               for name in tracked()
               if name.endswith(".py") and not name.endswith("__init__.py")}

    offenders = []
    for name, body in sources.items():
        try:
            tree = ast.parse(body)
        except SyntaxError:
            continue
        # `pytest_*` are HOOKS, called by name and referenced nowhere.
        defined = {n.name for n in tree.body
                   if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                   and not n.name.startswith(("_", "test_", "pytest_"))}
        defined |= {t.id for n in tree.body if isinstance(n, ast.Assign)
                    for t in n.targets
                    if isinstance(t, ast.Name) and not t.id.startswith("_")}

        used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        used |= {node.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Attribute)}
        # Read once per file, not once per name: that was twelve seconds.
        others = "\n".join(text for other, text in sources.items() if other != name)
        dead = sorted(n for n in defined - used if n not in others)
        if dead:
            offenders.append(f"{name}: {dead}")

    assert not offenders, (
        f"defined and used nowhere — {offenders}. A split leaves these behind "
        f"and no linter this repo runs reports them.")
