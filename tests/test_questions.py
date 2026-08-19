"""The question count table must match the questions.

Written after the first version of that table was hand-counted and got three of
its six rows wrong. A summary table nobody checks is how a document starts
lying about itself.
"""

import re
from pathlib import Path

import pytest

DOC = Path(__file__).resolve().parents[1] / "docs" / "questions.md"
MARKS = ("✅", "⚠️", "❌")
TIERS = ["1 — lookup", "2 — one hop", "3 — change impact",
         "4 — graph algorithms", "5 — multi-domain", "6 — whole-graph"]


def counted() -> dict:
    """Count questions and status marks per tier, from the questions themselves."""
    body = DOC.read_text().split("## Tier 1")[1].split("## The competency gap")[0]
    out = {}
    # strict: a seventh tier added without updating TIERS is a loud failure,
    # not a silent under-count that only surfaces in the total row.
    for name, block in zip(TIERS, re.split(r"\n## Tier ", body), strict=True):
        marks = dict.fromkeys(MARKS, 0)
        questions = re.split(r"\*\*Q\d+", block)[1:]
        for question in questions:
            # `re.split` has already consumed every **Q boundary, so the block
            # is the question. No further splitting needed.
            found = [mark for mark in MARKS if mark in question]
            for mark in found:
                marks[mark] += 1
        out[name] = {"questions": len(questions), **marks}
    return out


def tabulated() -> dict:
    """The same figures as the document's own summary table claims them."""
    table = DOC.read_text().split("## Counts")[1]
    out = {}
    for row in re.findall(r"^\| ([^|]+?) \| (.+)$", table, re.M):
        name = row[0].strip().strip("*")
        cells = [c.strip().strip("*") for c in row[1].split("|") if c.strip()]
        if name in TIERS or name == "Total":
            out[name] = dict(zip(["questions", *MARKS], [int(c) for c in cells]))
    return out


def test_the_document_has_the_questions_it_claims():
    assert sum(t["questions"] for t in counted().values()) == 102


def test_every_question_carries_exactly_one_status():
    """This could not fail as named while the counter broke on the first mark:
    every question contributed exactly one by construction, so a question
    carrying two — the old ✅ / ❌ form — passed silently as ✅. The counter no
    longer breaks, so both zero marks and two marks fail here."""
    for name, tier in counted().items():
        assert sum(tier[m] for m in MARKS) == tier["questions"], name


@pytest.mark.parametrize("tier", TIERS)
def test_each_tier_row_matches_the_questions(tier):
    assert counted()[tier] == tabulated()[tier], tier


def test_the_total_row_matches_the_tiers():
    real = counted()
    total = {k: sum(t[k] for t in real.values()) for k in ["questions", *MARKS]}
    assert total == tabulated()["Total"]


def test_question_numbers_are_unique_and_unbroken():
    numbers = [int(n) for n in re.findall(r"\*\*Q(\d+)", DOC.read_text())]
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == len(numbers)
    assert numbers == list(range(1, len(numbers) + 1))


def test_no_tier_four_question_is_left_without_its_graph_operation():
    """Tier 4 is the argument for a graph. A question there that does not name
    the operation it needs cannot be designed against."""
    block = DOC.read_text().split("## Tier 4")[1].split("## Tier 5")[0]
    # Named operations only. "sources" and "boundaries" were in this list and
    # are ordinary prose words, so Q79 ("chains cross subject boundaries")
    # satisfied it without naming an operation at all — the assertion was
    # weaker than its name.
    operations = ("shortest path", "longest path", "path enumeration",
                  "transitive closure", "reachability", "centrality",
                  "cycle detection", "graph diameter", "articulation points",
                  "descendant", "ancestor", "set cover", "frontier",
                  "set difference", "intersection", "blast radius",
                  "reachability from sources")
    for question in re.split(r"\*\*Q\d+", block)[1:]:
        # Whitespace collapsed first: the operation is often wrapped across two
        # lines, and matching the raw text silently missed those.
        flat = " ".join(question.lower().split())
        assert any(op in flat for op in operations), flat[:90]


def test_the_prose_totals_agree_with_the_counted_ones():
    """The table is machine-checked and the prose two paragraphs below it was
    not — which is how "the schema has to serve the 73" survived next to a
    table saying 74. Every total restated in words is checked here."""
    real = counted()
    totals = {k: sum(t[k] for t in real.values()) for k in ["questions", *MARKS]}
    text = DOC.read_text()
    words = {73: "Seventy-three", 74: "Seventy-four", 75: "Seventy-five"}

    answerable = totals["✅"]
    assert words[answerable] in text, f"the prose does not say {answerable}"
    for wrong, word in words.items():
        if wrong != answerable:
            assert word not in text, f"prose still claims {wrong}"

    assert f"serve the {answerable}" in text
    assert f"{totals['❌']} blocked" in text.replace("Fourteen", "14")
