"""The six-row parse table in `docs/schema.md`, executed rather than believed.

It was the one substantive claim in that file nothing ran. Every constraint in
The schema files are executed against a live engine by
`tests/test_schema_engine.py`; this table was measured by hand and written
down, which is the shape of claim the file's own argument says not to trust.

**The rows are read OUT OF the document**, not restated here. A second copy of
the six forms in this file would be a list that agrees with the page until
someone edits one of them, and then quietly stops testing what the page says.
Read this way, editing the page changes what runs.

**Why it goes stale silently.** samyama-graph#21 asks for pattern predicates in
`WHERE` to parse. On the day that lands, four of these six rows become wrong
and nothing would say so — the page would go on calling the natural form a
parse error and go on recommending `EXISTS { }`. That matters past hand-written
Cypher: text-to-Cypher emits `WHERE NOT (a)-[:R]->(b)` because that is what its
training data contains, so NLQ and the MCP layer inherit whatever this table
gets wrong.

Measured 2026-09-01 against **1.7.0**, where all six verdicts still hold. The
page states 1.1.0, which is what #24 owns pinning.
"""

from __future__ import annotations

import re

import pytest

from tests.test_schema_engine import SAMYAMA_URL, query, require_engine
from tests.schema_source import SCHEMA_DOC

#: The table's own heading, which is also where its version claim lives.
HEADING = re.compile(r"^\| Form \| Parses in ([\d.]+) \|", re.M)

#: A row: the form in backticks, then a verdict cell. `✅` is a pass and
#: anything containing "parse error" is a refusal — matched on the words rather
#: than on the tick, because a document may reasonably reword the cell.
ROW = re.compile(r"^\| `([^`]+)` \| (.+?) \|$", re.M)


#: What `cases()` yields when the table cannot be read, so that a malformed
#: document produces ONE failing test with a message rather than an error
#: during collection. An assertion in a `parametrize` argument runs at import
#: time and interrupts the whole session — every other test in the repo stops
#: reporting because a markdown table lost a row.
UNREADABLE = "<the parse table in docs/schema.md could not be read>"


def table() -> list[tuple[str, bool]]:
    """Every row of the parse table, as (form, should_parse). Tolerant: it
    reports what it found and lets the tests judge it."""
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    heading = HEADING.search(text)
    if not heading:
        return []

    body = text[heading.end():]
    end = body.index("\n\n") if "\n\n" in body else len(body)
    rows = []
    for form, verdict in ROW.findall(body[:end]):
        if set(verdict.strip()) <= {"-"}:            # the separator row
            continue
        rows.append((form, "parse error" not in verdict.lower()))
    return rows


def cases() -> list[tuple[str, object]]:
    """Always at least one case. Parametrising over an empty list makes the
    test disappear from the run entirely, which reads as success — the failure
    this whole file exists to prevent, in its own scaffolding."""
    return table() or [(UNREADABLE, None)]


def statement_for(form: str) -> str:
    """The table lists FRAGMENTS. Each needs a query around it to be parsed at
    all, and the surrounding query must be one the engine otherwise accepts, or
    a failure here would be about the wrapper rather than the form."""
    if form.startswith("OPTIONAL MATCH"):
        return ("MATCH (c:Course) OPTIONAL MATCH (c)-[r:REQUIRES]->() "
                "WITH c, r WHERE r IS NULL RETURN c LIMIT 1")
    return f"MATCH (c:Course) {form} RETURN c LIMIT 1"


def test_the_table_is_read_and_has_all_six_rows():
    """A parser that returns nothing makes every assertion below vacuous.

    Six is pinned: a regex that silently matches four rows instead of six
    reports a green run over a table it only half read.
    """
    rows = table()
    assert len(rows) == 6, f"read {len(rows)} rows from the parse table, not 6: {rows}"
    assert [parses for _, parses in rows] == [False] * 4 + [True] * 2, (
        f"the table's verdicts are no longer four refusals then two passes: "
        f"{rows}")


def test_the_version_the_table_claims_is_stated():
    """The verdicts are true OF A VERSION. A table that does not say which is a
    table nobody can check — and #24 exists because this repo has published
    figures without saying what produced them."""
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    heading = HEADING.search(text)
    assert heading and heading.group(1), "the parse table names no engine version"


@pytest.mark.parametrize("form, should_parse", cases(),
                         ids=lambda v: v if isinstance(v, str) else "")
def test_each_form_in_the_table_behaves_as_the_table_says(form, should_parse):
    """Run it. The direction is in the message, because the day this fires the
    reader needs to know whether the engine GAINED the syntax or LOST it —
    those call for opposite edits to the page."""
    if should_parse is None:
        pytest.fail(
            f"{form} — the heading `| Form | Parses in <version> |` is gone, "
            f"so nothing below was executed")
    require_engine()

    result = query(SAMYAMA_URL, statement_for(form))
    error = result.get("error")
    # A 5xx is the engine dying, not the engine refusing. Without this an
    # unhealthy instance reads as "this form does not parse", which is exactly
    # the wrong conclusion to write into a document about syntax.
    if result.get("transport"):
        pytest.fail(f"the engine failed rather than answered for {form!r}: {error}")

    parsed = error is None
    if parsed == should_parse:
        return

    direction = ("GAINED the syntax — the table calls this a parse error and "
                 "the engine now accepts it. Four rows may be stale; see "
                 "samyama-graph#21."
                 if parsed else
                 "LOST the syntax — the table says this parses and the engine "
                 f"now refuses it: {error}")
    pytest.fail(
        f"docs/schema.md and the engine at {SAMYAMA_URL} disagree about\n"
        f"    {form}\n"
        f"The engine has {direction}")
