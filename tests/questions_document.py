"""Reading `docs/questions.md` — the questions, their marks, their blocks.

A non-test module because two test files need it: `test_questions_document.py`
checks the document against itself, and `test_question_traversals.py` needs to
know which questions are answerable before it can demand a traversal for them.

Split out when `test_question_traversals.py` passed the 500-line review limit.
Split by SUBJECT: this reads the document, that reads the `.cypher` files.
"""

from __future__ import annotations

import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[1]


QUESTIONS = ROOT / "docs" / "questions.md"

#: A question STARTS a block. Two spellings ship — `**Q1.** text` and
#: `**Q61. text**` — and the second was invisible to a parser that required
#: the closing `**` right after the number, so five questions were not read at
#: all. Marks are read from the block, not the line, because a question that
#: wraps carries its mark on the continuation.
QUESTION = re.compile(r"^\*\*(Q\d+)\.", re.M)


#: A tier heading. The document is questions AND prose about them, and only the
#: tier sections hold questions — `## The missing academic join`,
#: `## The competency gap` and `## Counts` are narrative.
TIER_HEADING = re.compile(r"^## (Tier \d+ .+)$", re.M)


def tiers() -> dict[str, str]:
    """Each tier's body, and nothing else in the document — edtech-kg#146.

    Both parsers over this file used to read ALL of it, so ordinary prose in a
    narrative section was interpreted as question structure. Two shapes bit,
    within one afternoon of each other and in the same section:

    - a bold run opening `**Q` and a number DECLARES a question, so writing
      "**Q62 is caveated, not blocked**" in a paragraph made the tally read 103
      questions and gave tier 6 nine
    - every ✅ ⚠️ ❌ is counted to catch a question carrying two, so "neither the
      row nor the ❌ count" made tier 6 report nine marks for eight questions

    Both were worked around by telling the writer which characters to avoid,
    in a note sitting in reader-facing prose. The document is for readers; its
    prose should not be shaped around a parser.

    A tier ends at the next `##` heading of ANY kind, not the next tier — tier
    6 is followed by narrative, and taking the next tier heading would swallow
    it, which is the bug in the other direction.
    """
    text = QUESTIONS.read_text(encoding="utf-8")
    headings = list(TIER_HEADING.finditer(text))
    found = {}
    for heading in headings:
        after = text.index("\n", heading.end())
        end = text.find("\n## ", after)
        found[heading.group(1)] = text[after:end if end != -1 else len(text)]
    return found


def blocks() -> dict[str, str]:
    """Each question with everything up to the next one.

    Line-by-line was wrong in two ways at once. It required `**Qn.**`, so
    `**Q61. What is…**` was not a question; and it read the mark from the
    FIRST physical line, so a question wrapping onto a second was reported
    unmarked while its mark sat one line down. Eighteen were, and an unmarked
    question is exempt from the ratchet — so eighteen answerable questions
    could have had no traversal and nothing would have said so.
    """
    found = {}
    for body in tiers().values():
        starts = [(m.group(1), m.start()) for m in QUESTION.finditer(body)]
        for index, (name, at) in enumerate(starts):
            end = starts[index + 1][1] if index + 1 < len(starts) else len(body)
            found[name] = body[at:end]
    return found


def marks() -> dict[str, str]:
    """Every question in the document, with its mark."""
    found = {}
    for name, block in blocks().items():
        # The FIRST mark in the block, by position. A fixed priority order
        # reads a status character mentioned in an explanation as the
        # question's own mark — which is what happened when Q19's re-marking
        # said what it used to be.
        # `\u26a0` WITHOUT the variation selector. `"⚠️"` is two code points,
        # U+26A0 followed by U+FE0F, and an editor that writes the bare
        # U+26A0 — several do — produced a question this parser called
        # unmarked, which is the state that exempts it from the ratchet.
        positions = [(block.index(c), state) for c, state in
                     (("\u2705", "ok"), ("\u26a0", "caveat"), ("\u274c", "no"))
                     if c in block]
        found[name] = min(positions)[1] if positions else "unmarked"
    return found


def prose_only(block: str) -> str:
    """The block with `code spans` removed.

    An asterisk inside backticks is code — a Cypher `*1..1`, a glob, a
    multiplication — and counting it as emphasis is how a well-formed block
    fails a truncation check.
    """
    return re.sub(r"`[^`]*`", "", block)
