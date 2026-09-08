"""`docs/sources/ci-history.md` held to the record that produced it.

The page opens "every figure below was printed by the probe". This is what
makes that true rather than aspirational: every number it states is read back
out of `ci-history-measured.json`, and a figure in the page that is in no
sentence here is caught by the sweep at the bottom.

Both directions, because one alone is a guard with a hole. Record-to-page
catches a stale document after a re-measurement; page-to-record catches a
number typed into the page that was never measured at all.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
# `docs/`, not `docs/sources/`: that folder is the register of EXTERNAL
# sources and every row in its README carries a licence position. This page
# measures our own infrastructure, so it sits beside `engine-behaviours.md` —
# whose record likewise lives under `sources/` with the other measured JSON.
DOC = ROOT / "docs" / "ci-history.md"
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "ci-history-measured.json").read_text("utf-8"))

PAGE = DOC.read_text(encoding="utf-8")
CI = RECORD["workflows"]["ci.yml"]
DIAGNOSTIC = RECORD["workflows"]["runner-diagnostic.yml"]
VERDICT = RECORD["verdict"]


def stated(pattern: str) -> str:
    """The figure a sentence states — a miss is a FAILURE, never a pass.

    A regex anchored on wording that matches nothing after a harmless reflow
    would otherwise make every assertion below vacuous. This repo has shipped
    that guard twice.
    """
    found = re.search(pattern, PAGE)
    assert found, f"the page no longer states this — {pattern!r} matched nothing"
    return found.group(1)


def test_the_run_count_and_the_zero_are_the_measured_ones():
    """The two numbers the whole page exists for."""
    assert int(stated(r"`ci\.yml` has run \*\*(\d+) times")) == CI["runs"]
    assert int(stated(r"times since [\d-]+ and succeeded\s+(\d+) times")) == \
        CI["success"]
    assert CI["success"] == 0, (
        "CI has succeeded — this page and #109 both need rewriting, which is "
        "the best possible reason for this test to fail")


def test_the_floor_argument_matches_the_record():
    """"The tests have never executed" rests on these three figures together:
    the floor, how many runs reached it, and the longest run there has been."""
    assert int(stated(r"\*\*(\d+) seconds\n?is a floor")) == \
        VERDICT["floor_seconds"]
    assert int(stated(r"\*\*(\d+) of \d+ runs reached that floor")) == \
        CI["over_floor"]
    assert int(stated(r"longest run\s+in the repo's history is (\d+)s")) == \
        CI["max_seconds"]
    assert CI["max_seconds"] < VERDICT["floor_seconds"], (
        "a run has now lasted longer than the floor, so the page can no "
        "longer say the tests cannot have run")


def test_the_isolating_comparison_is_the_measured_one():
    """Both sides of it. The conclusion — that fetching an action is the
    variable — is false if either workflow's record changes."""
    with_actions = int(stated(r"\*\*(\d+) of \d+\*\* runs succeeded for the "
                              r"workflow that fetches\n  actions"))
    without = int(stated(r"\*\*(\d+) of \d+\*\* runs succeeded for the "
                         r"workflow that fetches\n  nothing"))
    assert with_actions == VERDICT["with_actions"]["success"]
    assert without == VERDICT["without_actions"]["success"]
    assert RECORD["dependencies"]["runner-diagnostic.yml"]["count"] == 0, (
        "the diagnostic fetches an action now; the comparison no longer "
        "isolates one variable and the page's conclusion does not follow")


def test_the_page_states_what_the_diagnostic_success_does_not_prove():
    """The page's most important paragraph, and the easiest to lose in an
    edit that tightens the prose. Without it the page reads as "the runner has
    network", which the measurement does not support."""
    tolerant = int(stated(r"\*\*(\d+) of its \d+ steps\*\*"))
    assert tolerant == VERDICT["diagnostic_tolerant_steps"]
    assert VERDICT["diagnostic_outcome_is_informative"] is False, (
        "the diagnostic now has a step that can fail it, so its outcome does "
        "carry information — this section of the page is now wrong")
    assert "not** evidence that the runner can reach the" in PAGE
    assert "no job-log endpoint" in PAGE


