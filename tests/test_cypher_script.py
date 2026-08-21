"""Reading a .cypher script — the two quote-aware readers, and applying it.

`etl/cypher_script.py` knows nothing about a course catalogue. It reads a file
of Cypher, splits it the way 1.1.0 needs, and sends it.

The two readers have to agree with each other, and once did not: `strip_comment`
was made to respect a string literal and the `;` split was not, so the stripper
preserved `MERGE (n {t: 'a;b'})` and the split then cut it in half. Neither
hazard exists in the shipped schema — no statement there carries a `//` or a
`;` inside a literal — which is exactly when a test is cheapest.
"""

from __future__ import annotations

from etl import cypher_script as script


class Recorder:
    """Every statement the reader would send, in order."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def run(self, query: str):
        self.sent.append(query)
        return {"columns": [], "records": []}


def test_a_semicolon_inside_a_literal_does_not_split_the_statement():
    """`strip_comment` was made quote-aware and the `;` split was not, so the
    pair disagreed: the stripper preserved `MERGE (n {t: 'a;b'})` and the split
    then cut it in half, sending the engine two fragments it rejects.

    No schema statement carries a semicolon in a literal today, which is
    exactly why nothing would have caught the first one that did."""
    assert script.split_statements("MERGE (n:C {t: 'a;b'});\nCREATE INDEX ON :C(y);") \
        == ["MERGE (n:C {t: 'a;b'})", "CREATE INDEX ON :C(y)"]
    assert script.split_statements('MERGE (n:C {t: "x;y"})') == ['MERGE (n:C {t: "x;y"})']
    assert script.split_statements("  \n ;; \n") == []


def test_a_comment_is_stripped_but_a_url_in_a_literal_is_not():
    """Splitting on `//` unconditionally truncates a statement carrying a URL
    at the scheme. No schema statement does today — the URLs are in comments —
    which is the only reason the naive split never did damage."""
    assert script.strip_comment("CREATE INDEX ON :C(year);  // annual") \
        == "CREATE INDEX ON :C(year);  "
    assert script.strip_comment("MERGE (n {url: 'https://x/y'})") \
        == "MERGE (n {url: 'https://x/y'})"
    assert script.strip_comment('MERGE (n {u: "a//b"}) // t') == 'MERGE (n {u: "a//b"}) '
    assert script.strip_comment("// whole line") == ""


def test_apply_schema_does_not_truncate_a_statement_carrying_a_url(tmp_path):
    """`apply_schema` stripped comments by splitting on `//`, which cuts
    `MERGE (n {url: 'https://x'})` at the scheme. No schema statement carries a
    URL today — they are all in comments — which is the only reason the naive
    split never did damage."""
    schema = tmp_path / "s.cypher"
    schema.write_text("// a comment mentioning https://example.org\n"
                      "CREATE CONSTRAINT ON (c:C) ASSERT c.url IS UNIQUE;  // key\n"
                      "MERGE (n:C {url: 'https://example.org/x'});\n")
    engine = Recorder()
    script.apply_schema(engine, quiet=True, schema=schema)
    assert engine.sent == [
        "CREATE CONSTRAINT ON (c:C) ASSERT c.url IS UNIQUE",
        "MERGE (n:C {url: 'https://example.org/x'})"], engine.sent
