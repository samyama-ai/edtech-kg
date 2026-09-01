"""`CONTRIBUTING.md` against what this repo actually does — edtech-kg#26.

A contributing guide is a document about the project's own habits, so it is
the easiest kind to write once and let rot. The conventions it states are
checked against real branches and real files rather than taken on trust.

The size table is a historical measurement and is dated in the page; it is not
re-derived here, because doing so would need the review history of every
merged PR on every test run.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "CONTRIBUTING.md"

#: The pattern the page states. Kept here as the one place a test compares
#: against, so a reworded page fails rather than quietly meaning something else.
BRANCH = re.compile(
    r"^(feat|fix|chore|docs|refactor|test|research)(\([^)]+\))?/\d+/[a-z0-9-]+$")


def page() -> str:
    assert PAGE.exists(), "CONTRIBUTING.md is gone (#26)"
    return PAGE.read_text(encoding="utf-8")


def test_it_is_short_enough_to_be_read():
    """#26's own definition of done. A contributing guide nobody finishes is a
    guide nobody follows, and `CLAUDE.md` already holds the long form."""
    lines = page().splitlines()
    assert len(lines) < 120, (
        f"CONTRIBUTING.md is {len(lines)} lines. The detail belongs in "
        f"CLAUDE.md; this file is the part someone reads once.")


def test_it_states_the_branch_convention_this_repo_uses():
    text = page()
    assert "<type>/<issue>/<kebab-description>" in text
    for kind in ("feat", "fix", "chore", "docs", "refactor", "test", "research"):
        assert kind in text, f"{kind} is used in this repo and is not listed"
    assert "Closes #" in text, "the auto-close convention is not stated"


def test_the_branch_convention_matches_the_branches_that_exist():
    """The check that keeps this honest. A convention no branch follows is
    aspiration; one every branch follows is a rule worth writing down."""
    listed = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"],
        capture_output=True, text=True, cwd=ROOT)
    names = [n.split("origin/", 1)[-1] for n in listed.stdout.split()
             if n not in ("origin/HEAD", "origin/main")]
    if not names:
        pytest.skip("no remote branches fetched")
    matching = [n for n in names if BRANCH.match(n)]
    # Not "all": `chore/readme-test-count` predates the rule and is merged.
    # A ratchet on the SHARE, so a new branch that ignores it moves the number.
    assert len(matching) / len(names) >= 0.8, (
        f"only {len(matching)} of {len(names)} branches follow the convention "
        f"CONTRIBUTING.md states: {[n for n in names if n not in matching]}")


def test_it_states_the_evidence_standard():
    """#26's definition of done names this specifically: measured is labelled
    measured, estimated is labelled estimated, counts come from scripts."""
    text = page().lower()
    for phrase in ("measured is labelled measured",
                   "printed by a probe, never typed",
                   "raw data is never committed"):
        assert phrase in text, f"the evidence standard omits: {phrase!r}"


def test_it_names_the_things_that_actually_bite():
    """Each of these cost this repo real review rounds. A guide that omits
    them is a guide written from first principles rather than from history."""
    text = page().lower()
    for phrase in ("mutation-test", "500 lines", "python3.11",
                   "samyama_test_url"):
        assert phrase in text, f"CONTRIBUTING.md does not mention {phrase!r}"


def test_the_commands_it_gives_are_the_ones_that_work():
    """A guide whose command is wrong is worse than one with no command."""
    text = page()
    assert "python3.11 -m pytest" in text, (
        "the suite command must name python3.11 — the default python3 on this "
        "machine is 3.14 with none of the dependencies")
    assert "SAMYAMA_TEST_URL" in text and "SAMYAMA_URL" in text, (
        "both variables are needed; setting one leaves engine tests skipping")


def test_it_points_at_the_long_form_rather_than_repeating_it():
    assert "CLAUDE.md" in page(), (
        "the twelve failure classes live in CLAUDE.md and this file should "
        "send the reader there rather than duplicating a second copy to drift")
