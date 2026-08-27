"""The CI workflow, read as a document and checked against what it claims.

A workflow file is the one piece of this repo that nothing else tests, and it
is uniquely easy to weaken by accident: dropping one environment variable turns
the engine tests back into skips, and the build stays green while proving less
than it did the day before. That change would look like a tidy-up in review.

So the three things that make CI mean anything are asserted here rather than
trusted: a real engine runs, an unreachable one fails instead of skipping, and
an unexpected skip fails the run.

These read the YAML as text on purpose. A YAML parser is not in the test
dependencies — the suite imports nothing outside the standard library except
pytest, and adding a parser to assert five strings would cost more than it
saves.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> str:
    if not WORKFLOW.exists():
        pytest.fail(f"{WORKFLOW.relative_to(ROOT)} is missing — the suite gates nothing (#18)")
    return WORKFLOW.read_text(encoding="utf-8")


def test_the_suite_runs_on_pull_requests_and_on_main(workflow):
    """A workflow that runs only on `push` gates nothing on a PR, which is the
    one moment anybody is looking."""
    assert re.search(r"^on:", workflow, re.M), "no trigger block"
    assert re.search(r"^\s*pull_request:", workflow, re.M), "does not run on pull requests"
    assert re.search(r"^\s*push:", workflow, re.M), "does not run on push"


def test_an_unreachable_engine_fails_rather_than_skips(workflow):
    """Without this variable the engine-backed tests skip, and a skip is
    indistinguishable from a pass in the summary line, the badge and the merge
    button. It is the whole reason #18 exists."""
    assert 'SAMYAMA_REQUIRE_ENGINE: "1"' in workflow, (
        "SAMYAMA_REQUIRE_ENGINE=1 is not set — engine tests would skip silently "
        "and the build would still be green")


def test_an_unexpected_skip_fails_the_run(workflow):
    """`-rs` makes skips visible; `SAMYAMA_CI=1` makes them fail. Visible alone
    is not enough — nobody reads a green log."""
    assert 'SAMYAMA_CI: "1"' in workflow, (
        "SAMYAMA_CI=1 is not set — conftest.py's skip guard would not run")
    assert re.search(r"pytest\b[^\n]*-rs", workflow), (
        "pytest is not run with -rs, so skip reasons never reach the log")


def test_an_engine_is_actually_started(workflow):
    """`SAMYAMA_REQUIRE_ENGINE=1` with no engine started is a build that fails
    every time, which is a gate everybody learns to route around."""
    assert re.search(r"docker run\b.*\bsamyama\b", workflow), "no engine container is started"
    assert "SAMYAMA_TEST_URL: http://localhost:8201" in workflow, (
        "the tests are not pointed at the started engine")


def test_the_engine_is_waited_for_rather_than_slept_on(workflow):
    """A fixed sleep that is too short leaves the engine unreachable — which
    with SAMYAMA_REQUIRE_ENGINE=1 is a flaky red build, and without it was a
    silent skip. Both are worse than polling."""
    assert re.search(r"curl[^\n]*localhost:8201", workflow), "no readiness poll"
    assert not re.search(r"^\s*(-\s*)?run:\s*sleep\s+\d+\s*$", workflow, re.M), (
        "the engine is waited for with a bare sleep rather than a poll")


def test_the_checkout_is_deep_enough_for_the_ratchets(workflow):
    """`actions/checkout@v4` defaults to a shallow clone that fetches only the
    PR ref. Neither `origin/main` nor `main` resolves in it, so both size
    ratchets — the exception list and the review limit — return no baseline and
    skip.

    With `SAMYAMA_CI=1` that fails the build rather than passing quietly, so
    nothing is lost silently. The problem is one layer down: a ratchet that
    never runs in CI is a ratchet that is not there, and these two are what
    stop the size guard from being widened. Reproduced in a shallow clone
    before fixing — both skipped, exactly here.
    """
    assert re.search(r"fetch-depth:\s*0", workflow), (
        "actions/checkout is shallow, so the size ratchets have no `main` to "
        "compare against and never run in CI")


def test_a_merged_commit_is_not_left_without_a_run(workflow):
    """`cancel-in-progress: true` applies to pushes as well as pull requests,
    so two merges in quick succession cancel the first one's build — leaving a
    commit on `main` that nothing ever checked. Superseding is right on a PR,
    where only the latest state matters, and wrong on the branch of record."""
    assert re.search(r"cancel-in-progress:\s*\$\{\{[^}]*pull_request", workflow), (
        "cancel-in-progress is unconditional, so a fast second merge can leave "
        "a commit on main with no completed run")


