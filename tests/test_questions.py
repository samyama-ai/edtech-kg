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
            # Occurrences, not distinct membership. Membership could not see a
            # question carrying the same mark twice, though the test that reads
            # these counts claims to catch "two marks".
            for mark in MARKS:
                marks[mark] += question.count(mark)
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
    # Self-checking, the same discipline the strict zip applies to counted():
    # a renamed "## Counts" heading otherwise returns {} and the tier tests
    # fail with KeyError instead of saying what is wrong.
    assert len(out) == len(TIERS) + 1, f"parsed {len(out)} rows from the Counts table"
    return out


def test_the_document_has_the_questions_it_claims():
    assert sum(t["questions"] for t in counted().values()) == 102


def test_every_question_carries_exactly_one_status():
    """Two earlier versions could not fail as named. The first broke out of the
    mark loop on the first match, so every question contributed exactly one by
    construction. The second tested distinct membership, so it caught ✅ / ❌ but
    not ✅ … ✅. Counting occurrences catches zero, two different, and two of
    the same."""
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
    """Scoped to the tier bodies. Scanning the whole document would break on a
    prose cross-reference written as **Q61** outside a tier — and the range
    assertion alone implies both sortedness and uniqueness."""
    body = DOC.read_text().split("## Tier 1")[1].split("## The competency gap")[0]
    numbers = [int(n) for n in re.findall(r"\*\*Q(\d+)", body)]
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
                  "set difference", "intersection", "blast radius")
    for question in re.split(r"\*\*Q\d+", block)[1:]:
        # Whitespace collapsed first: the operation is often wrapped across two
        # lines, and matching the raw text silently missed those.
        flat = " ".join(question.lower().split())
        assert any(op in flat for op in operations), flat[:90]


SPELLED = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
           "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
           "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
           "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
           "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def spelled(word: str) -> int:
    """"Seventy-four" -> 74. Keeps the tests from carrying a map of the
    particular numbers the document happens to say today — the previous version
    raised KeyError the moment a total left its window, turning a self-checking
    test into an opaque traceback in a document designed to grow."""
    return sum(SPELLED[part] for part in word.lower().split("-"))


def test_the_competency_gap_names_the_questions_it_blocks():
    """"Six questions above are blocked on the same thing" was three — a
    hand-counted figure in a document whose central argument is that it no
    longer contains any."""
    body = DOC.read_text().split("## Tier 1")[1].split("## The competency gap")[0]
    naming = [int(n) for n, text in zip(*[iter(re.split(r"\*\*Q(\d+)", body)[1:])] * 2)
              if "competency" in text.lower()]
    section = DOC.read_text().split("## The competency gap")[1]
    claimed = spelled(re.search(r"^(\w+(?:-\w+)?) questions", section.strip()).group(1))
    assert claimed == len(naming), f"the section claims {claimed}, {len(naming)} name it"
    for number in naming:
        assert f"Q{number}" in section, f"Q{number} names the gap but is not listed"


def test_every_blocked_question_belongs_to_a_named_cluster():
    """"Fourteen blocked, and they cluster" — four of them fell outside the
    four clusters named, so the sentence was true of ten of the fourteen."""
    body = DOC.read_text().split("## Tier 1")[1].split("## The competency gap")[0]
    blocked = {int(n) for n, text in zip(*[iter(re.split(r"\*\*Q(\d+)", body)[1:])] * 2)
               if "❌" in text.split("**Q")[0]}
    clusters = DOC.read_text().split("blocked**, in five clusters")[1]
    listed = {int(n) for n in re.findall(r"Q(\d+)", clusters.split("That last cluster")[0])}
    assert listed == blocked, f"unclustered: {blocked - listed}; phantom: {listed - blocked}"


def test_the_prose_totals_agree_with_the_counted_ones():
    """The table is machine-checked and the prose two paragraphs below it was
    not — which is how "the schema has to serve the 73" survived next to a
    table saying 74. Every total restated in words is checked here."""
    real = counted()
    totals = {k: sum(t[k] for t in real.values()) for k in ["questions", *MARKS]}
    text = DOC.read_text()

    # Read the spelled-out number out of the prose rather than keeping a map of
    # the numbers the document currently says.
    headline = re.search(r"\*\*(\w+(?:-\w+)?) answerable", text)
    assert headline, "the headline sentence changed shape"
    assert spelled(headline.group(1)) == totals["✅"]

    blocked = re.search(r"\*\*(\w+(?:-\w+)?) blocked\*\*", text)
    assert blocked, "the blocked sentence changed shape"
    assert spelled(blocked.group(1)) == totals["❌"]

    assert f"serve the {totals['✅']}" in text
