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

import re
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
    """A shallow clone fetches only the PR ref. Neither `origin/main` nor
    `main` resolves in it, so both size ratchets — the exception list and the
    review limit — return no baseline and skip.

    With `SAMYAMA_CI=1` that fails the build rather than passing quietly, so
    nothing is lost silently. The problem is one layer down: a ratchet that
    never runs in CI is a ratchet that is not there, and these two are what
    stop the size guard from being widened. Reproduced in a shallow clone
    before fixing — both skipped, exactly here.

    **Asserted against the CLONE, not against `fetch-depth: 0`.** That option
    belongs to `actions/checkout`, which this workflow no longer uses (#109),
    and a test naming it would have passed only while the fix was absent.
    What the ratchets actually need is a `main` to compare against.
    """
    assert re.search(r"refs/heads/\*:refs/remotes/origin/\*", workflow), (
        "the clone does not fetch all branches, so the size ratchets have no "
        "`main` to compare against and never run in CI")
    assert re.search(r"git branch -f main origin/main", workflow), (
        "`main` is not made resolvable locally, which is what the ratchets "
        "look for")


def test_the_workflow_fetches_no_actions(workflow):
    """One fewer external dependency on a runner nobody here can inspect.

    **This is NOT asserted as the fix for #109, and an earlier version of this
    docstring said it was.** That claim rested on the #109 diagnostics having
    7 runs and 7 successes without actions — and those diagnostics carry
    `continue-on-error: true` on every step by design, so a workflow built to
    be unfailable did not fail. Removing the actions here did not turn the
    tick green either.

    What is true: this workflow has 242 runs and 0 successes, and the shell
    these two actions were wrapping is cheap enough that not fetching them
    costs nothing. The test exists so the dependency is not reintroduced
    without someone deciding to, not because it is known to matter.
    """
    offending = [line for line in workflow.splitlines()
                 if re.match(r"\s*-?\s*uses:", line)]
    assert not offending, (
        f"this workflow fetches an action, which is the one thing this "
        f"runner cannot do: {offending}")


def test_the_python_version_is_asserted_rather_than_assumed(workflow):
    """`actions/setup-python` pinned 3.11 and is gone. Whatever the runner
    image ships is now what runs, so the version is checked in the job — a
    suite quietly running on a different interpreter than the repo targets is
    the same silent drift this file exists to stop."""
    assert "sys.version_info[:2] == (3, 11)" in workflow


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
