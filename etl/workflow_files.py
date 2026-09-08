"""What a workflow FILE says — what it fetches, and how many steps can fail it.

Split from `etl/probe_ci_history.py` when it passed the 500-line review limit.
Split by SUBJECT: everything there reads the Actions API and asks what HAPPENED
when workflows ran. This reads the committed YAML and asks what those workflows
ARE — a different source, and one that needs no token and no network.

The two counts here are load-bearing together. `tolerant < steps` is what
decides whether a workflow's own success outcome carries information, and the
first version counted the two with regexes that could drift in opposite
directions on a file nobody had changed.

edtech-kg#109.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def dependencies() -> dict:
    """What each committed workflow fetches, read from the YAML.

    `uses:` is the line that needs the runner to fetch something from outside.
    A workflow with none of them exercises the runner and nothing else, which
    is what makes `runner-diagnostic.yml`'s outcome mean something.

    Read with a regex rather than a YAML parser on purpose: the suite has no
    third-party dependency beyond pytest, and adding one to count six lines
    would be a heavier price than the parse is worth. The pattern is anchored
    to a list item OR its continuation — the dash is optional, because a step
    written `- name: x` / `  uses: y` puts the `uses:` on a line with no dash
    at all. A `uses:` inside a comment is not excluded by this pattern and
    never has been; the docstring used to claim it was.
    """
    if not WORKFLOWS.is_dir():
        # LOUD. Returning {} made every `tolerant < steps` comparison read as
        # False on an empty dict, so a missing workflow directory reported
        # "the diagnostic's outcome is informative" — the exact claim this
        # probe exists to refuse, arrived at by finding nothing.
        raise FileNotFoundError(
            f"{WORKFLOWS} does not exist, so no workflow can be classified. "
            f"Every comparison built on `uses:` counts would be vacuous.")

    found = {}
    # `.yaml` too. A workflow saved under the other spelling is one the runner
    # runs and this function does not see, and its absence here would read as
    # "that workflow fetches nothing".
    for path in sorted(list(WORKFLOWS.glob("*.yml"))
                       + list(WORKFLOWS.glob("*.yaml"))):
        text = path.read_text(encoding="utf-8")
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", text, re.M)
        found[path.name] = {"uses": sorted(set(uses)), "count": len(uses),
                            **step_counts(text)}
    return found


def step_counts(text: str) -> dict:
    r"""How many steps a workflow has, and how many of them cannot fail it.

    **Counted the same way as each other**, which the first version did not
    do. `^\s+- name:` saw only steps whose first key is `name`, missing any
    leading with `uses:` or `run:`; `continue-on-error:\s*true` was unanchored
    and would match the phrase in a comment or on a job-level key. So the two
    could drift in opposite directions at once and `tolerant < steps` — the
    test that decides whether the diagnostic's outcome means anything — could
    invert on a workflow nobody had touched.

    A step is a list item under `steps:`, whatever key it leads with, and NOT
    inside a `run: |` block scalar — those hold arbitrary shell, and a line
    reading `- name: foo` in one is text. A tolerant step is the key itself,
    indented under one, in any spelling YAML reads as true, with or without a
    trailing comment.
    """
    steps = tolerant = 0
    scalar_at = None
    #: The column `steps:` sits at. The block ends at the first non-blank line
    #: indented no further than that — which is how a SIBLING job's own
    #: `continue-on-error` stops being counted as a step's. Resetting only at
    #: column zero left `other:` inside the previous job's step list, and the
    #: job-level key was counted as a tolerant step.
    at_column = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        # A list item ALIGNED with its own key is legal, common YAML:
        #
        #     steps:
        #     - uses: actions/checkout@v4
        #
        # so a block must not end merely because a line is no further in than
        # `steps:` — it ends on a line at that column that is not a list
        # item. Ending on any equal indent gave `steps == 0` for every
        # workflow written that way, and zero steps with zero tolerant steps
        # reads as `tolerant < steps` being False, which flips
        # `diagnostic_outcome_is_informative` to True and quietly restores the
        # exact claim this probe refuses to make.
        if at_column is not None and indent <= at_column \
                and not stripped.startswith("- "):
            at_column = None
        if stripped == "steps:":
            at_column = indent
            continue
        if at_column is None:
            continue
        # **Not inside a block scalar.** `run: |` and `script: |` hold
        # arbitrary shell, and a line like `- name: foo` inside one is text,
        # not a step. The block runs until the indent returns to at most the
        # key's own, so its contents are skipped wholesale.
        if scalar_at is not None:
            if indent > scalar_at:
                continue
            scalar_at = None
        if re.search(r":\s*[|>][-+]?\s*$", stripped):
            scalar_at = indent
            continue

        if re.match(r"^-\s*[\w-]+:", stripped):
            steps += 1
        # Trailing comments, and the spellings YAML also reads as true. `$`
        # anchoring missed `continue-on-error: true  # while debugging`, and
        # `true` alone missed True/'true'/yes — all of which disable the
        # step, and a step that cannot fail its job is what this counts.
        truthy = re.match(
            r"^-?\s*continue-on-error:\s*['\"]?(true|yes|on)['\"]?\s*(#.*)?$",
            stripped, re.I)
        if truthy:
            tolerant += 1
    return {"steps": steps, "tolerant_steps": tolerant}
