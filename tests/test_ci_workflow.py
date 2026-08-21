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


def test_the_engine_image_is_pinned_to_a_version(workflow):
    """A floating tag changes the engine under published figures with no commit
    to point at. Every number in docs/ was measured against one build."""
    found = re.search(r"ENGINE_IMAGE:\s*(\S+)", workflow)
    assert found, "no ENGINE_IMAGE is declared"
    image = found.group(1)
    assert not image.endswith(":latest"), f"{image} floats — pin the version"
    assert re.search(r":\d+\.\d+\.\d+$", image), (
        f"{image} is not pinned to an exact version")


def test_the_workflow_installs_what_the_suite_actually_imports(workflow):
    """The suite needs pytest and the standard library, measured — so that is
    what CI installs.

    `pip install -e .` is not used, because it cannot run: `pyproject.toml`
    still carries the repo template's placeholder name and setuptools rejects
    it (#17). The dependencies it lists are not the ones the code imports
    either. Installing a dependency set nobody imports would be its own green
    build that proves nothing.

    Scoped to the modules the suite REACHES — the tests, this conftest, and the
    `etl` modules the tests import. `etl/loader.py`, `etl/helpers.py`,
    `etl/download_data.py` and `mcp_server/server.py` are untouched template
    scaffolding, still holding `{{KG_NAME}}` placeholders and imported by
    nothing; they carry third-party imports that CI never executes, and folding
    them in here would fail for a reason CI does not have.
    """
    assert re.search(r"pip install[^\n]*\bpytest\b", workflow), "pytest is not installed"

    reached = set(ROOT.glob("tests/*.py")) | {ROOT / "conftest.py"}
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

    third_party -= set(sys.stdlib_module_names) | {"__future__", "etl", "tests", "demo"}
    assert third_party <= {"pytest"}, (
        f"the suite imports {sorted(third_party)}, which CI does not install. "
        f"Either add it to the install step or drop the dependency.")
