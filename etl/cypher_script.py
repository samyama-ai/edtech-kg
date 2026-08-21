"""Reading a .cypher script — comments, statements, and applying it.

Split out of `etl/load_pwcs.py` when it passed the 500-line review limit. Split
by SUBJECT: nothing here knows about a course catalogue. It reads a file of
Cypher, splits it into statements the way 1.1.0 needs them, and sends them.

Both readers are quote-aware, and they have to agree with each other. They did
not once: `strip_comment` was made to respect a string literal and the `;`
split was not, so the stripper carefully preserved `MERGE (n {t: 'a;b'})` and
the split then cut it in half. Quote tracking only, no parser — 1.1.0 has no
escape sequence inside a string literal, so a quote always opens or closes one
and never appears within.
"""

from __future__ import annotations

from pathlib import Path

from etl.engine import Engine

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "edtech_kg.cypher"


def strip_comment(line: str) -> str:
    """Drop a `//` comment, but not a `//` inside a string literal.

    Splitting on `//` unconditionally truncates `MERGE (n {url: 'https://x'})`
    at the scheme. No statement in the schema carries a URL today — the URLs
    are in comments — so the naive split has never done damage, and would the
    day a default or an example value was added.

    Quote tracking only, no full parser: 1.1.0 has no escape sequence inside a
    string literal (see `lit`), so a quote character always opens or closes one
    and never appears within.
    """
    quote = None
    for i, character in enumerate(line):
        if quote:
            if character == quote:
                quote = None
        elif character in "\'\"":
            quote = character
        elif character == "/" and line[i:i + 2] == "//":
            return line[:i]
    return line


def split_statements(text: str) -> list[str]:
    """Split on `;`, but not on a `;` inside a string literal.

    `strip_comment` was made quote-aware and this was not, which left the pair
    inconsistent: the comment stripper would carefully preserve
    `MERGE (n {t: 'a;b'})` and the split would then cut it in half, sending the
    engine two fragments it rejects. No schema statement carries a semicolon in
    a literal today — which is exactly why nothing would have caught the first
    one that did.

    Quote tracking only, no parser, for the reason `strip_comment` gives: 1.1.0
    has no escape sequence inside a string literal, so a quote always opens or
    closes one and never appears within.
    """
    statements, current, quote = [], [], None
    for character in text:
        if quote:
            if character == quote:
                quote = None
        elif character in "'\"":
            quote = character
        elif character == ";":
            statements.append("".join(current))
            current = []
            continue
        current.append(character)
    statements.append("".join(current))
    return [s.strip() for s in statements if s.strip()]


def apply_schema(engine: Engine, quiet: bool = False,
                 schema: Path | None = None) -> int:
    """The constraints, from the schema file — not retyped here.

    A copy would drift from the file the tests execute, which is the defect
    this repo keeps finding: two things that should be one, with only one
    maintained.
    """
    text = (schema or SCHEMA).read_text()
    statements = split_statements(
        "\n".join(strip_comment(line) for line in text.splitlines()))
    for statement in statements:
        engine.run(statement)
    if not quiet:
        print(f"  schema     {len(statements):>5,} statements")
    return len(statements)
