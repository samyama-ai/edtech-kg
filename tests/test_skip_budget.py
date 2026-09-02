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

import ast
import re
from pathlib import Path

import conftest
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


def corpus_files() -> list[Path]:
    """The files the corpus reads — `conftest.py` deliberately not among them.

    A separate function because the exclusion is the thing that broke, and a
    list is assertable where a concatenated blob is not: the budget keys appear
    as substrings of real reasons by design, so no text check can tell "the key
    is in a skip message" from "the key is in the line that defines it".
    """
    root = Path(__file__).resolve().parents[1]
    return [p for p in sorted(root.rglob("*.py"))
            if ".git" not in p.parts and p.name != "conftest.py"]


def skip_reasons_in_the_tree() -> str:
    """Every string this tree's code can build a skip reason out of.

    Three things this is NOT, each for a measured reason.

    Not the raw text of every `.py` file: that put `conftest.py` in the corpus,
    where the budget keys are literals, so every key matched ITSELF and the
    orphan test below could not fail. Verified — adding
    `"the engine ran out of interstellar plasma": 3` to SKIP_BUDGET passed.
    That is the "dead weight that reads as coverage" the docstring below warns
    about, in the test written to catch it.

    Not `pytest.skip()` call sites alone, which is the tighter thing to want
    and does not work here: four of the six reasons are assembled into a
    `message` local and passed by name, sometimes through `require_data()`, so
    the literal is nowhere near the call. That version reported four of six
    keys as orphans.

    And not comments or docstrings — prose describing a skip is not a skip. AST
    string constants only, with every docstring subtracted, so a key that
    survives only because some paragraph mentions it still reads as an orphan.
    """
    found = []
    for path in corpus_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
                first = node.body[0] if node.body else None
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    docstrings.add(id(first.value))
        found += [n.value for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)
                  and id(n) not in docstrings]
    return "\n".join(found)


# A canary must exist as NO string literal anywhere, including in the test that
# uses it — this file is in the corpus too, and writing the canary down would
# put it there and make the assertion pass for the wrong reason. That is the
# same self-reference that made the old corpus vouch for every key by reading
# `conftest.py`, one level down. Joined at run time so no constant holds it.
def canary(*words: str) -> str:
    return " ".join(words)


def test_a_budget_key_nothing_can_raise_is_reported_as_an_orphan(monkeypatch):
    """The bug the corpus above replaced, asserted rather than remembered.

    Driving the check with a key nothing produces is the only thing that proves
    it can fail. The previous corpus read every `.py` file including
    `conftest.py`, where the keys are literals, so a nonsense key passed.
    """
    absent = canary("the", "engine", "ran", "out", "of", "interstellar", "plasma")
    monkeypatch.setitem(SKIP_BUDGET, absent, 3)
    corpus = skip_reasons_in_the_tree()
    assert corpus, "no string constants found at all — the walk is broken"
    assert absent not in corpus, (
        "the canary leaked into the corpus, so this test cannot fail")
    assert absent in [key for key in SKIP_BUDGET if key not in corpus]


def test_a_reason_named_only_in_a_docstring_is_still_an_orphan(monkeypatch):
    """Prose about a skip is not a skip.

    reasons live in docstrings all over this repo

    That line above is a docstring and nothing else. Without subtracting
    docstrings the corpus would vouch for a budget key on the strength of a
    paragraph mentioning it.
    """
    only_in_prose = canary("reasons", "live", "in", "docstrings", "all", "over",
                           "this", "repo")
    monkeypatch.setitem(SKIP_BUDGET, only_in_prose, 1)
    assert only_in_prose not in skip_reasons_in_the_tree()


def test_conftest_stays_out_of_the_corpus():
    """The regression the canary above cannot see.

    A canary built at run time is an orphan whether or not `conftest.py` is in
    the corpus, so it does not notice the exclusion being removed — measured:
    deleting the exclusion left every other test here green.

    Asserted on the FILE LIST rather than on the text. The budget keys appear
    as substrings of real skip reasons by design, so no text check can
    distinguish "this key is in a skip message" from "this key is in the line
    that defines it" — which is the whole failure being guarded against.
    """
    files = corpus_files()
    assert files, "the corpus walks no files at all"
    assert Path(conftest.__file__).resolve() not in {f.resolve() for f in files}, (
        "conftest.py is being read back into the corpus, so every SKIP_BUDGET "
        "key matches its own definition and the orphan check cannot fail")


def test_every_budget_key_is_a_reason_something_can_actually_raise():
    """A ratchet that stops applying is the thing this repo keeps finding.

    An entry whose text no `pytest.skip()` in the tree produces is a permanent
    exemption for a skip that cannot happen — dead weight that reads as
    coverage. Matched against call sites rather than a run, because a run on a
    machine with `data/` cached raises a different set than CI does.
    """
    corpus = skip_reasons_in_the_tree()
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


# --------------------------------------------------------------------------
# The HOOK, not just the helper. Extracting `budget_problems` made the
# comparison testable and left its consumer unasserted — measured: making
# `pytest_sessionfinish` discard the result and blowing the cache budget from
# 11 to 2 gave a silent guard, exit 0, and all eight tests above still green.
# That is the shape this repo keeps finding: helper covered, consumption by
# the real caller not.
# --------------------------------------------------------------------------

class FakeSession:
    """Enough of a session to record what the hook sets on it."""

    def __init__(self):
        self.exitstatus = 0


def test_the_hook_fails_the_run_when_a_family_is_over_budget(monkeypatch, capsys):
    key = "cached catalogue is incomplete"
    monkeypatch.setenv("SAMYAMA_CI", "1")
    monkeypatch.setattr(conftest, "_skipped",
                        skips(f"the {key} — run the probe", SKIP_BUDGET[key] + 1))
    session = FakeSession()
    conftest.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 1
    assert "CI SKIP GUARD FAILED" in capsys.readouterr().out


def test_the_hook_leaves_an_honest_run_alone(monkeypatch, capsys):
    """The other bound. A guard that fails a run inside its own budget is worse
    than none — it gets switched off, and then nothing is watching."""
    key = "cached catalogue is incomplete"
    monkeypatch.setenv("SAMYAMA_CI", "1")
    monkeypatch.setattr(conftest, "_skipped",
                        skips(f"the {key} — run the probe", SKIP_BUDGET[key]))
    session = FakeSession()
    conftest.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 0
    assert "CI SKIP GUARD FAILED" not in capsys.readouterr().out


def test_the_hook_does_nothing_outside_CI(monkeypatch):
    """`SAMYAMA_CI` unset is a developer's machine, where a skip is ordinary.
    Without this the guard fails every local run and gets deleted."""
    monkeypatch.delenv("SAMYAMA_CI", raising=False)
    monkeypatch.setattr(conftest, "_skipped", skips("a reason with no budget", 50))
    session = FakeSession()
    conftest.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 0

