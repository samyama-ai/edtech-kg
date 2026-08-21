"""The schema file must match what the documents claim about it.

`schema/edtech_kg.cypher` is the executable ontology, not prose. The same test
in `regulatory-affairs-kg` caught both a constraint collision and a syntax form
the engine does not parse — neither of which two rounds of reading had found.

No engine. These parse the file and compare it against `docs/schema.md` and
`docs/questions.md`; the tests that need a running instance are in
`tests/test_schema_engine.py`, and the helpers both use are in
`tests/schema_source.py`.

Split out at 599 lines, when review skipped the whole file as too large to
read — the second time a test file in this repo has been the thing nobody
could check.
"""

import re

import pytest

from tests.schema_source import (QUESTIONS, SCHEMA, SCHEMA_DOC, code, edges,
                                 first_column, labels, section, statements)
from tests.spelling import spelled


# --------------------------------------------------------------------------
# the file itself
# --------------------------------------------------------------------------

def test_every_label_is_constrained_once():
    """A label constrained twice is how a key collision gets in."""
    found = labels()
    assert found, "no constraints found — did the file move?"
    duplicates = {label for label in found if found.count(label) > 1}
    assert not duplicates, f"label constrained more than once: {duplicates}"


def test_uses_the_syntax_the_engine_parses():
    """Samyama-Graph 1.1.0 does not parse `CREATE CONSTRAINT ... FOR ... REQUIRE`,
    despite it appearing in the engine's own CYPHER_COMPATIBILITY.md. Guard
    against someone helpfully modernising the file back to Neo4j-5 syntax."""
    executable = " ".join(statements())
    # Word-boundary: REQUIRES contains REQUIRE, so a plain substring test is a
    # landmine the moment an index or property is named that way.
    assert not re.search(r"\bREQUIRE\b", executable), "use `ON (n:L) ASSERT n.p IS UNIQUE`"
    assert "IF NOT EXISTS" not in executable, "does not parse in 1.1.0"


def test_every_statement_is_a_constraint_or_an_index():
    for statement in statements():
        assert statement.startswith(("CREATE CONSTRAINT", "CREATE INDEX")), statement[:60]


def test_a_trailing_comment_does_not_reach_the_engine():
    """The hazard `code()` exists for. Run through the real function against a
    line the file does not contain yet, because the file having no trailing
    comment today is precisely why nothing else would catch the first one.

    The `;` in the comment is the sharp part: unstripped it splits one
    statement into two, and the second is a fragment the engine rejects.
    """
    got = statements("CREATE INDEX ON :Completion(year);  // annual; see #24")
    assert got == ["CREATE INDEX ON :Completion(year)"], got


def test_a_commented_out_constraint_is_not_counted():
    """`labels()` read the raw file while `statements()` read the stripped one,
    so a constraint commented out to disable it still counted as declared.

    Fed a synthetic schema rather than the real file with a line appended: if
    `labels()` ignores its argument and reads the file anyway — which is
    exactly the regression being guarded — appending to a copy still returns
    the right answer and the test passes. This input cannot be satisfied by
    the file's own contents.
    """
    sample = ("CREATE CONSTRAINT ON (c:Course) ASSERT c.url IS UNIQUE;\n"
              "// CREATE CONSTRAINT ON (c:Course) ASSERT c.name IS UNIQUE;\n")
    assert labels(sample) == ["Course"], \
        "a commented-out constraint is being counted, or the text argument is ignored"


def test_the_file_ends_terminated():
    """An unterminated statement merges with the next one, and the merged text
    still starts with CREATE — so the check above cannot see a missing
    semicolon. This can.

    Through `code()`, like everything else here. It re-read the raw file and
    filtered whole-comment lines itself — so a file ending in a statement with
    a TRAILING comment, which `code()` handles and this did not, would have
    failed here for a reason that is not a defect.
    """
    body = "\n".join(line for line in code().splitlines() if line.strip())
    assert body.rstrip().endswith(";"), "the last statement is not terminated"


def test_a_reflowed_table_still_yields_its_names():
    """`first_column` used to require exactly one space either side of the
    pipe. The tables happen to be written that way, so a stricter pattern goes
    on passing — and the day someone aligns the columns, every containment
    check against an empty set passes vacuously instead of failing.

    Both spellings must give the same answer, or the guards below are guarding
    the formatting rather than the content.
    """
    for row in (
        "| `REQUIRES` | Course -> Course | The prerequisite edge |",   # as written
        "|  `REQUIRES`   | Course -> Course | x |",                    # columns aligned
        "|`REQUIRES`| Course -> Course | x |",                         # padding stripped
        "  | `REQUIRES` | Course -> Course | x |",                     # table indented
    ):
        assert first_column(row) == {"REQUIRES"}, row


