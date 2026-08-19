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
    for name, block in zip(TIERS, re.split(r"\n## Tier ", body)):
        marks = dict.fromkeys(MARKS, 0)
        questions = re.split(r"\*\*Q\d+", block)[1:]
        for question in questions:
            segment = question.split("**Q")[0]
            for mark in MARKS:
                if mark in segment:
                    marks[mark] += 1
                    break
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
    operations = ("path", "closure", "reachab", "centrality", "cycle",
                  "diameter", "articulation", "descendant", "ancestor",
                  "set cover", "frontier", "difference", "intersection",
                  "blast radius", "enumeration", "boundaries", "sources")
    for question in re.split(r"\*\*Q\d+", block)[1:]:
        assert any(op in question.lower() for op in operations), question[:90]
