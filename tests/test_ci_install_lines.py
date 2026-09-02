"""How an install line is read.

Split from `tests/test_ci_dependencies.py` when it passed the 500-line review
limit — six reviews in this repo reported a file as too large and reviewed
nothing inside it. Split by SUBJECT: that file asks whether CI installs what
the suite needs, walking imports and subprocess invocations to find out. This
one asks only how `packages_installed` reads a single `pip install` line.

Every gap below is in the FALSE-GREEN direction, which is why they are worth
their own file. A parser that under-reads makes the guard report a package as
missing — noisy, but visible. A parser that OVER-reads makes it report a
package as installed when nothing installs it, and the guard then certifies a
workflow that cannot run the suite. Three of the four did exactly that.
"""

from __future__ import annotations

import pytest

from tests.test_ci_dependencies import packages_installed


def workflow_running(command: str) -> str:
    return f"jobs:\n  test:\n    steps:\n      - run: {command}\n"


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


def test_a_comment_inside_a_block_scalar_is_not_a_command():
    """Measured: `# pip install evil` inside a `run: |` block put `evil` in
    the installed set. `ci.yml` uses block scalars for three of five steps."""
    assert packages_installed(
        "jobs:\n  test:\n    steps:\n      - run: |\n"
        "          # pip install evil\n"
        "          python -m pip install pytest\n") == {"pytest"}


def test_an_inline_comment_is_not_a_package_list():
    """`pip install pytest  # and flake8` contributed `#`, `and` and
    `flake8` — the last being the dangerous one, because a dependency named in
    a comment would read as installed."""
    assert packages_installed(
        workflow_running("python -m pip install pytest  # and flake8")) == {"pytest"}


def test_a_backslash_continuation_keeps_its_packages():
    """Splitting per line dropped everything after the backslash, and the
    following line mentions no `pip install` so it was ignored entirely."""
    assert packages_installed(
        "jobs:\n  test:\n    steps:\n      - run: |\n"
        "          python -m pip install \\\n"
        "            pytest flake8\n") == {"pytest", "flake8"}


@pytest.mark.parametrize("spec, name", [
    ("packaging~=24.0", "packaging"),      # PEP 508 compatible release
    ('tomli;python_version<"3.11"', "tomli"),   # environment marker
    ('"setuptools>=61.0"', "setuptools"),
    ("pytest[testing]", "pytest"),
])
def test_a_version_specifier_does_not_become_part_of_the_name(spec, name):
    """`packaging~=24.0` parsed to `packaging~`, a name no install line
    contains — so the guard reported the package missing while it was there."""
    assert packages_installed(
        workflow_running(f"python -m pip install {spec}")) == {name}
