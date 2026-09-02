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


def blocks() -> dict[str, str]:
    """Each question with everything up to the next one.

    Line-by-line was wrong in two ways at once. It required `**Qn.**`, so
    `**Q61. What is…**` was not a question; and it read the mark from the
    FIRST physical line, so a question wrapping onto a second was reported
    unmarked while its mark sat one line down. Eighteen were, and an unmarked
    question is exempt from the ratchet — so eighteen answerable questions
    could have had no traversal and nothing would have said so.
    """
    text = QUESTIONS.read_text(encoding="utf-8")
    starts = [(m.group(1), m.start()) for m in QUESTION.finditer(text)]
    found = {}
    for index, (name, at) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        # A block also stops at the next HEADING, or the prose between tiers
        # is read as part of the last question in the tier above.
        heading = text.find("\n## ", at)
        if heading != -1 and heading < end:
            end = heading
        found[name] = text[at:end]
    return found


def marks() -> dict[str, str]:
    """Every question in the document, with its mark."""
    found = {}
    for name, block in blocks().items():
        # The FIRST mark in the block, by position. A fixed priority order
        # reads a status character mentioned in an explanation as the
        # question's own mark — which is what happened when Q19's re-marking
        # said what it used to be.
        positions = [(block.index(c), state) for c, state in
                     (("✅", "ok"), ("⚠️", "caveat"), ("❌", "no"))
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