def test_the_engine_image_is_pinned_to_a_version(workflow):
    """A floating tag changes the engine under published figures with no commit
    to point at. Every number in docs/ was measured against one build."""
    found = re.search(r"ENGINE_IMAGE:\s*(\S+)", workflow)
    assert found, "no ENGINE_IMAGE is declared"
    image = found.group(1)
    assert not image.endswith(":latest"), f"{image} floats — pin the version"
    assert re.search(r":\d+\.\d+\.\d+$", image), (
        f"{image} is not pinned to an exact version")


def packages_installed(workflow: str) -> set[str]:
    """What the workflow's `run:` commands actually install.

    Anchored to the `run:` COMMAND, not to any line mentioning `pip install`.
    Both YAML spellings — `run:` on its own line and `- run:` as the first key
    of a step — because the second is equally valid and was invisible to this
    guard, which would have read a workflow that installs everything as one
    that installs nothing.
    `ci.yml` discusses `pip install -e .` and `pip install --dry-run` in the
    comment block above the step, so matching the phrase anywhere absorbed
    English from those comments — `and`, `but`, `deliberate`, `is`, `not`,
    `still`, `that` — and the guard could then be satisfied by a word in prose
    rather than by a package in the install step. A vacuous pass in the check
    written to close one.

    A named function because the test below drives THIS, not a copy of it. The
    first version of that test re-implemented the regex inline, so reverting
    this one left it green — it was verifying a duplicate parser.
    """
    found = set()
    for line in re.findall(r"^\s*-?\s*run:.*?pip install([^\n]*)$", workflow, re.M):
        for word in line.split():
            if word.startswith("-"):
                continue
            # Quotes stripped first. A pinned dependency is normally quoted
            # in a shell command — `"setuptools>=61.0"` — and leaving the
            # quote on made the token `"setuptools`, which matches nothing.
            # The guard then reported a package as missing that the very same
            # line installs.
            found.add(re.split(r"[<>=!\[]", word.strip('"\''))[0].lower())
    return found


def test_the_workflow_installs_what_the_suite_actually_imports(workflow):
    """The suite needs pytest and the standard library, measured — so that is
    what CI installs.

    `pip install -e .` is not used, and the reason changed with this branch.
    It used to be that the packaging was broken — the template's placeholder
    name is not a valid identifier, so the install failed before it started.
    #17 fixed that, and this file is part of #17, so the old reason was an
    argument for a state the same branch removes. It survived here after being
    corrected in `ci.yml`, which is the sweep this round is about.

    The reason now is that installing adds nothing and costs something:
    `dependencies` is empty because outside the standard library this package
    imports nothing, while build isolation would reach the index for a
    backend.

    Scoped to the modules the suite REACHES — the tests, this conftest, and the
    `etl` modules the tests import. Not every file in the tree: a module the
    suite never imports can carry a third-party import that CI never executes,
    and compiling it here would fail for a reason CI does not have.

    The scope is DERIVED below by walking the imports, never listed here. A
    docstring that names the files it excludes is wrong the moment one of them
    is renamed or deleted, and it is wrong silently — the test keeps passing
    and the paragraph keeps explaining a tree that no longer exists.
    """
    assert re.search(r"pip install[^\n]*\bpytest\b", workflow), "pytest is not installed"

    reached = set(ROOT.glob("tests/**/*.py")) | {ROOT / "conftest.py"}
    for path in sorted(reached):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("etl."):
                candidate = ROOT / (node.module.replace(".", "/") + ".py")
                if candidate.exists():
                    reached.add(candidate)

    third_party = set()
    for path in sorted(reached):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            third_party.update(n.split(".")[0] for n in names)

    # First-party names are read from the tree rather than listed here. A
    # hand-kept list means a test that imports `mcp_server` or `schema` is
    # reported as an uninstalled dependency, and the failure message points at
    # the install step rather than at the import.
    first_party = {d.name for d in ROOT.iterdir() if (d / "__init__.py").exists()}
    first_party |= {p.stem for p in ROOT.glob("*.py")} | {"__future__"}
    third_party -= set(sys.stdlib_module_names) | first_party

    # What CI installs is READ from the workflow, not listed here. A literal
    # `{"pytest"}` meant adding a package to the install step left this test
    # still failing, and adding an import left it still passing — the drift
    # this file exists to catch, in the assertion that catches it.
    installed = packages_installed(workflow)

    missing = {name for name in third_party if name.lower() not in installed}
    assert not missing, (
        f"the suite imports {sorted(missing)}, which CI does not install "
        f"(it installs {sorted(installed)}). Either add it to the install "
        f"step or drop the dependency.")


