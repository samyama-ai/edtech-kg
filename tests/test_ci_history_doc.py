"""`docs/ci-history.md` held to the record that produced it.

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
    # The date is anchored INTO the headline, not looked for anywhere on the
    # page. As a bare substring it held only while the date appeared once; a
    # second mention would leave the headline effectively unchecked.
    headline = re.search(
        r"`ci\.yml` has run \*\*(\d+) times since ([\d-]+) and succeeded",
        PAGE)
    assert headline, "the headline sentence no longer parses"
    assert int(headline.group(1)) == CI["runs"]
    assert headline.group(2) == CI["first"][:10]
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
    # BOTH numbers. The denominator was an unanchored `\d+`, so the page
    # could say "0 of 218 runs" over a numerator computed across the TIMED
    # ones — a run with an unusable stamp dropping out of the evidence while
    # the sentence claimed full coverage.
    floor_line = re.search(r"\*\*(\d+) of (\d+) timed runs reached that floor",
                           PAGE)
    assert floor_line, (
        "the page must say TIMED runs — the count is over runs whose stamps "
        "parsed, not over every run")
    assert int(floor_line.group(1)) == CI["over_floor"]
    assert int(floor_line.group(2)) == CI["timed"]
    assert CI["untimed"] == 0, (
        f"{CI['untimed']} run(s) have unusable stamps and are outside the "
        f"floor evidence entirely. The page must say how many, or the "
        f"probe must be taught to read that stamp format.")
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
    # `[\d.]+` for the medians: they are real medians now and average the two
    # middles on an even count, so they can carry a decimal.
    row = re.search(
        r"\| `ci\.yml` \| (\d+) \| \*\*(\d+)\*\* \| ([\d.]+)s \| (\d+)s \| (\d+) \|",
        PAGE)
    assert row, "the ci.yml table row no longer parses"
    assert [float(g) for g in row.groups()] == [
        CI["runs"], CI["success"], CI["median_seconds"], CI["max_seconds"],
        RECORD["dependencies"]["ci.yml"]["count"]]

    # The other row too. Bound because the table is where a reader compares
    # the two workflows, so a stale figure there misreads as the comparison
    # itself failing. Found by the dead-code guard: `DIAGNOSTIC` was defined
    # at the top of this module and used by nothing, which is exactly what an
    # unchecked table row looks like from the outside.
    other = re.search(
        r"\| `runner-diagnostic\.yml` \| (\d+) \| (\d+) \| ([\d.]+)s \| (\d+)s \| (\d+) \|",
        PAGE)
    assert other, "the runner-diagnostic.yml table row no longer parses"
    assert [float(g) for g in other.groups()] == [
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


# Every number inside a bold span, not only ones the span STARTS with.
# `**999 times**` was caught and `**over 999 runs**` and `**nearly 40%**` both
# passed a full run — and a leading word is the natural way a fudged claim
# gets written.
# DATES are removed first. A bold span containing `2026-08-21` otherwise
# contributes 2026, 08 and 21 as if they were measurements — and the date IS
# bound, by `test_the_prose_figures_the_record_holds_are_pinned_too`, against
# the record's own `first`. Two guards, each on the thing it can actually
# check.
#: Every way this page can emphasise a figure. `**x**` was the only one
#: matched, so `__777 runs__` — valid CommonMark, and what some editors emit —
#: and `<strong>888</strong>` both passed a full run.
BOLD_SPAN = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__|<strong>(.*?)</strong>",
                       re.S)
BOLDED = sorted({int(n)
                 for match in BOLD_SPAN.findall(PAGE)
                 for span in match if span
                 for n in re.findall(r"\d+", re.sub(r"\d{4}-\d\d-\d\d", "", span))})


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
    # A MARGIN, not a bare `<`. At 59s against a 60s floor the old assertion
    # passed and the page still claimed a floor — while the floor's whole
    # justification is that CI additionally pulls a container image, which is
    # not timed here. The margin is what stands in for that pull, so it is
    # named rather than left implied.
    IMAGE_PULL_ALLOWANCE = 10
    margin = VERDICT["floor_seconds"] - suite["seconds"]
    assert margin >= IMAGE_PULL_ALLOWANCE, (
        f"the suite takes {suite['seconds']}s and the floor is "
        f"{VERDICT['floor_seconds']}s — a margin of {margin}s. The floor "
        f"exists to cover the suite PLUS an untimed container pull, and "
        f"{IMAGE_PULL_ALLOWANCE}s is the least that is credible. Raise the "
        f"floor, or time the pull.")
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
        r"\| `runner-diagnostics\.yml` \| (\d+) \| (\d+) \| ([\d.]+)s \| (\d+)s \|",
        PAGE)
    assert row, "the runner-diagnostics.yml row no longer parses"
    assert [float(g) for g in row.groups()] == [
        old["runs"], old["success"], old["median_seconds"], old["max_seconds"]]
    assert "not committed" in PAGE, (
        "the row must say the workflow is no longer in the tree, or a reader "
        "will look for a file that is not there")
    assert VERDICT["in_history_but_not_committed"] == ["runner-diagnostics.yml"]


def test_the_prose_figures_the_record_holds_are_pinned_too():
    """Three figures sat in prose that the record holds and nothing compared.

    Each was confirmed by mutation: the headline start date passed as
    2024-01-01 because `stated()` matched `[\\d-]+` rather than comparing;
    the diagnostic's duration and the module count likewise. The module count
    is the one that will actually drift — this PR adds two modules.
    """
    assert CI["first"][:10] in PAGE, (
        f"the page no longer states the first run's date ({CI['first'][:10]}) "
        f"— it was matched as a pattern and never compared")
    assert f"One module of {VERDICT['suite']['of_modules']}." in PAGE, (
        f"the page's module count is not {VERDICT['suite']['of_modules']}")
    diagnostic = RECORD["workflows"]["runner-diagnostic.yml"]
    # `:g` — the page writes 5, not 5.0. The median is a float since it
    # averages two middles on an even count, and prose does not carry a
    # trailing zero.
    assert f"{diagnostic['median_seconds']:g}-second" in PAGE, (
        "the diagnostic's duration is quoted in prose and unbound; it is the "
        "figure behind 'equally consistent with every probe failing at once'")


def test_the_narrative_section_is_marked_as_narrative():
    """The page opens "every figure below was printed by the probe", and the
    incident section carries PR numbers, "five failures" and "two hours later"
    — none in the record, none producible by the probe, and outside both the
    sweep and the named-sentence tests. CONTRIBUTING's rule is bidirectional,
    so the scope has to be stated rather than assumed."""
    assert "printed by" in PAGE
    assert "read from the merge history" in PAGE, (
        "the incident section must say its figures come from git, not from "
        "the probe — otherwise the page's opening claim covers them and is "
        "false")


def test_the_opening_claim_is_scoped_to_what_the_probe_prints():
    """It opened "every figure below was printed by the probe" and retracted
    that 113 lines later at the incident section. The marker was a real
    improvement, but the order is wrong for a reader who stops at the table."""
    opening = PAGE[:PAGE.index("## ")]
    assert "except where a section says otherwise" in opening, (
        "the opening claim covers sections it cannot cover; scope it where "
        "the reader meets it, not where it is retracted")


def test_the_causal_claim_is_backed_by_more_than_one_run():
    """It was stated flat at n=1. The diagnostic is workflow_dispatch, so the
    honest fix was more runs rather than softer wording."""
    without = VERDICT["without_actions"]
    assert without["runs"] >= 5, (
        f"the action-free comparison rests on {without['runs']} run(s); the "
        f"page states a cause and one observation does not support it")
    assert without["failure"] == 0, (
        f"{without['failure']} action-free run(s) have failed; the page's "
        f"causal sentence no longer follows")
    assert "not a controlled experiment" in PAGE, (
        "the page must still name the other differences between the two "
        "workflows — trigger, step count, step tolerance")


def test_the_page_no_longer_claims_fetching_is_the_cause():
    """**The diagnostic cannot fail**, so its 7 of 7 was never evidence that
    its steps worked — every step carries `continue-on-error: true`. And
    removing the actions from `ci.yml` did not turn the tick green.

    The page stated the cause anyway, with the step tolerance listed as one
    confound among several rather than as the whole of the difference.
    """
    page = PAGE
    assert "continue-on-error" in page, (
        "the page compares the two workflows without saying that one of them "
        "cannot fail")
    assert "not established" in page or "at most part of the cause" in page, (
        "the page still presents fetching an action as the established cause")
