"""`docs/questions.md` read against itself — edtech-kg#22.

Split from `test_question_traversals.py` at the 500-line limit. Split by
SUBJECT: this file checks the DOCUMENT — that every question is seen, that the
marks the parser reads match the table the page prints, and that no re-mark
left a fragment behind. That file checks the `.cypher` traversals.
"""

from __future__ import annotations

import re
from collections import Counter

from tests.spelling import spelled

from tests.questions_document import QUESTIONS, blocks, marks, prose_only


def test_the_parser_reads_every_question_in_the_document():
    """`> 50` was the old bound and it was far too loose.

    The parser saw 97 of 102 and reported 18 of those as unmarked, so 79 were
    classified correctly and the bound passed anyway. An unmarked question is
    exempt from the ratchet below, so twenty-three answerable questions could
    have had no traversal and nothing would have said so.

    Counted against the document rather than a number written here, and
    nothing may be left unmarked — "unmarked" is the state that quietly
    excuses a question.
    """
    found = marks()
    # CONTIGUITY, not `set(marks()) == {m.group(1) for m in QUESTION.finditer(…)}`.
    # That compared `QUESTION` with itself — `marks()` reads its blocks from
    # the same regex — so it held however many questions the regex was blind
    # to. The document numbers its questions from 1 without gaps, and a
    # question the parser cannot see leaves a hole that nothing else fills.
    numbers = sorted(int(q[1:]) for q in found)
    assert numbers, "the parser read no questions at all from questions.md"
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"the parser read {len(numbers)} questions and they are not a run from "
        f"Q1 — it is blind to "
        f"{sorted(set(range(1, max(numbers) + 1)) - set(numbers))}")
    unmarked = [q for q, state in found.items() if state == "unmarked"]
    assert not unmarked, (
        f"{unmarked} carry no status, so the ratchet cannot tell whether they "
        f"need a traversal")
    # NOT `{"ok", "caveat", "no"} <= set(...)`, which demanded the document
    # always hold at least one ❌ and would have failed the day the last gap
    # was closed — a test that fails on the outcome the work is for.
    assert set(found.values()) <= {"ok", "caveat", "no"}, (
        f"unexpected marks: {sorted(set(found.values()) - {'ok', 'caveat', 'no'})}")


def test_the_tally_the_document_prints_is_the_one_the_parser_reads():
    """The document's own table is machine-checked by `test_questions.py`
    against a different parser. If the two disagree, one of them is wrong
    about the same file — and this one drives which questions need a
    traversal."""
    counted = Counter(marks().values())
    text = QUESTIONS.read_text(encoding="utf-8")
    row = re.search(r"\| \*\*Total\*\* \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \| "
                    r"\*\*(\d+)\*\* \| \*\*(\d+)\*\* \|", text)
    assert row, "the totals row is no longer in questions.md"
    total, ok, caveat, no = (int(g) for g in row.groups())
    assert (counted["ok"], counted["caveat"], counted["no"]) == (ok, caveat, no), (
        f"the document's table says {ok}/{caveat}/{no} and this parser reads "
        f"{counted['ok']}/{counted['caveat']}/{counted['no']}")
    assert sum(counted.values()) == total


def test_no_question_carries_an_orphaned_fragment():
    """A by-line re-mark leaves the continuation behind, and the tier count
    does not notice.

    Q75's re-mark left two orphan lines and the document's own guards caught it
    — the tier read 21 questions. Q78's left one, and nothing caught it,
    because the fragment does not begin with `**Q` so the count stayed at 20.
    The ratchet detects one shape of this bug and not the other.

    What the fragment DOES carry is an unmatched `*`: `cover over paths.*` is
    the tail of an italic whose opening went with the replaced line. Emphasis
    markers pair, so an odd count in a block is a truncated one — measured,
    Q78 was the only block in the document with one.

    A PROXY for truncation, not a Markdown check. The message says emphasis
    because that is the symptom, and the next person who trips it should know
    they are looking at a truncation heuristic.

    Asterisks inside `code spans` are excluded, and that is not a nicety: the
    Q71 re-mark quotes a Cypher fragment whose `*` is a path quantifier, and
    counting it failed this test on a block that was perfectly well formed. A
    literal asterisk in PROSE still fails, and the fix then is to escape it,
    because the pairing is what makes this mean anything.
    """
    ragged = {q: prose_only(block).count("*") for q, block in blocks().items()
              if prose_only(block).count("*") % 2}
    assert not ragged, (
        f"these questions have unbalanced emphasis markers, which is what a "
        f"line-replaced re-mark leaves behind: {ragged}. Replace the whole "
        f"block, not its first line.")