def test_a_paired_row_yields_both_names():
    """`| `AT` / `IN` | … |` documents two edges in one row."""
    assert first_column("| `AT` / `IN` | Completion -> Institution | Who |") == {"AT", "IN"}


def test_only_the_first_column_is_read():
    """An edge sharing a name with a label would otherwise pass as documented
    on the strength of appearing in the From/To column."""
    assert first_column("| `REQUIRES` | `Course` -> `Course` | x |") == {"REQUIRES"}


# --------------------------------------------------------------------------
# the schema against the documents that describe it
# --------------------------------------------------------------------------

def test_every_constrained_label_appears_in_the_schema_doc():
    """A label nobody documented is a label nobody can use."""
    documented = SCHEMA_DOC.read_text()
    missing = [label for label in labels() if f"`{label}`" not in documented]
    assert not missing, f"in the cypher but not in docs/schema.md: {missing}"


def test_every_documented_label_exists_in_the_schema():
    """The reverse: the doc must not promise a label the ontology does not
    declare. Both tables in docs/schema.md are label tables."""
    tables = SCHEMA_DOC.read_text().split("## Edge types")[0]
    documented = first_column(tables)
    assert documented, "no label rows found — did the tables change shape?"
    assert documented <= set(labels()), f"documented but not declared: {documented - set(labels())}"


def test_every_documented_edge_exists_in_the_schema():
    table = section(SCHEMA_DOC.read_text(), "## Edge types", "## Why these shapes")
    documented = first_column(table)
    assert documented, "no edge rows found"
    assert documented <= edges(), f"documented but not in the cypher: {documented - edges()}"


def test_the_prerequisite_edge_is_present():
    """REQUIRES is what makes nineteen of the twenty tier-4 questions
    answerable. If it ever disappears, the graph argument goes with it."""
    assert "REQUIRES" in edges()
    assert "(:Course)-[:REQUIRES]->(:Course)" in SCHEMA.read_text()


def test_a_prose_condition_is_a_node_not_an_edge_to_a_course():
    """138 courses state a condition that names no course. Asserting it as a
    REQUIRES edge would invent a link the source does not make."""
    assert "Requirement" in labels()
    assert "(:Course)-[:HAS_REQUIREMENT]->(:Requirement)" in SCHEMA.read_text()


def test_the_schema_refuses_the_edges_the_sources_do_not_publish():
    """Two links this repo has explicitly declined to assert. A future edit
    adding either should have to delete this test and say why."""
    text = SCHEMA.read_text()
    # Any Course -> Programme edge, not one spelling of it. The refusal is
    # that no public source links the two, so PREPARES_FOR or different
    # spacing would sail past a literal check.
    assert not re.search(r"\(:Course\)\s*-\[:\w+\]->\s*\(:Programme\)", text)

    # Every DIRECTED EQUIVALENT_TO pattern must carry `asserted_by`.
    #
    # The previous version stripped the one literal that has properties and
    # then looked for a bare `-[:EQUIVALENT_TO]->`. Nothing could have matched:
    # the only directed occurrence in the file is the one just removed, and the
    # remaining mention is undirected (`-[:EQUIVALENT_TO]-`), which has no
    # `]->` in it at all. The test passed because it could not fail — the exact
    # shape it was written to catch.
    directed = re.findall(r"-\[:EQUIVALENT_TO([^\]]*)\]->", text)
    assert directed, "no directed EQUIVALENT_TO pattern found — did it move?"
    for properties in directed:
        assert "asserted_by" in properties, (
            f"an equivalence must carry who asserted it, got "
            f"`-[:EQUIVALENT_TO{properties}]->`")


