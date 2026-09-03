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
is catalogue pages — none is measured by `probe_engine_capability` and none is
claimed here.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import probe_engine_capability as probe

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = json.loads(probe.RECORD.read_text(encoding="utf-8"))

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
     "not_in_list_unparenthesised", r"returns (\d+) of 791 courses where"),
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
    # having it: anchoring seventeen sentences proved seventeen and said
    # nothing about the eighteenth.
    ("benchmarks/questions/tier-4-graph-algorithms.cypher",
     "chains_any_length", r"and the other (\d+) where there are none"),
    ("docs/questions.md", "courses",
     r"edges across (\d+) PWCS courses"),
    ("docs/questions.md", "courses",
     r"How many courses does this district publish\? ✅ — \*\*(\d+)\*\*"),
    ("docs/questions.md", "courses",
     r"list a prerequisite at all\? ✅ — 229 of (\d+)"),
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


#: Numbers in these files that look like engine figures and are NOT — each
#: measured by something else, and named so the sweep below can tell "checked"
#: from "not an engine figure at all". Anything not here and not quoted above
#: is a figure nobody is holding.
NOT_ENGINE_FIGURES = {
    "229": "courses listing a prerequisite — probe_pwcs, and\n"
           "docs/sources/course-prerequisites.md",
    "781": "courses carrying grade levels — edtech-kg#137",
    "783": "courses carrying a description — edtech-kg#137",
    "960": "catalogue pages in the sitemap — probe_pwcs",
    "463": "isolated courses — quoted only as the correction to 431,\n"
           "in prose that is about the correction",
    "431": "the WRONG figure, quoted as wrong",
}


@pytest.mark.parametrize("path", sorted({p for p, _, _ in QUOTATIONS}))
def test_no_engine_figure_in_these_files_goes_unchecked(path):
    """The sweep. Anchoring seventeen sentences proves those seventeen; it says
    nothing about the eighteenth somebody adds next week.

    Every number in these files matching a value the probe measured must be
    either quoted above — and therefore checked — or named as something else.
    That is the difference between "these figures are held" and "some figures
    are held".
    """
    values = {str(got["value"]) for got in RECORD["constructs"].values()
              if isinstance(got.get("value"), int) and got["value"] > 9}
    checked = "\n".join(
        stated(path, pattern)[1]
        for quoted, _, pattern in QUOTATIONS if quoted == path)

    text = (ROOT / path).read_text(encoding="utf-8")
    loose = []
    for number, line in ((n, line) for line in text.splitlines()
                         for n in re.findall(r"\b\d{2,4}\b", line)):
        if number not in values or number in NOT_ENGINE_FIGURES:
            continue
        if number in checked and line.strip()[:40] in checked:
            continue
        if any(re.search(pattern, line) for _, _, pattern in QUOTATIONS):
            continue
        loose.append(f"{number} in: {line.strip()[:76]}")

    assert not loose, (
        f"{path} states figures the probe measures and nothing checks:\n  "
        + "\n  ".join(sorted(set(loose)))
        + "\nAdd each to QUOTATIONS with a pattern, or to NOT_ENGINE_FIGURES "
          "saying what actually measured it.")