#: The questions blocked by the missing Course-to-Programme join, named rather
#: than counted by regex. `docs/questions.md` has a section for them and
#: `benchmarks/questions/tier-5-multi-domain.cypher` explains the tier's share.
#:
#: This was "nine" in both files and matched neither: the tier holds four and
#: the document holds six. Nobody typed nine from a measurement — it was
#: carried from an earlier draft and restated, which is how every stale figure
#: in this repo has arrived.
#: Five are BLOCKED and have no query. Q62 and Q77 are CAVEATED. Q62's text says
#: "held at a caveat rather than blocked outright, because the narrowed reading
#: is the one a student asks and it is fully answered". Split, and the marks
#: asserted, because the first version of this called all six blocked while
#: Q62 said otherwise — the exact defect this file is correcting, reintroduced
#: in the correction. Citation alone cannot tell them apart.
TURNING_ON_THE_MISSING_JOIN = {
    "Q62": "caveat", "Q77": "caveat", "Q75": "no", "Q81": "no",
    "Q83": "no", "Q89": "no", "Q90": "no",
}


def test_the_missing_join_blocks_exactly_the_questions_the_documents_name():
    """Both figures, held to the questions themselves.

    A question stops citing the join, or a new one starts, and the two prose
    counts go stale silently — there is no other check on them, which is
    exactly how "nine" survived in two files at once.
    """
    citing = {q for q, text in blocks().items()
              if re.search(r"#66|academic edge|geography wearing", text)}
    assert citing == set(TURNING_ON_THE_MISSING_JOIN), (
        f"the questions citing the missing academic join are "
        f"{sorted(citing, key=lambda q: int(q[1:]))}, and the documents name "
        f"{list(TURNING_ON_THE_MISSING_JOIN)}. Update both prose counts, in "
        f"docs/questions.md and in tier-5-multi-domain.cypher.")

    # THE MARKS, not only the membership. A question flipping ❌ to ✅ would
    # otherwise stay in this set silently, and the section would keep calling
    # it blocked.
    status = marks()
    wrong = {q: status[q] for q, expected in TURNING_ON_THE_MISSING_JOIN.items()
             if status[q] != expected}
    assert not wrong, (
        f"{wrong} no longer carry the marks this section describes — five are "
        f"blocked and Q62 is caveated, and the prose says which is which.")

    document = QUESTIONS.read_text(encoding="utf-8")
    assert "## The missing academic join" in document, (
        "the finding that blocks the most questions has no section again")
    section = document.split("## The missing academic join", 1)[1].split("\n## ", 1)[0]
    # WORD-BOUNDED. `"Q9" in section` is satisfied by `Q90`, so a question in
    # the Q1-Q9 range joining this set would go unchecked.
    unnamed = [q for q in TURNING_ON_THE_MISSING_JOIN
               if not re.search(rf"\b{q}\b", section)]
    assert not unnamed, (
        f"the section does not name {unnamed}, which the join blocks")

    # ONE DIRECTION, as `tests/spelling.py` says in its own docstring: read the
    # document's word and compare ints. The first version of this held a
    # `{4: "FOUR"}` table and asserted the literal — the reverse direction that
    # module was written to reject, and it wedges: rewriting the header as
    # "Four of those ten" in ordinary sentence case is a correct,
    # count-preserving edit that would turn this red with no way out but
    # editing the test. It also shadowed the repo's own `spelled`.
    tier = (QUESTIONS.parents[1] / "benchmarks" / "questions"
            / "tier-5-multi-domain.cypher").read_text(encoding="utf-8")
    in_tier = [q for q in TURNING_ON_THE_MISSING_JOIN if int(q[1:]) in range(81, 95)]

    for pattern, count, what in (
            (r"(\w+) of those ten", len(in_tier), "tier 5's share"),
            (r"(\w+) across the document", len(TURNING_ON_THE_MISSING_JOIN),
             "the document-wide count")):
        found = re.search(pattern, tier)
        assert found, f"tier 5's header no longer states {what}"
        assert spelled(found.group(1)) == count, (
            f"tier 5's header says {found.group(1)!r} for {what} and the "
            f"questions say {count} — this figure was 'nine' in two files at "
            f"once, which is what this test exists for")