def test_the_schema_doc_agrees_with_the_questions_it_claims_to_serve():
    """`docs/schema.md` says "nineteen of the twenty tier-4 questions" — a
    hand-written number about a different document, which is the class of claim
    this repo has had to correct three times."""
    block = section(QUESTIONS.read_text(), "## Tier 4", "## Tier 5")
    questions = re.split(r"\*\*Q\d+", block)[1:]
    answerable = sum(1 for q in questions if "✅" in q)

    # Read the document's own words and compare integers. Predicting how it
    # will spell a number wedges the test: with a digits fallback, a count
    # outside the word map demands the literal digits, so spelling it out —
    # the natural fix, and what both documents do — leaves this failing.
    claim = SCHEMA_DOC.read_text().lower()
    stated = re.search(r"([\w-]+) of the ([\w-]+) tier-4", claim)
    assert stated, "the schema doc no longer states a tier-4 count in that shape"
    assert (spelled(stated.group(1)), spelled(stated.group(2))) == (answerable, len(questions)), (
        f"the schema doc says {stated.group(0)!r}, but questions.md has "
        f"{answerable} answerable of {len(questions)}"
    )


def test_the_competency_gap_count_agrees_with_the_questions():
    """docs/schema.md and the cypher both said six; questions.md says three.
    The schema was drafted before #65 corrected that count, and the stale
    figure shipped in two files — the hand-counted-figure class again, one
    document removed from where it was fixed."""
    block = section(QUESTIONS.read_text(), "## Tier 1", "## The competency gap")
    blocked = [n for n, text in zip(*[iter(re.split(r"\*\*Q(\d+)", block)[1:])] * 2)
               if "competency" in text.lower()]
    # Anchored on the competency-gap sentence itself. A looser pattern matched
    # an unrelated "those questions was blocked" elsewhere on the page.
    for path, pattern in ((SCHEMA_DOC, r"([\w-]+) questions?[^.]*?blocked on one thing"),
                          (SCHEMA, r"competency gap — ([\w-]+) questions")):
        stated = re.search(pattern, path.read_text().lower())
        assert stated, f"{path.name} no longer states a competency-gap count"
        assert spelled(stated.group(1)) == len(blocked), (
            f"{path.name} says {stated.group(1)!r}, but questions.md blocks "
            f"{len(blocked)}: {blocked}")


def test_what_it_does_not_claim_is_written_down():
    """The house standard: limits stated before anyone finds them."""
    for document in (SCHEMA.read_text(), SCHEMA_DOC.read_text()):
        assert "does not claim" in document.lower()


def test_tier_two_labels_are_marked_as_empty():
    """A modelled-but-unpopulated label read as populated would overstate the
    graph. The doc must say which are which."""
    doc = SCHEMA_DOC.read_text()
    assert "modelled and empty" in doc
    modelled = section(doc, "modelled and empty", "## Edge types")
    for label in ("Credential", "Pathway", "Level", "Competency", "EarningsRecord"):
        assert f"`{label}`" in modelled, label


def test_every_edge_in_the_schema_is_documented():
    """The reverse direction, which labels already had and edges did not: an
    edge added to the cypher and never written down would not have failed.

    Only the first column counts. Collecting every backticked word in the table
    picks up the node labels in the From/To column too, so an edge sharing a
    name with a label would pass without being documented."""
    table = section(SCHEMA_DOC.read_text(), "## Edge types", "## Why these shapes")
    documented = first_column(table)
    assert documented, "no edge rows found — a reflowed table would make this pass vacuously"
    missing = sorted(edges() - documented)
    assert not missing, f"in the cypher but not in docs/schema.md: {missing}"


def test_no_label_is_keyed_on_a_bare_path():
    """A catalogue-relative path does not carry the district. `probe_pwcs`
    resolves by path, which is correct inside one catalogue and only inside
    one — `/mathematics/algebra-1` is a path two districts can both publish.
    The host is what separates them, so the key keeps it."""
    keyed = re.findall(r"ASSERT \w+\.(\w+) IS UNIQUE", SCHEMA.read_text())
    assert "path" not in keyed, "a path key cannot distinguish two districts"
    assert "url" in keyed, "the page-keyed labels should key on the absolute URL"


