"""`docs/questions.md` read against itself — edtech-kg#22.

Split from `test_question_traversals.py` at the 500-line limit. Split by
SUBJECT: this file checks the DOCUMENT — that every question is seen, that the
marks the parser reads match the table the page prints, and that no re-mark
left a fragment behind. That file checks the `.cypher` traversals.
"""

from __future__ import annotations

import re
from collections import Counter

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
BLOCKED_BY_THE_MISSING_JOIN = ("Q62", "Q75", "Q81", "Q83", "Q89", "Q90")


def test_the_missing_join_blocks_exactly_the_questions_the_documents_name():
    """Both figures, held to the questions themselves.

    A question stops citing the join, or a new one starts, and the two prose
    counts go stale silently — there is no other check on them, which is
    exactly how "nine" survived in two files at once.
    """
    citing = {q for q, text in blocks().items()
              if re.search(r"#66|academic edge|geography wearing", text)}
    assert citing == set(BLOCKED_BY_THE_MISSING_JOIN), (
        f"the questions citing the missing academic join are "
        f"{sorted(citing, key=lambda q: int(q[1:]))}, and the documents name "
        f"{list(BLOCKED_BY_THE_MISSING_JOIN)}. Update both prose counts, in "
        f"docs/questions.md and in tier-5-multi-domain.cypher.")

    document = QUESTIONS.read_text(encoding="utf-8")
    assert "## The missing academic join" in document, (
        "the finding that blocks the most questions has no section again")
    section = document.split("## The missing academic join", 1)[1].split("\n## ", 1)[0]
    unnamed = [q for q in BLOCKED_BY_THE_MISSING_JOIN if q not in section]
    assert not unnamed, (
        f"the section does not name {unnamed}, which the join blocks")

    # SPELLED OUT, because the prose spells its counts out. Matching digits
    # would pass on any file that happens to contain them and fail on this one.
    spelled = {4: "FOUR", 6: "SIX"}
    tier = (QUESTIONS.parents[1] / "benchmarks" / "questions"
            / "tier-5-multi-domain.cypher").read_text(encoding="utf-8")
    in_tier = [q for q in BLOCKED_BY_THE_MISSING_JOIN if int(q[1:]) in range(81, 95)]
    assert f"{spelled[len(in_tier)]} of those ten" in tier, (
        f"tier 5 holds {len(in_tier)} of the ten unanswerable and its header "
        f"says something else — the figure was 'nine' in two files at once")
    assert f"{spelled[len(BLOCKED_BY_THE_MISSING_JOIN)]} across the document" in tier


def test_the_mark_key_does_not_claim_every_gap_is_a_data_gap():
    """`❌` read "needs data we do not have". Measured over the 25 that carry
    it, that is a plurality and not the whole: some are the missing join, some
    are properties no schema declares, and two are constructs this engine
    cannot express. A key that names one cause invites a reader to assume it."""
    document = QUESTIONS.read_text(encoding="utf-8")
    assert "| ❌ | needs data we do not have" not in document
    key = [line for line in document.splitlines() if line.startswith("| ❌ |")]
    assert len(key) == 1, f"the key row for ❌ is {key}"
    assert "the reason is on the question" in key[0]

