"""Reading `schema/edtech_kg.cypher` — one view of the file, shared by both
test modules that parse it.

Split out when `tests/test_schema_cypher.py` reached 599 lines and was skipped
whole by review as too large to read. The parse tests and the engine tests are
different jobs with different requirements — one needs nothing, the other needs
a running instance — and the helpers were the only reason they shared a file.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "edtech_kg.cypher"
SCHEMA_DOC = ROOT / "docs" / "schema.md"
QUESTIONS = ROOT / "docs" / "questions.md"


def strip_comment(line: str) -> str:
    """Drop a `//` comment, but not a `//` inside a string literal.

    Splitting unconditionally truncates `MERGE (n {url: 'https://x'})` at the
    scheme. No statement in the schema carries a URL today — the URLs are all
    in comments — so the naive split has never done damage, and would the day
    a default or an example value was added.

    Quote tracking only, no parser: 1.1.0 has no escape sequence inside a
    string literal, so a quote always opens or closes one and never appears
    within. Same function as `etl/load_pwcs.strip_comment`, and deliberately
    not imported from it — these tests must not depend on the code they check.
    """
    quote = None
    for i, character in enumerate(line):
        if quote:
            if character == quote:
                quote = None
        elif character in "'\"":
            quote = character
        elif character == "/" and line[i:i + 2] == "//":
            return line[:i]
    return line


def code(text: str | None = None) -> str:
    """The file with every comment removed — the single view of what executes.

    Trailing comments count, not only whole-comment lines. `CREATE INDEX ON
    :Completion(year);  // annual` would otherwise carry the comment into the
    statement, and a `;` inside one would split a statement in half.

    `text` is here so the tests can exercise THIS function against a hazard the
    file does not contain yet. A test that reimplements the stripping on a
    synthetic line proves the technique and says nothing about the code that
    ships — the dead-path test, which this repo has shipped before.
    """
    source = SCHEMA.read_text(encoding="utf-8") if text is None else text
    return "\n".join(strip_comment(line) for line in source.splitlines())


def statements(text: str | None = None) -> list[str]:
    """Executable statements, comments stripped."""
    return [s.strip() for s in " ".join(code(text).splitlines()).split(";") if s.strip()]


# Both constraint spellings. The file uses the `ON … ASSERT` form because the
# Neo4j-5 `FOR … REQUIRE` form does not parse in 1.1.0 — but a pattern pinned to
# only that form returns an EMPTY list the day the engine catches up and someone
# modernises the file, and every containment check against an empty set passes
# vacuously. The same hazard `first_column` guards against, one file over.
CONSTRAINT = re.compile(
    r"CREATE CONSTRAINT (?:\w+ )?(?:IF NOT EXISTS )?"
    r"(?:ON|FOR) \(\w+:(\w+)\)")


def labels(text: str | None = None) -> list[str]:
    """From the stripped text, so a commented-out constraint is not counted.

    `labels()` and `edges()` used to regex the raw file while `statements()`
    read the stripped one — two views of one file, which is the defect this
    repo keeps finding.

    Whitespace is collapsed before matching, for the same reason `first_column`
    is reflow-tolerant: the pattern spans `CREATE CONSTRAINT … ON (n:Label)`,
    so a declaration wrapped across two lines matches NOTHING, and the label
    then drops silently out of every containment check that reads this list.
    A missing label does not fail those checks — it makes them pass on a
    smaller set, which is the vacuous pass this file exists to prevent.
    """
    return CONSTRAINT.findall(" ".join(code(text).split()))


def patterns(text: str | None = None) -> str:
    """The edge patterns, which live in COMMENTS because they carry no
    constraint — so this one reads the RAW file, deliberately.

    Takes `text` for the same reason `code()` does: so a test can drive it
    with markup the file does not contain, rather than reimplementing it.
    """
    return SCHEMA.read_text(encoding="utf-8") if text is None else text


def edges(text: str | None = None) -> set[str]:
    return set(re.findall(r"-\[:([A-Z_]+)", patterns(text)))


def first_column(table: str) -> set[str]:
    """The backticked names in a markdown table's first column.

    Whitespace-tolerant. The previous patterns required exactly one space
    either side of the pipe, so a formatter reflowing the table — or anyone
    aligning the columns — would yield an EMPTY set and every containment
    check against it would pass vacuously. Callers assert the result is
    non-empty for the same reason.

    Only the first column is read; collecting every backticked word in the
    table picks up the labels in the From/To column, and an edge sharing a name
    with a label would then pass without being documented.
    """
    names: set[str] = set()
    for row in table.splitlines():
        cell = re.match(r"\s*\|([^|]*)\|", row)
        if not cell:
            continue
        names |= set(re.findall(r"`(\w+)`", cell.group(1)))
    return names


def section(text: str, after: str, before: str | None = None) -> str:
    """The slice of a document between two headings, or a readable failure.

    `text.split(heading)[1]` raises `IndexError` the day a heading is reworded
    — a bare traceback naming a list index, from which nobody can tell that a
    document was renamed. Every guard in these files rests on slicing a
    document by its own headings, so the failure mode is worth naming once
    here rather than at each call site.
    """
    parts = text.split(after)
    assert len(parts) > 1, f"no heading {after!r} in this document any more"
    tail = parts[1]
    if before is None:
        return tail
    parts = tail.split(before)
    assert len(parts) > 1, (
        f"{before!r} no longer follows {after!r} in this document")
    return parts[0]


# One declaration, whole, however it is wrapped. `code()` preserves lines, so a
# declaration reflowed across two of them cannot be found by a line-local
# substring — which is the blind spot `labels()` was fixed for, and which two
# key-composition tests reintroduced by locating constraints their own way.
DECLARATION = re.compile(
    r"CREATE CONSTRAINT (?:\w+ )?(?:IF NOT EXISTS )?"
    r"(?:ON|FOR) \(\w+:(\w+)\) (?:ASSERT|REQUIRE) \w+\.(\w+) IS UNIQUE")


def declarations(text: str | None = None) -> list[tuple[str, str]]:
    """Every `(label, key)` the schema declares, wrap-tolerant.

    Whitespace is collapsed before matching, for the reason `labels()` gives:
    a declaration wrapped at the line width matches nothing, drops out of the
    list, and every containment check against the smaller list passes.
    """
    return DECLARATION.findall(" ".join(code(text).split()))


def constraint_line(label: str) -> int | None:
    """The line the declaration of `label` ENDS on, or None.

    Callers want the comment block above a declaration, so they need a line
    number — but they were finding it with `f":{label})" in line`, which is
    exactly the line-local test that misses a wrapped declaration. This walks
    a growing window so a declaration spanning several lines is still located
    by its last line, which is the one the comment block sits above.
    """
    lines = SCHEMA.read_text(encoding="utf-8").splitlines()
    for end in range(len(lines)):
        window = " ".join(" ".join(lines[max(0, end - 4):end + 1]).split())
        for found, _ in DECLARATION.findall(window):
            if found == label:
                return end
    return None
