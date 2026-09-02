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
            # The property-presence check asks a different question; these
            # fixtures are about counts.
            if "IS NULL" in query:
                return 0
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


def test_verify_reads_back_the_requirement_nodes_too():
    """`Requirement` was written and never read back. It is the one label whose
    key is DERIVED rather than taken from the source, so a collision in
    `requirement_id` would silently merge two conditions into one node — the
    case most in need of a read-back, and the one that had none."""
    class Counts:
        def __init__(self, answers):
            self.answers = answers

        def scalar(self, query):
            if "IS NULL" in query:
                return 0
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


def test_a_surplus_reads_as_stale_data_and_a_shortfall_as_a_lost_write():
    """`verify()` holds the graph to the CATALOGUE, not to this run's writes.
    MERGE never removes, so a source row deleted since the last load leaves the
    engine holding more than the loader wrote — a real failure under that
    contract, but one whose fix is `--reset` rather than debugging the loader.
    The two directions have to read differently."""
    class Counts:
        def __init__(self, answers):
            self.answers = answers

        def scalar(self, query):
            if "IS NULL" in query:
                return 0
            hits = [v for fragment, v in self.answers.items() if fragment in query]
            assert len(hits) == 1, f"ambiguous: {query}"
            return hits[0]

    loaded = {"subjects": 1, "courses": 2, "pathways": 3, "in_subject": 4,
              "requires": 5, "includes": 6, "requirements": 7}
    base = {":Subject": 1, ":Course": 2, ":Pathway": 3, ":Requirement": 7,
            "IN_SUBJECT": 4, "REQUIRES": 5, "INCLUDES": 6, "HAS_REQUIREMENT": 7}

    surplus = loader.verify(Counts(dict(base, REQUIRES=9)), loaded)
    assert len(surplus) == 1 and "--reset" in surplus[0], surplus
    assert "MERGE never removes" in surplus[0], surplus[0]

    shortfall = loader.verify(Counts(dict(base, REQUIRES=2)), loaded)
    assert len(shortfall) == 1 and "did not land" in shortfall[0], shortfall
    assert "--reset" not in shortfall[0], shortfall[0]


def test_a_node_left_without_its_properties_is_reported():
    """`upsert` MERGEs the key and SETs the rest in a second statement. That
    second request can fail on its own — retries exhausted, a 4xx — leaving a
    node that exists, carries its key and has none of its properties. A COUNT
    passes it, because counting is exactly what it satisfies."""
    class Counts:
        def scalar(self, query):
            if "n.name IS NULL" in query and "(n:Course)" in query:
                return 3
            if "IS NULL" in query:
                return 0
            return 1 if "(n:" in query else 1

    loaded = {"subjects": 1, "courses": 1, "pathways": 1, "in_subject": 1,
              "requires": 1, "includes": 1, "requirements": 1}
    problems = loader.verify(Counts(), loaded)
    assert any("carry the key and no `name`" in p for p in problems), problems
    assert any("3 node(s)" in p for p in problems), problems


def loaded_course(**record) -> str:
    """The Cypher `load()` writes for one course, through the real upsert.

    Defaults for the keys the rest of `load()` reads, so a test about two
    properties does not have to restate the whole record shape.
    """
    record = {"url": "https://catalog.pwcs.edu/x/course", "title": "Course",
              "prerequisite_links": [], "requirements_text": None,
              "description": None, "grade_levels": [], **record}
    engine = Recorder()
    loader.load(engine, {"published": set(), "subjects": [], "pathways": [],
                         "courses": [record]}, quiet=True)
    return "\n".join(engine.sent)


def test_a_course_is_written_with_its_description_and_grade_levels():
    """DRIVEN THROUGH `load()`, not read off the source.

    `tests/schema_properties.declared` reads the loader's AST to decide what a
    label carries, which is what tells a query it may reach for a property
    without a `NEEDS:` line. That is a statement about the source, so a loader
    that stops WRITING while the assignment stays in the file — behind a
    disabled branch, say — leaves the annotation off and the query answering
    null again. Measured: that mutation passed everything else.
    """
    written = loaded_course(url="https://catalog.pwcs.edu/x/course-1",
                            title="Course 1", description="A description.",
                            grade_levels=["10", "11"])
    assert "n.description = 'A description.'" in written, written
    # JOINED as the catalogue prints them. The engine's property values are
    # scalars, so a list cannot be written and the join is the representation.
    assert "n.grade_levels = '10, 11'" in written, written


def test_a_course_without_them_is_written_without_the_properties():
    """Absence is real — 8 of 791 courses publish no description and 10 no
    grades. Writing `""` would make `c.description IS NOT NULL` true for every
    course and turn a measured absence into a measured presence."""
    written = loaded_course(url="https://catalog.pwcs.edu/x/course-2",
                            title="Course 2")
    assert "n.description" not in written
    assert "n.grade_levels" not in written
    assert "n.name = 'Course 2'" in written, written

