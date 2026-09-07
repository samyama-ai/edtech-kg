"""The cypher file itself — its syntax, its structure, and how it is read.

`schema/edtech_kg.cypher` is the executable ontology, not prose. The same test
in `regulatory-affairs-kg` caught both a constraint collision and a syntax form
the engine does not parse — neither of which two rounds of reading had found.

No engine, and no documents. These read only the cypher: that every label is
constrained once, that the syntax is the form 1.1.0 parses, that a commented-out
constraint is not counted, and that every key states what it is composed of.

The file against `docs/schema.md` and `docs/questions.md` is
`tests/test_schema_documents.py`. The tests that need a running instance are
`tests/test_schema_engine.py`, and the readers all three share are in
`tests/schema_source.py`.
"""

import re

import pytest

from etl.cypher_script import split_statements, strip_comment
from tests.schema_source import (WRAP_LIMIT, code, constraint_line,
                                 declarations, edges, first_column, labels,
                                 section, statements, schema_text)


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


def test_the_prerequisite_edge_is_present():
    """REQUIRES is what makes nineteen of the twenty tier-4 questions
    answerable. If it ever disappears, the graph argument goes with it."""
    assert "REQUIRES" in edges()
    assert "(:Course)-[:REQUIRES]->(:Course)" in schema_text()


def test_a_prose_condition_is_a_node_not_an_edge_to_a_course():
    """138 courses state a condition that names no course. Asserting it as a
    REQUIRES edge would invent a link the source does not make."""
    assert "Requirement" in labels()
    assert "(:Course)-[:HAS_REQUIREMENT]->(:Requirement)" in schema_text()


def test_the_schema_refuses_the_edges_the_sources_do_not_publish():
    """Two links this repo has explicitly declined to assert. A future edit
    adding either should have to delete this test and say why."""
    text = schema_text()
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


def test_no_label_is_keyed_on_a_bare_path():
    """A catalogue-relative path does not carry the district. `probe_pwcs`
    resolves by path, which is correct inside one catalogue and only inside
    one — `/mathematics/algebra-1` is a path two districts can both publish.
    The host is what separates them, so the key keeps it."""
    keyed = re.findall(r"ASSERT \w+\.(\w+) IS UNIQUE", schema_text())
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
    text = schema_text()
    marker = re.search(r"NORMALISATION.*?CREATE CONSTRAINT", text, re.S)
    assert marker, "the URL key states no normalisation rule"
    rule = marker.group().lower()

    # Each part, and what is DONE to it, ON THE SAME LINE. Searching the whole
    # block for the word instead lets a gutted rule pass: "lower" also occurs
    # in the sentence explaining why the PATH is not lower-cased, so a host
    # line reading "host — whatever" still found it.
    lines = [line.strip(" /") for line in rule.splitlines()
             if line.strip(" /")]
    for part, decision in (("host", "lower"), ("path", "preserved"),
                           ("trailing", "removed"), ("query", "dropped")):
        stated = next((line for line in lines if line.startswith(part)), None)
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
    text = schema_text()
    assert 'sha1("<course URL>' in text, "Requirement still keys off a path"
    assert 'sha1("<course path>' not in text


def test_the_equivalence_edge_states_its_direction():
    """Directed and not symmetric: one body asserting an equivalence is a
    different fact from the other asserting the converse, and only one may
    exist. Unstated, a query would traverse one way and silently miss half."""
    text = schema_text()
    assert "not symmetric" in text.lower()
    assert "traverse both" in text.lower()


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
    lines = schema_text().splitlines()
    for label in ("AwardingBody", "EarningsRecord", "Place"):
        # `constraint_line`, not a line-local substring, for the reason the
        # composite-key test below gives: a wrapped declaration is invisible
        # to `f":{label})" in line` and the check then passes on nothing.
        line = constraint_line(label)
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
        body = "\n".join(line for line in code(ending).splitlines()
                        if line.strip())
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


def test_every_composite_key_names_its_components():
    """A key documented as `sha1(...)` with no components recorded is a key
    nobody can check after a load — a wrong id is indistinguishable from a
    right one, because there is nothing to recompute it from.

    Every label keyed on an opaque `id` must therefore state the formula in a
    parseable form: `sha1("<a>|<b>")` or `"<a>|<b>"`. That is what makes a
    loader's key auditable, and it is asserted rather than left to whoever
    reads the comments.
    """
    lines = schema_text().splitlines()

    # Through `declarations()`, which collapses whitespace first. Selecting by
    # the line-local substring `f":{label})"` misses a declaration wrapped
    # across two lines — the blind spot this file already has a test for — and
    # the label then never enters `opaque`, so the loop below checks a smaller
    # set and passes vacuously. Joining the matching lines with " " before
    # regexing had a second fault: `ASSERT` on one line and `.id IS UNIQUE` on
    # another matched across the join, admitting a label whose key is not an id.
    opaque = [label for label, key in declarations() if key == "id"]
    assert opaque, "no id-keyed labels found — did the constraint spelling change?"

    formula = re.compile(r'(?:sha1\(")?<[^>]+>(?:\|<[^>]+>)*')
    undocumented = []
    for label in opaque:
        at = constraint_line(label)
        assert at is not None, f"{label} is declared but cannot be located"
        preceding = "\n".join(lines[max(0, at - 14):at])
        if not formula.search(preceding):
            undocumented.append(label)
    assert not undocumented, (
        f"these are keyed on an opaque id and do not state what it is composed "
        f"of, so a bad key is undetectable after load: {sorted(undocumented)}")