# --------------------------------------------------------------------------
# the skip guard itself, driven directly
# --------------------------------------------------------------------------
#
# Driven with fabricated reports rather than by running a real xfail. A real
# one would have to live in the suite permanently to be covered, and a test
# kept alive only to be observed by another test is the sort of thing that gets
# deleted as dead a year later, taking this coverage with it.


class _Report:
    """The two fields the hook reads, in the shapes pytest actually produces."""

    def __init__(self, nodeid, longrepr, skipped=True, wasxfail=None):
        self.nodeid, self.longrepr, self.skipped = nodeid, longrepr, skipped
        if wasxfail is not None:
            self.wasxfail = wasxfail


@pytest.fixture
def guard(monkeypatch):
    """The real hook, with its accumulator emptied for the test."""
    import conftest
    monkeypatch.setattr(conftest, "_skipped", [])
    return conftest


def test_an_xfail_is_not_treated_as_a_silent_skip(guard):
    """`report.skipped` is True for an xfailed test, and its `longrepr` is a
    plain string rather than the 3-tuple a skip carries. Without the guard it
    landed here with an empty reason, missed the allowlist, and failed the
    build with a message naming no reason at all.

    An xfail is a deliberate statement that a test is expected to fail — the
    opposite of a test quietly not running, which is what this file exists to
    catch."""
    guard.pytest_runtest_logreport(
        _Report("tests/t.py::x", "reason: known broken", wasxfail="known broken"))
    assert guard._skipped == []


def test_a_skip_of_an_unrecognised_shape_still_names_itself(guard):
    """A reason that comes through as something other than the 3-tuple must not
    be recorded as an empty string. A blank reason fails the build with nothing
    for the next person to search for, which is its own dead end."""
    guard.pytest_runtest_logreport(_Report("tests/t.py::y", "Skipped: odd shape"))
    assert guard._skipped == [("tests/t.py::y", "Skipped: odd shape")]
    assert guard._skipped[0][1] != ""


def test_a_real_skip_is_recorded_with_its_reason(guard):
    """The ordinary path, so the two cases above are not the only ones covered
    and a hook that recorded nothing at all would still fail here."""
    guard.pytest_runtest_logreport(
        _Report("tests/t.py::z", ("tests/t.py", 12, "Skipped: no engine")))
    assert guard._skipped == [("tests/t.py::z", "Skipped: no engine")]


def test_a_passing_test_is_not_recorded(guard):
    guard.pytest_runtest_logreport(_Report("tests/t.py::p", None, skipped=False))
    assert guard._skipped == []


def test_a_package_named_only_in_a_comment_does_not_count_as_installed():
    """The guard reads what the step RUNS, not what the file mentions.

    `ci.yml` explains at length why `pip install -e .` is not used, so a guard
    matching any line containing `pip install` treated the words of that
    explanation as installed packages.
    """
    workflow = """
jobs:
  test:
    steps:
      # We deliberately do not run `pip install -e . numpy` here, and that is
      # explained above.
      - name: Install
        run: python -m pip install --quiet pytest
"""
    installed = packages_installed(workflow)
    assert installed == {"pytest"}, (
        f"the guard read {sorted(installed)} as installed — anything beyond "
        f"pytest came from the comment, not from the command")


def test_a_pinned_dependency_is_read_through_its_quotes():
    """A pin is normally quoted in a shell command, and the quote broke it.

    `"setuptools>=61.0"` parsed to `"setuptools` — so the guard reported a
    package as missing that the very same line installs, and the obvious
    "fix" would have been to remove the pin rather than to read it.
    """
    workflow = (
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - run: python -m pip install --quiet pytest "
        '"setuptools>=61.0" ' + "'wheel<1'\n"
    )
    assert packages_installed(workflow) == {"pytest", "setuptools", "wheel"}
