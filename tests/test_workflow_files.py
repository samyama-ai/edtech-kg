"""What a workflow FILE says — the two counts that decide what its outcome means.

Split from `tests/test_probe_ci_history.py` when it passed the 500-line review
limit, matching the split of the module under test. Split by SUBJECT: that file
drives the Actions API and asks what HAPPENED; this reads committed YAML and
asks what a workflow IS.

`steps` and `tolerant_steps` are load-bearing together. `tolerant < steps` is
what decides whether a workflow's own success outcome carries information, and
counting them with regexes that could drift in opposite directions is how that
comparison silently inverts.

No network, no token.
"""

from __future__ import annotations

import pytest

from etl import workflow_files


def test_steps_and_tolerant_steps_are_counted_the_same_way():
    """They must not drift in opposite directions. `^\\s+- name:` saw only
    steps whose first key is `name` — missing `- uses:` and `- run:` — while
    an unanchored `continue-on-error: true` matched comments and job-level
    keys, so `tolerant < steps` could invert on an unchanged workflow.
    """
    workflow = """
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
      - name: Something
        run: echo hi
      - run: echo bare
        continue-on-error: true
      # continue-on-error: true   <- a comment, not a step
  other:
    continue-on-error: true
"""
    counted = workflow_files.step_counts(workflow)
    assert counted["steps"] == 3, "a step leading with uses: or run: is a step"
    assert counted["tolerant_steps"] == 1, (
        "only the real key indented under a step counts — not the comment, "
        "and not the job-level one")


def test_a_steps_aligned_list_is_counted():
    """Legal, common YAML:

        steps:
        - uses: actions/checkout@v4

    Ending the block on any equal indent gave `steps == 0` for every workflow
    written that way — and zero steps with zero tolerant steps reads as
    `tolerant < steps` being False, which flips
    `diagnostic_outcome_is_informative` to True and quietly restores the
    claim this probe exists to refuse.
    """
    aligned = """
jobs:
  test:
    steps:
    - uses: actions/checkout@v4
    - name: One
      continue-on-error: true
    - run: echo two
  other:
    continue-on-error: true
"""
    assert workflow_files.step_counts(aligned) == {"steps": 3, "tolerant_steps": 1}


def test_a_step_inside_a_block_scalar_is_not_a_step():
    """`run: |` and `script: |` hold arbitrary shell. A line reading
    `- name: foo` inside one is text, and counting it inflated `steps` — which
    feeds `tolerant < steps`, the comparison that decides whether a workflow's
    own success outcome carries information."""
    yaml = """
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
      - name: Shell
        run: |
          echo hi
          - name: not a step
          continue-on-error: true
      - run: echo two
"""
    assert workflow_files.step_counts(yaml) == {"steps": 3, "tolerant_steps": 0}


def test_the_truthy_spellings_yaml_accepts_all_count():
    """`$`-anchored `true` missed a trailing comment, and `true` alone missed
    True/'true'/yes — all of which disable the step, and a step that cannot
    fail its job is what this counts."""
    for spelling in ("true", "True", "TRUE", "'true'", "yes", "on",
                     "true  # while debugging"):
        yaml = (f"jobs:\n  j:\n    steps:\n      - name: x\n"
                f"        continue-on-error: {spelling}\n")
        counted = workflow_files.step_counts(yaml)
        assert counted["tolerant_steps"] == 1, (spelling, counted)


def test_a_missing_workflow_directory_fails_loudly(monkeypatch, tmp_path):
    """Returning {} made every `tolerant < steps` comparison read as False on
    an empty dict, so a missing directory reported "the diagnostic's outcome
    is informative" — the claim this probe exists to refuse, reached by
    finding nothing."""
    monkeypatch.setattr(workflow_files, "WORKFLOWS", tmp_path / "absent")
    with pytest.raises(FileNotFoundError, match="vacuous"):
        workflow_files.dependencies()
