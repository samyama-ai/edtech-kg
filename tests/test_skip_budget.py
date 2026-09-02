"""The CI skip guard, which had no tests in the change that rewrote it.

A skip is indistinguishable from a pass in every summary line, so this guard is
the only thing standing between "the engine did not start" and a green build.
It was a single global cap over every skip reason, and it was not doing work at
either value it held: at 8 the cache family alone put `main` over it, and
raising it to 24 moved that failure rather than removing it. A cap wide enough
to admit every family is wide enough to hide one of them doubling.

`budget_problems` is driven directly here rather than through the hook, because
the hook's output is a session exit status a test cannot assert on without
ending its own run.
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import SKIP_BUDGET, budget_problems


def skips(reason: str, count: int) -> list[tuple[str, str]]:
    return [(f"tests/test_x.py::test_{i}", reason) for i in range(count)]


def test_a_reason_with_no_budget_entry_is_reported():
    """The original failure mode: a test skipping for a NEW reason. That is the
    engine not starting, or a fixture giving up — the case this whole apparatus
    exists for, and it must not be absorbed by a family that has room."""
    problems = budget_problems(skips("the engine at localhost refused", 1))
    assert len(problems) == 1
    assert "no entry in SKIP_BUDGET" in problems[0]
    assert "the engine at localhost refused" in problems[0]


def test_a_family_over_its_budget_is_reported_with_both_numbers():
    key = "cached catalogue is incomplete"
    problems = budget_problems(skips(f"the {key} — run the probe", SKIP_BUDGET[key] + 1))
    assert len(problems) == 1
    assert "grew past their budget" in problems[0]
    assert f"budget {SKIP_BUDGET[key]}" in problems[0]


def test_a_family_at_exactly_its_budget_passes():
    """Both bounds, not just the ceiling. A guard that fires at its own budget
    fails every honest run and gets switched off within a day."""
    key = "cached catalogue is incomplete"
    assert budget_problems(skips(f"the {key} — run the probe", SKIP_BUDGET[key])) == []


def test_one_family_growing_is_caught_while_the_total_stays_under():
    """The whole reason for a per-reason budget rather than a cap.

    Below, the cache family doubles and another family empties, so the TOTAL is
    unchanged and a global cap of any value would see nothing.
    """
    cache = "cached catalogue is incomplete"
    other = "is not re-anchored yet"
    swapped = (skips(f"the {cache} — run the probe", SKIP_BUDGET[cache] + SKIP_BUDGET[other])
               + skips(f"tier-1-lookup {other} — edtech-kg#133", 0))
    assert len(swapped) == SKIP_BUDGET[cache] + SKIP_BUDGET[other]   # total unchanged
    problems = budget_problems(swapped)
    assert problems and "grew past their budget" in problems[0]


def test_a_reason_matching_two_keys_is_a_failure_not_a_first_match():
    """Two keys are prefixes of the same sentence. Counting a reason against
    whichever was declared first makes both numbers meaningless while still
    adding up, which is exactly the failure the global cap had."""
    problems = budget_problems(
        [("tests/test_x.py::test_0",
          "holds no Course nodes, so a predicate inside a WHERE and "
          "holds no Course nodes, so no anchor can resolve")])
    assert len(problems) == 1
    assert "more than one SKIP_BUDGET key" in problems[0]


def test_no_two_budget_keys_can_match_the_same_reason_by_containment():
    """The ambiguity check above is a runtime net. This is the static one: no
    key may be a substring of another, or a real skip could land on both."""
    nested = [(a, b) for a in SKIP_BUDGET for b in SKIP_BUDGET if a != b and a in b]
    assert not nested, (
        f"these SKIP_BUDGET keys contain one another, so a reason matching the "
        f"longer always matches the shorter too: {nested}")


def test_every_budget_key_is_a_reason_something_can_actually_raise():
    """A ratchet that stops applying is the thing this repo keeps finding.

    An entry whose text no `pytest.skip()` in the tree produces is a permanent
    exemption for a skip that cannot happen — dead weight that reads as
    coverage. Matched against the source rather than a run, because a run on a
    loaded machine raises a different set than CI does.
    """
    corpus = "\n".join(p.read_text(encoding="utf-8")
                       for p in Path(__file__).resolve().parents[1].rglob("*.py")
                       if ".git" not in p.parts and p.name != "test_skip_budget.py")
    orphans = [key for key in SKIP_BUDGET if key not in corpus]
    assert not orphans, (
        f"no skip in this tree can produce these reasons, so their budgets "
        f"exempt nothing: {orphans}")


def test_nothing_still_reads_the_old_global_cap():
    """`MAX_ALLOWED_SKIPS` and `ALLOWED_SKIPS` are gone. A leftover reference
    would be a second, weaker guard running beside this one."""
    root = Path(__file__).resolve().parents[1]
    stale = [str(p.relative_to(root)) for p in root.rglob("*.py")
             if ".git" not in p.parts and p.name != "test_skip_budget.py"
             and re.search(r"\b(MAX_ALLOWED_SKIPS|ALLOWED_SKIPS)\b",
                           p.read_text(encoding="utf-8"))]
    assert not stale, f"these still reference the removed global cap: {stale}"