#: The cluster row's OTHER half: questions in "Rules joining the two tiers"
#: that are there because no source publishes the rule, not because the schema
#: lacks an edge. Tagged #41 and #42 in their own blocks.
NO_PUBLISHED_SOURCE = ("Q39", "Q57", "Q58", "Q93")


def test_the_cluster_row_and_the_join_section_describe_the_same_split():
    """Nine and six, reconciled — and the guard can SEE the row now.

    `blocks()` reads question blocks, and the Counts tables live outside every
    one of them, so the cluster row was structurally invisible to the test
    above. The document said "nine" in that row and "six" in the new section
    with nothing tying them together, which is the failure this file exists to
    catch, one table further down.

    They are different populations and both are right: the row's reason is
    compound. Four of its nine have no published source; the other five are
    the ones with a source and no schema edge. Q62 is in neither the row nor
    the ❌ count, because it is answered with a caveat.
    """
    document = QUESTIONS.read_text(encoding="utf-8")
    row = [line for line in document.splitlines()
           if line.startswith("| **Rules joining the two tiers**")]
    assert len(row) == 1, f"the cluster row is {row}"
    # BOTH HALVES, split on the `·` the row uses to separate them. Asserting
    # the union passes when a question moves from one side to the other, which
    # is the only edit likely to happen here — measured: moving Q93 across the
    # separator left this green.
    questions_cell = row[0].split("|")[2]
    assert "·" in questions_cell, (
        "the cluster row no longer separates its two reasons, so nothing "
        "distinguishes 'no published source' from 'no schema edge' in it")
    unsourced, unjoined = (re.findall(r"\bQ\d+\b", half)
                           for half in questions_cell.split("·", 1))

    blocked = [q for q, mark in TURNING_ON_THE_MISSING_JOIN.items() if mark == "no"]
    assert set(unjoined) == set(blocked), (
        f"the cluster row's schema-edge half is "
        f"{sorted(unjoined, key=lambda q: int(q[1:]))} and this section "
        f"describes {sorted(blocked)}")
    assert set(unsourced) == set(NO_PUBLISHED_SOURCE), (
        f"the cluster row's no-source half is "
        f"{sorted(unsourced, key=lambda q: int(q[1:]))}, not "
        f"{list(NO_PUBLISHED_SOURCE)}")
    named = unsourced + unjoined

    caveated = [q for q, mark in TURNING_ON_THE_MISSING_JOIN.items() if mark != "no"]
    assert not set(caveated) & set(named), (
        f"{caveated} is answered with a caveat and the cluster row lists "
        f"blocked questions — it should not appear there")

    section = document.split("## The missing academic join", 1)[1].split("\n## ", 1)[0]
    # NOT "subset" any more. #143 moved Q77 into this finding and it is ⚠️, so
    # it is not in the cluster row at all — the two sets OVERLAP on the five
    # blocked ones rather than one containing the other. The word changed
    # because the relationship did.
    assert "overlaps" in section and "compound" in section, (
        "the section no longer explains how its seven relate to the row's "
        "nine, and a reader comparing the two gets no answer")
    caveated = [q for q, mark in TURNING_ON_THE_MISSING_JOIN.items() if mark != "no"]
    assert all(re.search(rf"\b{q}\b", section) for q in caveated), (
        f"{caveated} are caveated members of this finding and the section has "
        f"to name them — they are the ones a reader would otherwise count as "
        f"unanswerable")


def test_the_mark_key_does_not_claim_every_gap_is_a_data_gap():
    """`❌` read "needs data we do not have". Measured over the 25 that carry
    it, that is a plurality and not the whole: some are the missing join, some
    are properties no schema declares, and two are constructs this engine
    cannot express. A key that names one cause invites a reader to assume it."""
    document = QUESTIONS.read_text(encoding="utf-8")
    key = [line for line in document.splitlines() if line.startswith("| ❌ |")]
    assert len(key) == 1, f"the key row for ❌ is {key}"
    assert "the reason is on the question" in key[0]
