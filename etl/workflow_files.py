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
    to a list item so a `uses:` inside a comment or a string does not count.
    """
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

    A step is a list item under `steps:`, whatever key it leads with. A
    tolerant step is the key itself, indented under one, not the words
    appearing anywhere.
    """
    steps = tolerant = 0
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
        if re.match(r"^-\s*[\w-]+:", stripped):
            steps += 1
        if re.match(r"^-?\s*continue-on-error:\s*true$", stripped):
            tolerant += 1
    return {"steps": steps, "tolerant_steps": tolerant}