def test_a_constraint_form_the_pattern_does_not_know_fails_loudly():
    """`DECLARATION` reads `… ASSERT n.p IS UNIQUE`. A form it does not know —
    `IS NODE KEY`, a composite, anything a later engine adds — used to drop out
    of `declarations()` silently, and every check reading that list then passed
    on a smaller set.

    1.1.0 does not parse `IS NODE KEY` today, measured, so this guards the file
    changing rather than the file as it is.
    """
    with pytest.raises(AssertionError, match="match the declaration pattern"):
        declarations("CREATE CONSTRAINT ON (n:A) ASSERT n.k IS UNIQUE;\n"
                     "CREATE CONSTRAINT ON (n:B) ASSERT (n.a, n.b) IS NODE KEY;\n")
    # The known form still parses cleanly.
    assert declarations("CREATE CONSTRAINT ON (n:A) ASSERT n.k IS UNIQUE;") == [("A", "k")]


def test_a_block_comment_is_refused_rather_than_half_parsed():
    """`/* … */` is legal Cypher and 1.1.0 accepts it — measured. The readers
    here strip only `//`, so one would pass through into a statement and the
    failure would surface as "this is not a constraint or an index", pointing
    at the wrong thing."""
    with pytest.raises(AssertionError, match="block"):
        code("/* a note */\nCREATE INDEX ON :C(year);")
    assert "CREATE INDEX" in code("// a note\nCREATE INDEX ON :C(year);")


def test_a_declaration_wrapped_wider_than_the_window_raises_rather_than_vanishing():
    """`None` from `constraint_line` means "not declared". A declaration
    wrapped wider than the search window would also have returned `None` —
    indistinguishable, so the caller's assertion would have reported the wrong
    fault: "this label is not declared" about a label that plainly is.

    The window is generous (the widest wrap in the real file is one line), so
    this is a guard on the failure MODE rather than on a case the file has.
    """
    wide = ("CREATE CONSTRAINT ON\n" + "\n" * (WRAP_LIMIT + 2) +
            "  (c:Stretched)\n  ASSERT c.url IS UNIQUE;\n")
    with pytest.raises(AssertionError, match="wrapped wider"):
        constraint_line("Stretched", wide)

    # Not declared at all is still a quiet None — that is a real answer.
    assert constraint_line("Absent", "CREATE INDEX ON :C(year);") is None


def test_both_tiers_are_actually_read():
    """Dropping tier 2 from the readers must fail loudly, not silently.

    Measured: removing `edtech_kg_tier2.cypher` from `cypher_script.SCHEMA_FILES`
    left every schema and loader test green — the load still succeeds with six
    fewer keys and two fewer indexes declared, and nothing said so. A comment in that module
    warned about exactly this and guarded nothing.

    Asserted on the applied text rather than on the tuple, because the failure
    that matters is a tier going unapplied, however that happens.
    """
    from etl import cypher_script

    for name, text in (("tests", schema_text()),
                       ("the loader", cypher_script.schema_text())):
        assert "TIER 1 — uniqueness constraints" in text, (
            f"{name} is not reading tier 1")
        assert "TIER 2 — modelled, not yet populated" in text, (
            f"{name} is not reading tier 2 — it declares six keys and two "
            f"indexes, and a load without them succeeds silently")

    applied = len(split_statements("\n".join(
        strip_comment(line) for line in cypher_script.schema_text().splitlines())))
    per_file = [len(split_statements("\n".join(
        strip_comment(line) for line in f.read_text().splitlines())))
        for f in cypher_script.SCHEMA_FILES]
    assert applied == sum(per_file) and len(per_file) == 2, (
        f"the loader applies {applied} statements from {len(per_file)} file(s); "
        f"the schema is two files and every statement in both must be applied")


def test_a_label_sits_under_the_tier_banner_it_belongs_to():
    """`Pathway` carried a comment reading "TIER 1" while the declaration sat
    physically under the `TIER 2 — modelled, not yet populated` banner. Both
    statements were in the file, and the reader believed whichever they reached
    first.

    Only the markdown doc was guarded, so nothing checked the cypher itself —
    which is the file that executes, and the one a loader author reads.
    """
    text = schema_text()
    # Declarations, via `labels()` — not any mention of the label. Both tiers
    # name each other's labels in edge patterns, so a substring test reports
    # `(:Course)-[:DEVELOPS]->(:Competency)` as a Course declaration.
    declared_in_tier_one = set(labels(
        section(text, "TIER 1 — uniqueness constraints", "TIER 2 — modelled")))
    declared_in_tier_two = set(labels(section(text, "TIER 2 — modelled")))
    assert declared_in_tier_one and declared_in_tier_two, "the banners moved"

    for label in ("Course", "Subject", "Pathway", "Requirement"):
        assert label in declared_in_tier_one, (
            f"{label} is loaded but is not declared under TIER 1")
        assert label not in declared_in_tier_two, (
            f"{label} is loaded, but its constraint sits under the tier-2 "
            f'"modelled, not yet populated" banner')

    for label in ("Credential", "Level", "Competency", "EarningsRecord"):
        assert label in declared_in_tier_two, (
            f"{label} is unpopulated but is not declared under TIER 2")


def test_a_heading_mentioned_in_prose_does_not_truncate_the_section():
    """`section()` sliced on the FIRST occurrence of a heading, so a sentence
    quoting that heading above the banner itself cut the section short — every
    caller then checked a fragment, and a containment test against a fragment
    passes.

    Ambiguity is refused rather than guessed at: two occurrences is a document
    the reader cannot resolve, and saying so beats picking one.
    """
    quoted = ("Everything under ## TIER 2 is unpopulated.\n"
              "## TIER 2\nthe real section\n")
    with pytest.raises(AssertionError, match="ambiguous"):
        section(quoted, "## TIER 2")

    assert section("intro\n## TIER 2\nbody\n", "## TIER 2").strip() == "body"