def test_the_url_key_states_how_it_is_normalised():
    """"The absolute URL" is not a spelling. A trailing slash, a mixed-case
    host or a tracking query string each produce a second node for one page,
    and a constraint in 1.1.0 declares the key without enforcing it — so
    nothing catches the duplicate. The rule has to be written where a loader
    author will read it.

    Every part that can differ is named, including the two that are
    deliberately NOT touched: the path keeps its case, because a URL path is
    case-sensitive by spec and lower-casing it merges pages a server may
    distinguish.
    """
    text = SCHEMA.read_text()
    marker = re.search(r"NORMALISATION.*?CREATE CONSTRAINT", text, re.S)
    assert marker, "the URL key states no normalisation rule"
    rule = marker.group().lower()

    # Each part, and what is DONE to it, ON THE SAME LINE. Searching the whole
    # block for the word instead lets a gutted rule pass: "lower" also occurs
    # in the sentence explaining why the PATH is not lower-cased, so a host
    # line reading "host — whatever" still found it.
    lines = [l.strip(" /") for l in rule.splitlines() if l.strip(" /")]
    for part, decision in (("host", "lower"), ("path", "preserved"),
                           ("trailing", "removed"), ("query", "dropped")):
        stated = next((l for l in lines if l.startswith(part)), None)
        assert stated, f"the rule does not have a line for {part}"
        assert decision in stated, (
            f"the {part} line does not say it is {decision}: {stated!r}")
    # The rule and the probe must agree; the probe already resolves by
    # `parsed.path.rstrip("/")`, so a key that kept the slash would resolve one
    # way and merge another.
    assert 'rstrip("/")' in text, \
        "the rule does not tie itself to what etl/probe_pwcs.py actually does"


def test_a_dependent_key_is_at_least_as_specific_as_what_it_depends_on():
    """`Requirement.id` derived from the course *path* while `Course` is keyed
    on the absolute URL — the same collision this file argues against, one node
    removed. A dependent key cannot be less specific than its parent's."""
    text = SCHEMA.read_text()
    assert 'sha1("<course URL>' in text, "Requirement still keys off a path"
    assert 'sha1("<course path>' not in text


def test_the_equivalence_edge_states_its_direction():
    """Directed and not symmetric: one body asserting an equivalence is a
    different fact from the other asserting the converse, and only one may
    exist. Unstated, a query would traverse one way and silently miss half."""
    text = SCHEMA.read_text()
    assert "not symmetric" in text.lower()
    assert "traverse both" in text.lower()


def test_the_unenforced_merge_rule_is_admitted():
    """The file requires loaders to MERGE because 1.1.0 does not reject a
    duplicate CREATE — and etl/loader.py is still the repo template, so nothing
    enforces it. That gap is stated rather than left implied.

    Matched on the CLAIM, not on one sentence. The previous version pinned the
    exact words "Nothing enforces the MERGE rule yet", so moving the paragraph
    out of the numbered scope list — where it did not belong, being a statement
    about loaders rather than about scope — broke a test that has no opinion
    about where the paragraph sits.
    """
    doc = " ".join(SCHEMA_DOC.read_text().split()).lower()
    assert "merge rule is not enforced" in doc or "nothing enforces the merge rule" in doc, \
        "the doc no longer admits that nothing enforces the MERGE rule"
    assert "duplicate create" in doc, \
        "the reason the rule matters — 1.1.0 accepts a duplicate CREATE — is gone"


def test_a_url_in_a_string_literal_survives_comment_stripping():
    """Splitting on `//` unconditionally truncates a statement carrying a URL
    at the scheme. No schema statement does today — the URLs are in comments —
    which is the only reason the naive split never did damage."""
    assert statements("MERGE (n:C {url: 'https://example.org/x'});") \
        == ["MERGE (n:C {url: 'https://example.org/x'})"]
    assert statements('MERGE (n:C {u: "a//b"}); // t') == ['MERGE (n:C {u: "a//b"})']


def test_both_constraint_spellings_are_recognised():
    """The file uses `ON … ASSERT` because the Neo4j-5 `FOR … REQUIRE` form does
    not parse in 1.1.0. A pattern pinned to only that form returns an EMPTY list
    the day the engine catches up and someone modernises the file — and every
    containment check against an empty set passes vacuously. The same hazard
    `first_column` guards against."""
    assert labels("CREATE CONSTRAINT ON (c:Course) ASSERT c.url IS UNIQUE;") == ["Course"]
    assert labels("CREATE CONSTRAINT FOR (c:Course) REQUIRE c.url IS UNIQUE;") == ["Course"]
    assert labels("CREATE CONSTRAINT course_url IF NOT EXISTS "
                  "FOR (c:Course) REQUIRE c.url IS UNIQUE;") == ["Course"]


def test_every_tier_two_key_says_how_it_is_composed():
    """`Requirement`, `Completion` and `Level` state their id formula; three
    tier-2 keys said only `id`. An unpopulated label whose key is undefined is
    a decision deferred without a record that it was deferred."""
    lines = SCHEMA.read_text().splitlines()
    for label in ("AwardingBody", "EarningsRecord", "Place"):
        # A default rather than a bare `next()`: with none, a renamed label
        # raises StopIteration from inside a generator, which pytest reports as
        # an error with no message rather than as "this label is not declared".
        line = next((i for i, l in enumerate(lines)
                     if "ASSERT" in l and f":{label})" in l), None)
        assert line is not None, f"{label} is no longer declared in the schema"
        preceding = "\n".join(lines[max(0, line - 8):line])
        assert "id =" in preceding or "id is" in preceding.lower(), \
            f"{label}'s key composition is not stated"