def test_the_incident_paragraph_quotes_the_measured_run_count():
    """The one figure in "what it cost" — it restates the run count, so it
    goes stale on the next measurement exactly like every other figure here."""
    assert int(stated(r"red tick that had meant nothing for\n(\d+) runs")) == \
        CI["runs"]


def test_the_table_row_figures_are_the_measured_ones():
    row = re.search(r"\| `ci\.yml` \| (\d+) \| \*\*(\d+)\*\* \| (\d+)s \| (\d+)s \| (\d+) \|",
                    PAGE)
    assert row, "the ci.yml table row no longer parses"
    assert [int(g) for g in row.groups()] == [
        CI["runs"], CI["success"], CI["median_seconds"], CI["max_seconds"],
        RECORD["dependencies"]["ci.yml"]["count"]]

    # The other row too. Bound because the table is where a reader compares
    # the two workflows, so a stale figure there misreads as the comparison
    # itself failing. Found by the dead-code guard: `DIAGNOSTIC` was defined
    # at the top of this module and used by nothing, which is exactly what an
    # unchecked table row looks like from the outside.
    other = re.search(
        r"\| `runner-diagnostic\.yml` \| (\d+) \| (\d+) \| (\d+)s \| (\d+)s \| (\d+) \|",
        PAGE)
    assert other, "the runner-diagnostic.yml table row no longer parses"
    assert [int(g) for g in other.groups()] == [
        DIAGNOSTIC["runs"], DIAGNOSTIC["success"], DIAGNOSTIC["median_seconds"],
        DIAGNOSTIC["max_seconds"],
        RECORD["dependencies"]["runner-diagnostic.yml"]["count"]]


def test_the_page_does_not_conclude_past_its_evidence():
    """#109 asks whether the runner can reach the network. The probe cannot
    answer that, and a page that answered it anyway would be the failure this
    repository documents most often — a confident number nobody measured."""
    # DISCUSSING the possibility is fine and necessary — the page has to name
    # the open question. ASSERTING it is not. So each phrase is located and
    # its own sentence is required to hedge, rather than the phrase being
    # banned outright. The first version of this test banned the substring and
    # failed on the sentence that poses the question, which would have pushed
    # the page toward saying less about what it does not know.
    hedges = ("whether", "open question", "unanswered", "not established",
              "does not claim")
    for overreach in ("the runner has no network",
                      "the runner cannot reach the network",
                      "dns is blocked", "pypi is blocked"):
        lower = PAGE.lower()
        start = 0
        while (at := lower.find(overreach, start)) != -1:
            # Split on every sentence end, not just ". " — a line wrapped
            # after the full stop ends ".\n", so the naive split ran two
            # sentences together and the phrase could borrow a hedge from the
            # NEXT sentence, which is the failure mode of a guard like this.
            # `[.!?]` followed by whitespace OR markup. A full stop before
            # `**` — which starts a bolded sentence, and this page has
            # several — was not a boundary, so two sentences ran together and
            # the phrase could still borrow the next one's hedge. That is the
            # same bug the previous fix was for, one character narrower.
            bounds = [m.end() for m in
                      re.finditer(r"[.!?](?:[\s\n]|\*\*|\Z)", lower)]
            opens = max([b for b in bounds if b <= at] + [0])
            closes = min([b for b in bounds if b > at] + [len(lower)])
            sentence = lower[opens:closes]
            assert any(h in sentence for h in hedges), (
                f"the page asserts {overreach!r} as fact:\n  {sentence.strip()}\n"
                f"Nothing measured supports it — the log is unread.")
            start = at + 1


BOLDED = sorted({int(n) for n in
                 re.findall(r"\*\*(\d+)(?:s| of| times)?", PAGE)})


