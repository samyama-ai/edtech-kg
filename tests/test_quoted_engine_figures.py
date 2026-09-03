"""Every engine figure quoted in prose, against the record that measured it.

edtech-kg#136, second half. The probe and its record landed first; this is what
makes them load-bearing. Until now `240`, `359`, `119` and the rest were typed
into comments and a document, and nothing tied them to anything — in a repo
whose stated rule is that a count reaches a document through a probe and is
never hand-typed.

`431 of 791` is what that costs. It was written into two files and, when the
question was finally put to the graph, the answer was 463.

**Anchored on the sentence, not on the number.** Each entry below is a pattern
with the figure captured, so the check is "what this sentence says" against
"what the probe measured". If a sentence is reworded past its anchor the test
fails saying so, which is the same contract
`test_the_prose_totals_agree_with_the_counted_ones` already uses here: a
figure nobody can locate is a figure nobody is checking.

Not every number near these is an engine figure. `229 of 791` is prerequisite
coverage from `probe_pwcs`, `781 of 791` is grade levels from #137, and `960`
is catalogue pages. None is measured by `probe_engine_capability`, so the sweep
below passes over them on the only test that matters — whether the probe
records that value — rather than on a hand-maintained list of names.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import probe_engine_capability as probe

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = json.loads(probe.RECORD.read_text(encoding="utf-8"))


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def measured_values() -> set[str]:
    """Every integer the probe recorded, as a string, above a floor.

    The floor drops one- and two-digit values. A recorded `0` or `4` collides
    with a section number, a year fragment and a table column on almost every
    line, so including them would make the sweep report noise until somebody
    turned it off — a worse outcome than a narrower sweep that holds.
    """
    return {str(got["value"]) for got in RECORD["constructs"].values()
            if isinstance(got.get("value"), int) and got["value"] > 9}

#: `(file, construct, pattern)`. The pattern captures the figure the prose
#: states; the construct names what the probe measured it as.
QUOTATIONS = [
    ("docs/questions.md", "requires_edges",
     r"measures (\d+) resolvable prerequisite"),
    ("docs/questions.md", "courses",
     r"the scope is one district\.\*\* PWCS, (\d+) courses"),
    ("docs/questions.md", "chains_length_two_or_more",
     r"count 0 rows over (\d+) chains of length two or more"),
    ("docs/questions.md", "repeated_variable_across_var_length",
     r"matches \*\*all (\d+)\*\* REQUIRES edges"),

    ("benchmarks/questions/tier-4-graph-algorithms.cypher", "requires_edges",
     r"Measured against the loaded district — (\d+) REQUIRES edges"),
    ("benchmarks/questions/tier-4-graph-algorithms.cypher",
     "chains_length_two_or_more", r"REQUIRES edges, (\d+) chains of"),
    ("benchmarks/questions/tier-4-graph-algorithms.cypher", "requires_edges",
     r"MATCH \(\)-\[r:REQUIRES\]->\(\) +RETURN count\(r\) +-> +(\d+)"),
    ("benchmarks/questions/tier-4-graph-algorithms.cypher",
     "repeated_variable_across_var_length",
     r"REQUIRES\*1\.\.1\]->\(c\) +RETURN count\(p\) +-> +(\d+)"),
    ("benchmarks/questions/tier-4-graph-algorithms.cypher",
     "not_in_list_unparenthesised",
     r"returns (\d+) of \d+ courses where"),
    ("benchmarks/questions/tier-4-graph-algorithms.cypher",
     "not_in_list_parenthesised",
     r"`NOT \(c\.url IN \[a, b\]\)` returns (\d+)"),
    ("benchmarks/questions/tier-4-graph-algorithms.cypher",
     "bare_single_node_map_absent_url",
     r"returns all (\d+) courses for a URL no course has"),

    # `359` is Q71's wrong answer, and it is a CURRENT measurement rather than
    # a historical one: the unbounded `REQUIRES*` path count is what that query
    # returns on this district today. It reads as history — "the answer this
    # file used to give" — which is exactly why it needs holding: a figure
    # phrased in the past tense looks like it cannot go stale, and it can.
    ("benchmarks/questions/tier-4-graph-algorithms.cypher",
     "chains_any_length", r"the answer this file used to give was (\d+)"),
    ("benchmarks/questions/tier-4-graph-algorithms.cypher",
     "chains_any_length", r"this reported (\d+) where there are none"),
    ("docs/questions.md", "chains_any_length",
     r"The query answered (\d+) where the answer is none"),
    ("docs/questions.md", "chains_any_length",
     r"cycle detection a confident (\d+)"),
    ("docs/questions.md", "requires_edges",
     r"so the (\d+) resolvable edges and the"),

    # Found by the sweep below on its first run, which is the argument for
    # having it: anchoring a list of sentences proves that list and says
    # nothing about the next one somebody adds.
    ("benchmarks/questions/tier-4-graph-algorithms.cypher",
     "chains_any_length", r"and the other (\d+) where there are none"),
    ("docs/questions.md", "courses",
     r"edges across (\d+) PWCS courses"),
    ("docs/questions.md", "courses",
     r"How many courses does this district publish\? ✅ — \*\*(\d+)\*\*"),
    ("docs/questions.md", "courses",
     r"list a prerequisite at all\? ✅ — \d+ of (\d+)"),
]


def stated(path: str, pattern: str) -> tuple[int, str]:
    text = (ROOT / path).read_text(encoding="utf-8")
    found = re.search(pattern, text)
    assert found, (
        f"{path} no longer states a figure matching {pattern!r}. Either the "
        f"sentence was reworded — update the pattern — or the claim was "
        f"removed, in which case remove the entry.")
    return int(found.group(1)), found.group(0)


@pytest.mark.parametrize(
    "path, construct, pattern", QUOTATIONS,
    ids=[f"{p.split('/')[-1]}:{c}" for p, c, _ in QUOTATIONS])
def test_a_quoted_figure_is_the_one_the_probe_measured(
        path, construct, pattern):
    said, sentence = stated(path, pattern)
    measured = RECORD["constructs"][construct]["value"]
    assert said == measured, (
        f"{path} says {said} and the record measured {measured} for "
        f"{construct!r}.\n  sentence: {sentence}\n"
        f"Re-run `python -m etl.probe_engine_capability --record` if the "
        f"engine changed, then update the prose. If the prose is right "
        f"and the record is stale, that is the same bug the other way.")


def test_every_construct_the_documents_quote_is_in_the_record():
    """A quotation naming a construct the probe does not run is a figure with
    nothing behind it — the state this issue exists to leave."""
    unknown = sorted({c for _, c, _ in QUOTATIONS} - set(RECORD["constructs"]))
    assert not unknown, f"quoted but never measured: {unknown}"


#: Figures that ARE values the probe measured, appear in a swept file, and are
#: nevertheless measured by something else — a coincidence of value, not a
#: quotation. Each maps to what actually produced it.
#:
#: It is EMPTY, and that is the finding. It held six entries and every one was
#: inert: five were not recorded values at all, so the sweep's first clause
#: already skipped them, and the sixth — 463, `isolated_courses` — was a
#: recorded value appearing nowhere. That one was not merely useless. Naming a
#: recorded value here switches the sweep off for it PERMANENTLY, and 463 is
#: the figure in this repo with a documented history of being wrong in prose:
#: 431 was typed into two files and the graph said 463. The sweep was blind to
#: exactly the number it was written for.
#:
#: `test_no_exemption_is_dead` keeps this honest. An entry that changes nothing
#: is a comment that lies, and this one lied towards a false all-clear.
NOT_ENGINE_FIGURES: dict[str, str] = {}


def swept_files() -> list[str]:
    return sorted({path for path, _, _ in QUOTATIONS})


def patterns_for(path: str) -> list[str]:
    """This file's patterns, and only this file's.

    Testing every pattern against every file silently exempts a line in
    `questions.md` that happens to match a tier-4 pattern — a hole that widens
    with each quotation added, and only in the direction of passing.
    """
    return [pattern for quoted, _, pattern in QUOTATIONS if quoted == path]


def test_no_exemption_is_dead():
    """An exemption must both name a measured value and appear somewhere.

    Neither condition held for any of the six entries this dict shipped with.
    A dead exemption reads as a considered decision and is not one; a dead
    exemption on a RECORDED value is worse, because it turns the sweep off for
    that figure while looking like documentation.
    """
    values = measured_values()
    seen = "\n".join(read(path) for path in swept_files())
    dead = [f"{number} ({why}) — "
            + ("not a value the probe measures"
               if number not in values else "appears in no swept file")
            for number, why in NOT_ENGINE_FIGURES.items()
            if number not in values or not re.search(rf"\b{number}\b", seen)]
    assert not dead, (
        "these exemptions change nothing and should be deleted:\n  "
        + "\n  ".join(dead))


@pytest.mark.parametrize("path", swept_files())
def test_no_engine_figure_in_these_files_goes_unchecked(path):
    """The sweep. Anchoring a list of sentences proves that list; it says
    nothing about the one somebody adds next week.

    The count is deliberately not written here. A file arguing that figures
    must come from a measurement is a poor place to hand-type one, and this
    docstring said "seventeen" while QUOTATIONS held twenty.

    Every number in these files matching a value the probe measured must be
    either quoted above — and therefore checked — or named as something else.
    That is the difference between "these figures are held" and "some figures
    are held".
    """
    values = measured_values()
    mine = patterns_for(path)
    loose = []
    for number, line in ((n, line) for line in read(path).splitlines()
                         for n in re.findall(r"\b\d{2,4}\b", line)):
        if number not in values or number in NOT_ENGINE_FIGURES:
            continue
        # A line one of THIS file's patterns matches is already checked by the
        # parametrised test above. An earlier version also tried a prefix
        # comparison against the matched fragments, which almost never fired —
        # a fragment rarely starts at column 0 — so it read as load-bearing
        # while this line did all the work.
        if any(re.search(pattern, line) for pattern in mine):
            continue
        loose.append(f"{number} in: {line.strip()[:76]}")

    assert not loose, (
        f"{path} states figures the probe measures and nothing checks:\n  "
        + "\n  ".join(sorted(set(loose)))
        + "\nAdd each to QUOTATIONS with a pattern, or to NOT_ENGINE_FIGURES "
          "saying what actually measured it.")
