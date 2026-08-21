"""Writing the catalogue — the edges, and the schema they must agree with.

Every write is a MERGE, because a constraint in 1.1.0 declares the key and does
not reject a duplicate CREATE. The two edge-building steps are pure functions
so the grouping and the collapse arithmetic can be checked without an engine.

The engine client is `tests/test_engine.py`; the parsing is
`tests/test_pwcs_source.py`.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from etl import load_pwcs as loader
from etl import pwcs_edges as edges_mod
from etl.engine import Unquotable

SCHEMA = Path(__file__).resolve().parents[1] / "schema" / "edtech_kg.cypher"


class Recorder:
    """Every statement the loader would send, in order.

    One definition. It was re-declared inside four tests, three of them
    identical and one that raised on any call — so "what does the loader send"
    was answered by four slightly different objects.
    """

    def __init__(self, refuse: bool = False) -> None:
        self.sent: list[str] = []
        self.refuse = refuse

    @property
    def statements(self) -> int:
        """Derived, not counted twice. A separate counter and `len(self.sent)`
        are two records of one fact, and the pair can disagree."""
        return len(self.sent)

    def run(self, query: str):
        if self.refuse:
            raise AssertionError(f"should not have run: {query}")
        self.sent.append(query)
        return {"columns": [], "records": []}

# --------------------------------------------------------------------------
# the loader and the schema must agree on the key
# --------------------------------------------------------------------------

# Both constraint spellings. The file uses `ON … ASSERT` because the Neo4j-5
# `FOR … REQUIRE` form does not parse in 1.1.0 — but a pattern pinned to only
# that form returns an EMPTY map the day the engine catches up and someone
# modernises the file, and every check below then passes on nothing.
DECLARATION = re.compile(
    r"CREATE CONSTRAINT (?:\w+ )?(?:IF NOT EXISTS )?"
    r"(?:ON|FOR) \(\w+:(\w+)\) (?:ASSERT|REQUIRE) \w+\.(\w+) IS UNIQUE")


def pairs_to_map(pairs, what: str) -> dict[str, str]:
    """`dict(pairs)` keeps the LAST value for a repeated key and says nothing.

    A label declared twice with different keys, or upserted twice on different
    properties, is exactly the collision these checks exist to catch — and
    building a dict silently resolves it in favour of whichever came last.
    """
    seen: dict[str, str] = {}
    clashes = []
    for label, key in pairs:
        if label in seen and seen[label] != key:
            clashes.append(f"{label}: {seen[label]!r} and {key!r}")
        seen[label] = key
    assert not clashes, f"{what} names one label with two different keys: {clashes}"
    return seen


def declared_keys() -> dict[str, str]:
    code = "\n".join(line.split("//")[0] for line in SCHEMA.read_text().splitlines())
    declared = pairs_to_map(DECLARATION.findall(" ".join(code.split())), "the schema")
    assert declared, (
        "no constraints parsed out of the schema — a renamed file or a changed "
        "constraint spelling would otherwise make every check below vacuous")
    return declared


def loader_keys() -> dict[str, str]:
    """Which label the loader upserts on which property.

    `re.DOTALL` on the argument list: the previous pattern matched only a
    single-line call, so wrapping one across lines dropped that label from the
    schema-agreement check silently — a guard quietly covering less than it
    claimed.

    The engine argument is `[^,]+`, not the literal name `engine`. Renaming
    that parameter — or passing anything else — made the call invisible here
    while it went on writing nodes.

    Every call site must match, and that is asserted below rather than assumed:
    a pattern that matches four of five calls reports agreement about the four
    and says nothing about the fifth, which is the shape of a guard covering
    less than it claims.
    """
    source = inspect.getsource(loader)
    # `[^,]+` for the engine argument breaks on any call whose first argument
    # itself contains a comma. Non-greedy up to the first quoted argument
    # instead, which is what the pattern is actually looking for.
    matched = re.findall(r'upsert\(.*?"(\w+)",\s*"(\w+)"', source, re.S)
    # Comments and docstrings stripped, and `def upsert(` excluded: this
    # counted the DEFINITION and any prose mention as call sites, so the
    # equality below could fail on a mention or mask real drift.
    code = "\n".join(line.split("#")[0] for line in source.splitlines())
    call_sites = len(re.findall(r"(?<!def )\bupsert\(", code))
    assert len(matched) == call_sites, (
        f"{call_sites} upsert call sites in the loader, {len(matched)} matched "
        f"by this pattern — the unmatched ones are unchecked")
    return pairs_to_map(matched, "the loader")


def test_every_label_the_loader_writes_is_keyed_as_the_schema_declares():
    """`Pathway` was declared `ASSERT pw.ctid IS UNIQUE` while the loader
    upserted on `url` and never set `ctid`. All 38 nodes carried a null value
    for the declared key, and 1.1.0 accepted it in silence — a constraint here
    declares the key and does not enforce it, which is the whole reason the
    schema tells loaders to MERGE.

    Reading both sides rather than restating either, so this cannot drift.
    """
    declared, used = declared_keys(), loader_keys()
    assert used, "no upsert calls found — did the loader change shape?"
    for label, key in used.items():
        assert label in declared, f"{label} is written but declared nowhere"
        assert declared[label] == key, (
            f"the loader keys {label} on {key!r}; the schema declares "
            f"{declared[label]!r}. Every node would carry a null declared key.")


def test_the_loader_sets_the_key_it_merges_on():
    """The other half: a key the loader MERGEs on but never writes would leave
    the property unset even when the two names agree.

    Asserted by CALLING it, not by matching a fragment of its source. The
    previous version pinned an exact f-string and broke on any reformat, while
    proving nothing about what upsert emits.
    """
    engine = Recorder()
    loader.upsert(engine, "Course", "url", "https://x/y", {"name": "A"})
    assert engine.sent[0] == "MERGE (n:Course {url: 'https://x/y'})", engine.sent[0]
    assert engine.sent[1] == (
        "MATCH (n:Course {url: 'https://x/y'}) SET n.name = 'A'"), engine.sent[1]


def test_upsert_refuses_a_label_or_property_that_is_not_an_identifier():
    """`lit()` guards values. Labels and property names are interpolated bare —
    Cypher has no other way to write them — so nothing guarded them at all.
    Every name here is a source literal today; the next loader may build one
    from a column heading."""
    for label, key, props in (("Cour se", "url", {}),
                              ("Course", "n.url", {}),
                              ("Course", "url", {"na me": "x"})):
        with pytest.raises(Unquotable):
            loader.upsert(Recorder(refuse=True), label, key, "v", props)


# --------------------------------------------------------------------------
# building the edges — the arithmetic, without an engine
# --------------------------------------------------------------------------

# Every published page, and the courses among them. A prerequisite resolves
# against the SECOND — the whole point of the split.
BY_PATH = {"/a/one": "https://catalog.pwcs.edu/a/one",
           "/a/two": "https://catalog.pwcs.edu/a/two",
           "/a": "https://catalog.pwcs.edu/a"}
COURSE_BY_PATH = {"/a/one": "https://catalog.pwcs.edu/a/one",
                  "/a/two": "https://catalog.pwcs.edu/a/two"}


def prerequisites(*records):
    return edges_mod.prerequisite_pairs(list(records), BY_PATH, COURSE_BY_PATH)


def course(url: str, *hrefs: str) -> dict:
    return {"url": url,
            "prerequisite_links": [{"href": h, "name": "n"} for h in hrefs]}


def test_two_links_to_the_same_course_make_one_edge():
    """An edge MERGE matches on start, type and end alone (#77), so two links
    naming the same course give two MERGEs, ONE edge, and a counter of two —
    and `verify()` then exits non-zero on a well-formed catalogue."""
    got = prerequisites(course("https://catalog.pwcs.edu/a/three", "/a/one", "/a/one"))
    assert got["pairs"] == [("https://catalog.pwcs.edu/a/three",
                             "https://catalog.pwcs.edu/a/one")]
    assert got["duplicated"] == 1


def test_a_prerequisite_pointing_at_an_unparsed_page_is_counted():
    got = prerequisites(course("https://catalog.pwcs.edu/a/three", "/node/1435"))
    assert got["pairs"] == [] and got["unresolved"] == 1


def test_a_prerequisite_resolves_to_the_node_key_not_the_href():
    """The key a Course node was created with, via `by_path` — not whatever
    spelling the href happened to use."""
    got = prerequisites(course("https://catalog.pwcs.edu/a/three", "/a/one/"))
    assert got["pairs"][0][1] == "https://catalog.pwcs.edu/a/one"


def test_a_prerequisite_naming_a_subject_page_writes_no_edge_and_counts_none():
    """The one real defect in this branch. `by_path` holds subject and pathway
    pages too, so a prerequisite pointing at one resolved as if it were a
    course — and the statement written is `MATCH (a:Course …), (b:Course …)`
    where `b` is a `:Subject`. The MATCH finds nothing, no edge is written,
    and the counter still increments; `verify()` then reports a mismatch with
    nothing to say why.

    This is the guard `pwcs_source.read` already applies to pathway rows,
    missing on the edge the graph exists for. No link does this today — that
    is a property of this catalogue, measured, not a property of the code.
    """
    got = prerequisites(course("https://catalog.pwcs.edu/a/three", "/a"))
    assert got["pairs"] == [], "a subject page was resolved as a course"
    assert got["off_level"] == ["https://catalog.pwcs.edu/a"], got
    # And not conflated with a page that did not parse — different facts.
    assert got["unresolved"] == 0, got


def pathway(url: str, *rows) -> dict:
    return {"url": url, "courses": [{"url": u, "section": s, "credits": c}
                                    for u, s, c in rows]}


def test_a_pathway_course_resolves_through_by_path():
    """This matched on `absolute(href)` while Course nodes are created from the
    sitemap URL verbatim, and the two normalise differently — `course_urls()`
    leaves `<loc>` untouched, `absolute()` strips a trailing slash. A mismatch
    writes no edge and still increments the counter."""
    edges = edges_mod.pathway_edges([pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one/", "First", "1"))], BY_PATH, COURSE_BY_PATH)
    assert list(edges["grouped"]) == [("https://catalog.pwcs.edu/p",
                                       "https://catalog.pwcs.edu/a/one")]


def test_a_course_in_two_sections_is_one_edge_with_both_names():
    edges = edges_mod.pathway_edges([pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", "Second", "1"))], BY_PATH, COURSE_BY_PATH)
    assert len(edges["grouped"]) == 1
    assert edges["collapsed"] == 1
    assert next(iter(edges["grouped"].values()))["sections"] == ["First", "Second"]


def test_differing_credits_across_sections_are_counted_not_lost():
    """The section names were preserved when rows were folded and the credits
    were not — the same silent loss #77 is about."""
    edges = edges_mod.pathway_edges([pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", "Second", "2"))], BY_PATH, COURSE_BY_PATH)
    assert edges["conflicting"] == 1


def test_a_pathway_row_naming_an_unparsed_page_is_counted():
    edges = edges_mod.pathway_edges([pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/node/1435", "First", "1"))], BY_PATH, COURSE_BY_PATH)
    assert edges["grouped"] == {} and edges["unlinkable"] == 1


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
    loader.apply_schema(engine, quiet=True, schema=schema)
    assert engine.sent == [
        "CREATE CONSTRAINT ON (c:C) ASSERT c.url IS UNIQUE",
        "MERGE (n:C {url: 'https://example.org/x'})"], engine.sent


def test_a_semicolon_inside_a_literal_does_not_split_the_statement():
    """`strip_comment` was made quote-aware and the `;` split was not, so the
    pair disagreed: the stripper preserved `MERGE (n {t: 'a;b'})` and the split
    then cut it in half, sending the engine two fragments it rejects.

    No schema statement carries a semicolon in a literal today, which is
    exactly why nothing would have caught the first one that did."""
    assert loader.split_statements("MERGE (n:C {t: 'a;b'});\nCREATE INDEX ON :C(y);") \
        == ["MERGE (n:C {t: 'a;b'})", "CREATE INDEX ON :C(y)"]
    assert loader.split_statements('MERGE (n:C {t: "x;y"})') == ['MERGE (n:C {t: "x;y"})']
    assert loader.split_statements("  \n ;; \n") == []


def test_a_requirement_is_labelled_from_the_list_it_came_from():
    """The label was re-derived by counting URL segments, which is how
    `pwcs_source` classifies a page in the first place. Re-deriving it means
    one page can be a Pathway to the reader and a Course to the loader — and
    the MATCH then looks for a label the node does not carry, writes no edge,
    and still counts one.

    The pathway here sits at COURSE depth on purpose: under the old rule it
    was labelled `Course`, and no HAS_REQUIREMENT edge could ever match.
    """
    engine = Recorder()
    data = {"published": set(), "subjects": [], "courses": [],
            "pathways": [{"url": "https://catalog.pwcs.edu/specialty/it",
                          "title": "IT", "requirements_text": "Application required",
                          "courses": [], "dangling": []}]}
    loader.load(engine, data, quiet=True)
    matched = [q for q in engine.sent if "HAS_REQUIREMENT" in q]
    assert matched, engine.sent
    assert "MATCH (n:Pathway" in matched[0], matched[0]


def test_a_comment_is_stripped_but_a_url_in_a_literal_is_not():
    """Splitting on `//` unconditionally truncates a statement carrying a URL
    at the scheme. No schema statement does today — the URLs are in comments —
    which is the only reason the naive split never did damage."""
    assert loader.strip_comment("CREATE INDEX ON :C(year);  // annual") \
        == "CREATE INDEX ON :C(year);  "
    assert loader.strip_comment("MERGE (n {url: 'https://x/y'})") \
        == "MERGE (n {url: 'https://x/y'})"
    assert loader.strip_comment('MERGE (n {u: "a//b"}) // t') == 'MERGE (n {u: "a//b"}) '
    assert loader.strip_comment("// whole line") == ""


def test_the_first_credit_value_is_kept_and_the_disagreement_is_counted():
    """A course in two sections of one pathway may carry different credits.
    The engine holds one edge, so one value survives — the FIRST, and the
    disagreement is reported rather than lost. Untested until now: the count
    was asserted and the surviving value was not, so keeping the last would
    have passed."""
    edges = edges_mod.pathway_edges([pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", "Second", "2"))], BY_PATH, COURSE_BY_PATH)
    entry = next(iter(edges["grouped"].values()))
    assert entry["credits"] == "1", "the first published credit value must survive"
    assert edges["conflicting"] == 1


def test_the_includes_write_joins_the_sections_and_counts_them():
    """Two statements per edge, because a bare SET after MERGE does not parse
    in 1.1.0 (#75). Nothing asserted what the SECOND statement carries, so the
    section join and the `sections` count — the whole reason rows are grouped
    rather than written one per row — were unchecked."""
    engine = Recorder()
    data = {"published": set(), "subjects": [],
            "courses": [{"url": "https://catalog.pwcs.edu/a/one", "title": "One",
                         "prerequisite_links": []}],
            "pathways": [
        {"url": "https://catalog.pwcs.edu/p", "title": "P", "dangling": [],
         "courses": [{"url": "https://catalog.pwcs.edu/a/one", "section": "First",
                      "credits": "1"},
                     {"url": "https://catalog.pwcs.edu/a/one", "section": "Second",
                      "credits": "1"}]}]}
    loader.load(engine, data, quiet=True)
    includes = [q for q in engine.sent if "INCLUDES" in q]
    assert len(includes) == 2, includes
    assert includes[0].startswith("MATCH (p:Pathway"), includes[0]
    assert "e.section = 'First | Second'" in includes[1], includes[1]
    assert "e.sections = 2" in includes[1], includes[1]


def test_verify_compares_the_engine_against_the_loader_and_names_the_gap():
    """`verify()` is what makes every figure in the README a measurement rather
    than a tally the loader kept about itself — and it had no test at all."""
    class Counts:
        """Answers a count query by the ONE fragment it contains.

        Matching by substring in insertion order meant a query mentioning two
        labels would silently take whichever was declared first. Ambiguity is
        refused instead, so a future query that names two is a failure here
        rather than a wrong number in `verify()`.
        """

        def __init__(self, answers):
            self.answers = answers

        def scalar(self, query):
            hits = [v for fragment, v in self.answers.items() if fragment in query]
            assert len(hits) == 1, (
                f"{len(hits)} fragments match this query, so the answer would "
                f"be arbitrary: {query}")
            return hits[0]

    loaded = {"subjects": 1, "courses": 2, "pathways": 3, "in_subject": 4,
              "requires": 5, "includes": 6, "requirements": 7}
    agreeing = {":Subject": 1, ":Course": 2, ":Pathway": 3, ":Requirement": 7,
                "IN_SUBJECT": 4, "REQUIRES": 5, "INCLUDES": 6,
                "HAS_REQUIREMENT": 7}
    assert loader.verify(Counts(agreeing), loaded) == []

    short = dict(agreeing, REQUIRES=4)
    problems = loader.verify(Counts(short), loaded)
    assert len(problems) == 1, problems
    assert "REQUIRES" in problems[0] and "wrote 5" in problems[0], problems[0]


def test_a_label_named_twice_with_two_keys_is_a_clash_not_a_last_wins():
    """`dict(pairs)` keeps the LAST value for a repeated key and says nothing.
    A label declared twice with different keys — or upserted on two different
    properties — is exactly the collision `test_every_label_the_loader_writes
    _is_keyed_as_the_schema_declares` exists to catch, and building a dict
    resolved it silently in favour of whichever came last."""
    assert pairs_to_map([("Course", "url"), ("Subject", "url")], "x") == {
        "Course": "url", "Subject": "url"}
    # The same pair twice is not a clash — it is one fact stated twice.
    assert pairs_to_map([("Course", "url"), ("Course", "url")], "x") == {"Course": "url"}
    with pytest.raises(AssertionError, match="two different keys"):
        pairs_to_map([("Course", "url"), ("Course", "ctid")], "the schema")


def test_a_pathway_row_naming_a_subject_page_writes_no_edge_and_counts_none():
    """The same off-level defect `prerequisite_pairs` was fixed for, on the
    other edge. `by_path` holds subject and pathway pages, so a row naming one
    resolved — and the statement written is `MATCH (c:Course …)`, which finds
    nothing. No edge, and the counter still incremented."""
    edges = edges_mod.pathway_edges(
        [pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a", "First", "1"))],
        BY_PATH, COURSE_BY_PATH)
    assert edges["grouped"] == {}, "a subject page was resolved as a course"
    assert edges["off_level"] == ["https://catalog.pwcs.edu/a"], edges
    assert edges["unlinkable"] == 0, edges


def test_verify_reads_back_the_requirement_nodes_too():
    """`Requirement` was written and never read back. It is the one label whose
    key is DERIVED rather than taken from the source, so a collision in
    `requirement_id` would silently merge two conditions into one node — the
    case most in need of a read-back, and the one that had none."""
    class Counts:
        def __init__(self, answers):
            self.answers = answers

        def scalar(self, query):
            hits = [v for fragment, v in self.answers.items() if fragment in query]
            assert len(hits) == 1, f"ambiguous: {query}"
            return hits[0]

    loaded = {"subjects": 1, "courses": 2, "pathways": 3, "in_subject": 4,
              "requires": 5, "includes": 6, "requirements": 7}
    short = {":Subject": 1, ":Course": 2, ":Pathway": 3, ":Requirement": 6,
             "IN_SUBJECT": 4, "REQUIRES": 5, "INCLUDES": 6,
             "HAS_REQUIREMENT": 7}
    problems = loader.verify(Counts(short), loaded)
    assert len(problems) == 1, problems
    assert "Requirement" in problems[0] and "wrote 7" in problems[0], problems[0]


def test_a_course_under_a_non_subject_parent_writes_no_edge_and_counts_none():
    """The third place in this loader with the off-level shape, after REQUIRES
    and INCLUDES. The parent path was looked up in `by_path` — every published
    page — and then matched as `:Subject`. A course whose parent is a pathway
    page resolved, the MATCH found nothing, no edge was written, and the
    counter still incremented.

    The index each edge resolves against now matches the label it writes.
    """
    engine = Recorder()
    data = {"published": set(),
            "subjects": [],
            "courses": [{"url": "https://catalog.pwcs.edu/cte/algebra-1",
                         "title": "Algebra 1", "prerequisite_links": []}],
            # The parent page exists and is a PATHWAY, not a subject.
            "pathways": [{"url": "https://catalog.pwcs.edu/cte", "title": "CTE",
                          "courses": [], "dangling": []}]}
    loaded = loader.load(engine, data, quiet=True)
    assert loaded["in_subject"] == 0, "a pathway page was resolved as a subject"
    assert not [q for q in engine.sent if "IN_SUBJECT" in q], engine.sent
