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


def orphan_table_rows(text: str) -> list[str]:
    """Rows that open a block, which only a header may legitimately do.

    A markdown table is a contiguous run of lines. Insert a heading or a
    paragraph into the middle of one and every row below it stops being a
    table and renders as a stray line of pipe-delimited text — invisible in
    the source, where it still looks exactly like a row.
    """
    rows, fence, previous = [], False, ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            fence = not fence
            previous = stripped
            continue
        if (not fence and stripped.startswith("|") and stripped.endswith("|")
                and not (previous.startswith("|") and previous.endswith("|"))):
            rows.append(stripped)
        previous = stripped
    return rows


@pytest.mark.parametrize("document", DOCS, ids=lambda p: p.name)
def test_no_table_row_is_stranded_outside_its_table(document):
    """`docs/sources/course-prerequisites.md` shipped one.

    A section heading was inserted before the last row of a table, orphaning
    "Carrying free-text requirements as well" after a paragraph — on the page
    whose accuracy is the entire point of that change. Nothing failed; the row
    simply rendered as text, and a reviewer found it.
    """
    text = document.read_text(encoding="utf-8")
    for row in orphan_table_rows(text):
        # A row that legitimately opens a table is its header, and a header is
        # always followed by the `|---|` separator. Anything else is stranded.
        assert re.search(re.escape(row) + r"\n\s*\|[\s:|-]+\|", text), (
            f"{document.name}: this row is not attached to a table — {row[:80]}")
