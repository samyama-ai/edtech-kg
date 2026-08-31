"""A table row stranded outside its table — the defect #74's own page shipped.

Separate from `tests/test_docs_links.py` so that two open branches are not
both appending to one file: the test-count line in `README.md` already taught
this repo what that costs at merge time. `DOCS` is imported rather than
rebuilt, so this check covers whatever that module decides the document set is.
"""

from __future__ import annotations

import re

import pytest

from tests.test_docs_links import DOCS

SEPARATOR = re.compile(r"\A\|?[\s:|-]+\|[\s:|-]*\Z")


def _is_row(line: str) -> bool:
    """A line this checker is willing to read as a table row.

    Outer pipes required. This repo writes every table that way, and the
    looser form — `a | b` with no outer pipes — cannot be told apart from
    ordinary prose containing a pipe without guessing. Rather than guess, the
    looser form is REFUSED elsewhere in this module rather than silently
    skipped: see `test_no_document_uses_a_table_style_this_check_cannot_read`.
    """
    return len(line) > 1 and line.startswith("|") and line.endswith("|")


def _code_free_lines(text: str) -> list[tuple[int, str]]:
    """Every line outside a code block, with its index.

    BOTH block forms. Fenced blocks were handled; four-space indented blocks
    were not, so an indented example containing pipes was scanned as prose.
    The index travels with the line because the check that follows has to look
    at what comes NEXT, and a whole-document search cannot.
    """
    out, fence = [], False
    for i, raw in enumerate(text.splitlines()):
        stripped = raw.strip()
        if stripped.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        # Indented code — four spaces, which is the other block form and the
        # one the first version missed. Skipped UNCONDITIONALLY: the first
        # attempt at this exempted indented lines that look like rows, which
        # un-skipped exactly the case it was written to skip.
        #
        # The cost is a table indented under a list item, which markdown also
        # allows and which this then stops checking. This repo writes none, and
        # a checker that skips a rare form is better than one that reads code
        # as prose.
        if raw.startswith("    "):
            continue
        out.append((i, stripped))
    return out


def rows_that_open_a_block(text: str) -> list[tuple[int, str]]:
    """Rows with no row above them — candidates, not yet orphans.

    A markdown table is a contiguous run of lines. Insert a heading or a
    paragraph into the middle of one and every row below it stops being a
    table and renders as a stray line of pipe-delimited text — invisible in
    the source, where it still looks exactly like a row.

    Opening a block is legitimate for a HEADER and for nothing else, so the
    caller decides which of these is stranded. Named for what it returns: the
    earlier name promised orphans and handed back candidates, which is the
    kind of mismatch that gets a caller to trust the list.
    """
    lines = _code_free_lines(text)
    previous = ""
    opening = []
    for index, line in lines:
        if _is_row(line) and not _is_row(previous):
            opening.append((index, line))
        previous = line
    return opening


@pytest.mark.parametrize("document", DOCS, ids=lambda p: p.name)
def test_no_table_row_is_stranded_outside_its_table(document):
    """`docs/sources/course-prerequisites.md` shipped one.

    A section heading was inserted before the last row of a table, orphaning
    "Carrying free-text requirements as well" after a paragraph — on the page
    whose accuracy is the entire point of that change. Nothing failed; the row
    simply rendered as text, and a reviewer found it.
    """
    lines = document.read_text(encoding="utf-8").splitlines()
    for index, row in rows_that_open_a_block("\n".join(lines)):
        # THE NEXT LINE, at this row's own position. A whole-document search
        # for the row followed by a separator passes as soon as the same text
        # appears anywhere with a separator under it — so a table repeated on
        # a page made every orphaned copy of its header invisible.
        following = lines[index + 1].strip() if index + 1 < len(lines) else ""
        assert SEPARATOR.match(following), (
            f"{document.name} line {index + 1}: this row is not attached to a "
            f"table — {row[:80]}")


@pytest.mark.parametrize("document", DOCS, ids=lambda p: p.name)
def test_no_document_uses_a_table_style_this_check_cannot_read(document):
    """Refuse the table form this checker skips, rather than skip it.

    Markdown allows a table without outer pipes. `_is_row` cannot recognise
    one without also matching prose, so such a table would pass this file
    while being exactly as strandable — a silent gap in a guard, which is
    worse than a guard that says what it cannot do.

    Detected by its separator: a `|---|` line whose row above has no outer
    pipes is a table written in the form this check does not cover.
    """
    lines = document.read_text(encoding="utf-8").splitlines()
    for index, line in _code_free_lines("\n".join(lines)):
        if not SEPARATOR.match(line) or _is_row(line):
            continue
        above = lines[index - 1].strip() if index else ""
        assert not above or _is_row(above), (
            f"{document.name} line {index + 1}: this table is written without "
            f"outer pipes, which this check cannot read. Add the outer pipes "
            f"so stranded rows in it would be caught — {above[:70]}")