def test_a_trailing_comment_on_the_last_line_still_reads_as_terminated():
    """The terminator check re-read the raw file and filtered whole-comment
    lines itself, so a file ending in a statement with a TRAILING comment —
    which `code()` handles and that did not — would fail here for a reason that
    is not a defect. Through `code()`, both spellings pass."""
    for ending in ("CREATE INDEX ON :C(year);",
                   "CREATE INDEX ON :C(year);  // rebuilt annually"):
        body = "\n".join(l for l in code(ending).splitlines() if l.strip())
        assert body.rstrip().endswith(";"), ending


def test_a_constraint_wrapped_across_two_lines_is_still_counted():
    """`labels()` matched a pattern spanning `CREATE CONSTRAINT … ON (n:L)`
    against line-preserving text, so a declaration wrapped at the line width
    matched nothing and the label dropped out of the list silently.

    Nothing would have failed. Every check that reads `labels()` is a
    containment test, and a containment test against a SMALLER set passes —
    the vacuous pass this file is otherwise careful about, arriving through
    the formatter rather than through the engine.
    """
    wrapped = ("CREATE CONSTRAINT ON\n"
               "  (c:Course)\n"
               "  ASSERT c.url IS UNIQUE;\n")
    assert labels(wrapped) == ["Course"], \
        "a constraint reflowed across lines is invisible to labels()"


def test_a_renamed_heading_fails_with_a_sentence_not_an_index_error():
    """Every guard here slices a document by its own headings. `split(h)[1]`
    raises IndexError when a heading is reworded — a traceback naming a list
    index, from which nobody can tell that a document was renamed."""
    with pytest.raises(AssertionError, match="no heading"):
        section("nothing here", "## Edge types")
    with pytest.raises(AssertionError, match="no longer follows"):
        section("## Edge types\nrows", "## Edge types", "## Why these shapes")
    assert section("a ## H b ## J c", "## H", "## J").strip() == "b"


def test_no_document_calls_960_a_course_count():
    """The tier-1 correction says the course count is 795; a later section still
    said "one district, 960 courses". A page that corrects itself in one place
    and repeats the error in another is worse than one that never corrected it.

    Both files, not just the doc. The guard used to read `docs/schema.md`
    alone, and the same wrong figure was sitting in the cypher's own "what this
    does NOT claim" section — the stale-figure-one-file-over class this repo
    has now corrected three times.
    """
    for path in (SCHEMA_DOC, SCHEMA):
        flat = " ".join(path.read_text(errors="replace").split())
        assert "960 courses" not in flat, (
            f"{path.name} still calls 960 a course count; it is the sitemap "
            f"page count, and the course count is 795")


def test_every_composite_key_names_its_components():
    """A key documented as `sha1(...)` with no components recorded is a key
    nobody can check after a load — a wrong id is indistinguishable from a
    right one, because there is nothing to recompute it from.

    Every label keyed on an opaque `id` must therefore state the formula in a
    parseable form: `sha1("<a>|<b>")` or `"<a>|<b>"`. That is what makes a
    loader's key auditable, and it is asserted rather than left to whoever
    reads the comments.
    """
    text = SCHEMA.read_text()
    lines = text.splitlines()

    opaque = [label for label in labels()
              if re.search(rf"ASSERT \w+\.id IS UNIQUE", " ".join(
                  l for l in lines if f":{label})" in l))]
    assert opaque, "no id-keyed labels found — did the constraint spelling change?"

    formula = re.compile(r'(?:sha1\(")?<[^>]+>(?:\|<[^>]+>)*')
    undocumented = []
    for label in opaque:
        at = next((i for i, l in enumerate(lines)
                   if "ASSERT" in l and f":{label})" in l), None)
        assert at is not None, label
        preceding = "\n".join(lines[max(0, at - 14):at])
        if not formula.search(preceding):
            undocumented.append(label)
    assert not undocumented, (
        f"these are keyed on an opaque id and do not state what it is composed "
        f"of, so a bad key is undetectable after load: {sorted(undocumented)}")
