"""The question count table must match the questions.

Written after the first version of that table was hand-counted and got three of
its six rows wrong. A summary table nobody checks is how a document starts
lying about itself.
"""

import re
from pathlib import Path

from tests.spelling import spelled

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
            #
            # Failure mode, for whoever debugs this next: the count is over the
            # whole question block, so a question whose explanatory prose
            # legitimately contains a status mark — quoting another question's
            # status, say — turns the suite red for the wrong reason. If that
            # happens, the prose is the thing to change, not this.
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
    """Derived from the table, not hardcoded. A literal here would be the one
    number in this file needing a hand edit when the document grows — the class
    of thing the rest of it was written to eliminate."""
    counts = counted()
    assert sum(t["questions"] for t in counts.values()) == tabulated()["Total"]["questions"]
    # And the headline sentence agrees with both.
    claimed = int(re.search(r"\*\*(\d+) questions, tiered", DOC.read_text()).group(1))
    assert claimed == sum(t["questions"] for t in counts.values())


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
    # The COUNT is what this test checks, so it must not be in the anchor that
    # finds the section. Splitting on "in five clusters" made adding a sixth
    # raise IndexError from the split rather than fail an assertion — a test
    # that breaks instead of reporting, on the change it exists to notice.
    text = DOC.read_text()
    anchor = re.search(r"blocked\*\*, in \w+ clusters", text)
    assert anchor, "the blocked-clusters sentence changed shape"
    clusters = text[anchor.end():]
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
    # BOTH HALVES. This read `**<word> answerable` and compared it to the ✅
    # count alone — while the key calls ⚠️ "answerable, with a caveat that must
    # travel with the answer". One figure could not be right about both, and
    # #143 moved 7 questions from ✅ to ⚠️, which is exactly when the ambiguity
    # starts to matter: 58 and 77 are both defensible answers to "how many are
    # answerable" and the document has to say which it means.
    outright = re.search(r"\*\*(\w+(?:-\w+)?) answered outright", text)
    assert outright, "the headline sentence no longer states the ✅ count"
    assert spelled(outright.group(1)) == totals["✅"]

    caveated = re.search(r"and (\w+(?:-\w+)?) with a caveat", text)
    assert caveated, "the headline sentence no longer states the ⚠️ count"
    assert spelled(caveated.group(1)) == totals["⚠️"]

    both = re.search(r"(\w+(?:-\w+)?)\s*\n?answerable in all", text)
    assert both, "the headline sentence no longer states the two together"
    assert spelled(both.group(1)) == totals["✅"] + totals["⚠️"]

    blocked = re.search(r"\*\*(\w+(?:-\w+)?) blocked\*\*", text)
    assert blocked, "the blocked sentence changed shape"
    assert spelled(blocked.group(1)) == totals["❌"]

    # The schema has to serve everything answerable, caveated included.
    assert f"serve the {totals['✅'] + totals['⚠️']}" in text

    # THE TIER-4 CLAUSE, in the same sentence and the same reading. It said
    # "thirteen of the twenty tier-4 questions among them" while "them" was the
    # seventy-seven — switching from ✅+⚠️ to ✅ alone inside the sentence that
    # argues a figure has to say which reading it means. Nothing read this
    # clause, so nothing caught it.
    tier_four = re.search(r"and ([\w-]+) of the ([\w-]+) tier-4", text)
    assert tier_four, "the headline no longer states a tier-4 share"
    tier = counted()["4 — graph algorithms"]
    among = tier["✅"] + tier["⚠️"]
    assert spelled(tier_four.group(1)) == among, (
        f"the headline says {tier_four.group(1)!r} of the tier-4 questions are "
        f"among the answerable and {among} are — ✅ plus ⚠️, the same reading "
        f"the sentence uses for its own total.")