def test_the_sweep_has_something_to_sweep():
    """A parametrize over an empty list collects zero cases and reports
    success. If a reflow stops the bold pattern matching, the sweep below
    silently checks nothing — which is the failure it exists to catch, applied
    to itself."""
    # **Named figures, not a count.** A threshold equal to the current count
    # is not a ratchet: it passes today and passes after every figure but one
    # is lost. And a threshold below it is a number the next person lowers.
    # What the sweep must actually cover is the argument's own load-bearing
    # figures — if any of these stops appearing in bold, the page has stopped
    # making the claim, whatever the total is.
    required = {
        "the run count": CI["runs"],
        "the successes": CI["success"],
        "the floor": VERDICT["floor_seconds"],
        "the measured suite duration": VERDICT["suite"]["seconds"],
        "the tolerant step count": VERDICT["diagnostic_tolerant_steps"],
    }
    missing = {what: figure for what, figure in required.items()
               if figure not in BOLDED}
    assert not missing, (
        f"the page no longer states {missing} in bold, so the sweep does not "
        f"cover it. These are the figures the floor argument and the "
        f"isolating comparison rest on.")


@pytest.mark.parametrize("number", BOLDED)
def test_every_bolded_figure_on_the_page_is_in_the_record(number):
    """The sweep. A figure typed into a bolded claim that appears nowhere in
    the record is exactly what "printed by a probe, never typed" forbids, and
    the sentence-by-sentence tests above only cover the sentences they name.
    """
    known = {CI["runs"], CI["success"], CI["over_floor"], CI["max_seconds"],
             CI["median_seconds"], VERDICT["floor_seconds"],
             VERDICT["diagnostic_steps"], VERDICT["diagnostic_tolerant_steps"],
             VERDICT["with_actions"]["success"],
             VERDICT["without_actions"]["success"],
             VERDICT["without_actions"]["runs"],
             # Was a bare literal whitelisted here, which made the one
             # figure the floor argument rests on the only unbound number on
             # the page. It is TIMED now, by the probe, with the command
             # recorded beside it.
             VERDICT["suite"]["seconds"]}
    assert number in known, (
        f"the page states **{number}** in bold and the record holds no such "
        f"figure. Either re-run the probe, or the number was typed.")


def test_the_suite_duration_was_measured_not_asserted():
    """**The figure the whole floor argument turns on.**

    CONTRIBUTING: "every figure in a document is printed by a probe, never
    typed. If you cannot point at the command, delete the figure." This one
    was typed and then DISCLOSED as an assertion, and a review was right that
    disclosure is not measurement — if the suite really took 30s the floor
    would drop toward 40s, the 58s run could have executed tests, and the
    headline would weaken.
    """
    suite = VERDICT["suite"]
    assert suite["measured"] is True, (
        f"the suite duration was not timed ({suite.get('why')}), so the floor "
        f"argument rests on a constant again. Re-run the probe without "
        f"--no-time-suite.")
    assert suite["command"], "no command recorded to point at"
    assert suite["seconds"] < VERDICT["floor_seconds"], (
        f"the suite takes {suite['seconds']}s and the floor is "
        f"{VERDICT['floor_seconds']}s; the floor must exceed the suite it "
        f"bounds, or it bounds nothing")
    assert suite["command"] in PAGE, (
        "the page must show the command that produced this figure")


def test_the_third_workflow_row_is_bound_too():
    """The page calls `runner-diagnostics.yml` load-bearing — it is half the
    action-free evidence — and nothing checked its row. A table row nobody
    binds is a figure nobody re-measures, which is this module's whole
    subject."""
    old = RECORD["workflows"].get("runner-diagnostics.yml")
    if old is None:
        assert "runner-diagnostics.yml" not in PAGE, (
            "the page shows a workflow the record no longer holds")
        return
    row = re.search(
        r"\| `runner-diagnostics\.yml` \| (\d+) \| (\d+) \| (\d+)s \| (\d+)s \|",
        PAGE)
    assert row, "the runner-diagnostics.yml row no longer parses"
    assert [int(g) for g in row.groups()] == [
        old["runs"], old["success"], old["median_seconds"], old["max_seconds"]]
    assert "not committed" in PAGE, (
        "the row must say the workflow is no longer in the tree, or a reader "
        "will look for a file that is not there")
    assert VERDICT["in_history_but_not_committed"] == ["runner-diagnostics.yml"]
