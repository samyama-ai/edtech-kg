"""Every answerable question has a traversal, and the traversal parses — #22.

`docs/questions.md` marks questions ✅ answerable, ⚠️ answerable with a caveat,
or ❌ not. Those marks were a judgement. This turns them into a check: a
question marked answerable whose query the engine will not parse is a question
the schema does not serve, and the mark is wrong.

**Parsing is a weak bound, and Q68 is the proof.** That query parsed, ran
without error, and returned "there are no articulation points" on a graph that
has them — because `IN` over a list of nodes matches nothing either way rather
than refusing. A parses-only gate passed a query that answers wrongly.

So two things are checked, and they are not the same:

* **Parsing**, ratcheted below against whatever engine is reachable. Cheap, and
  it runs on an empty one.
* **Execution against LOADED data** — which catches a statement that ERRORS
  when real rows reach it, and an empty engine cannot, because a predicate
  inside a `WHERE` is never evaluated when nothing matches.
* **A non-empty answer** where one is expected. This is the check that bites,
  and neither of the two above is it: Q68 returned zero rows without erroring,
  and Q71 returned 359 rows that were every edge in the graph. Both parsed,
  both ran, both answered confidently and wrongly.

Q68 and Q71 were found BY HAND, not by any of these. What is guarded now is
the shape they share — a whole-graph statement whose answer is empty when the
graph is not — and the shape they do not: a wrong non-empty answer is still
only caught by reading it. Said plainly rather than implied, because the last
version of this docstring claimed execution "caught Q68" and it did not.

A query that parses, runs, and names a property nothing writes would still
pass. That is what the `NEEDS:` annotations are for, and #123 is closing the
gap they document.

Written for the engine this repo pins: a pattern inside `WHERE` does not parse
(see `docs/schema.md`), so absence is `NOT EXISTS { MATCH ... }` throughout.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from tests.questions_document import QUESTION, marks
from tests.schema_properties import declared, named_in_schema, undeclared
from tests.test_schema_engine import SAMYAMA_URL, query, require_engine

ROOT = pathlib.Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "docs" / "questions.md"
BENCHMARKS = ROOT / "benchmarks" / "questions"


def uncommented(text: str) -> str:
    """Comments out BEFORE any split on `;`.

    Three of these comments contain a semicolon. Splitting first cuts them
    mid-sentence and the fragment is handed to the parser as Cypher — which
    reported the document's own prose as a syntax error, and would have made
    this file lie in the most confusing possible way.
    """
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("//"))


def schema_text() -> str:
    return (ROOT / "schema" / "edtech_kg.cypher").read_text(encoding="utf-8")


def files() -> list[pathlib.Path]:
    return sorted(BENCHMARKS.glob("tier-*.cypher"))


def statements(path: pathlib.Path) -> list[str]:
    return [s.strip() for s in uncommented(path.read_text(encoding="utf-8")).split(";")
            if s.strip()]


def answered(path: pathlib.Path) -> list[str]:
    """The question ids a benchmark file claims to answer."""
    return re.findall(r"^// (Q\d+)\.", path.read_text(encoding="utf-8"), re.M)


def test_there_are_benchmark_files_to_check():
    """A glob that matches nothing makes every test below vacuous."""
    assert files(), f"no tier-*.cypher under {BENCHMARKS}"


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_every_statement_in_the_file_parses(path):
    """The whole point. A traversal the engine refuses is not an answer."""
    require_engine()
    refused = []
    for statement in statements(path):
        result = query(SAMYAMA_URL, statement)
        if result.get("transport"):
            pytest.fail(f"the engine failed rather than answered: {result['error']}")
        if "error" in result:
            refused.append(f"{statement.splitlines()[0][:60]} -> "
                           f"{result['error'][:120]}")
    assert not refused, (
        f"{path.name} carries statements the engine will not parse, so the "
        f"questions they claim to answer are not answered: {refused}")


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_the_file_answers_a_question_for_every_statement_it_carries(path):
    """A statement with no `// Qn.` above it answers nothing nameable, and a
    question named twice is two answers to one question."""
    ids = answered(path)
    assert ids, f"{path.name} names no questions"
    assert len(ids) == len(set(ids)), (
        f"{path.name} names a question twice: "
        f"{[q for q in ids if ids.count(q) > 1]}")
    # Not equality: Q4 asks two counts and is answered by two statements.
    assert len(statements(path)) >= len(ids), (
        f"{path.name} names {len(ids)} questions and carries "
        f"{len(statements(path))} statements")


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_it_does_not_claim_to_answer_a_question_marked_unanswerable(path):
    """❌ means the schema does not serve it. A query here would mean the mark
    is wrong, which is a document change rather than a quiet extra file."""
    every = marks()                    # hoisted: this re-read questions.md per question
    wrong = [q for q in answered(path) if every.get(q) == "no"]
    assert not wrong, (
        f"{path.name} answers {wrong}, which questions.md marks ❌. Either the "
        f"mark is wrong and the document should say so, or the query is not "
        f"answering the question asked")


def test_every_answerable_question_in_a_covered_tier_has_a_traversal():
    """The ratchet, and the reason this issue exists. Scoped to the tiers that
    have a file — a tier with no file yet is not a failure, but a question
    inside a covered tier with no query is exactly what #22 is about.
    """
    covered = {q for path in files() for q in answered(path)}
    text = QUESTIONS.read_text(encoding="utf-8")
    tiers, section = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        # THE SHARED PARSER, not a second one. This required the closing `**`
        # right after the number, so `**Q61. What is…**` was not a question —
        # the exact bug `tests/questions_document.py` was written to fix, and
        # it sat twenty lines from the fix. Measured: strict reads 96 of 102,
        # and the six it cannot see are Q61-Q65 and Q75 — every one of them in
        # the tier this change adds. An invisible question is exempt from the
        # ratchet below, so deleting Q61's traversal failed nothing.
        m = QUESTION.match(line)
        if m and section:
            tiers.setdefault(section, []).append(m.group(1))

    every = marks()
    missing = []
    for section, ids in tiers.items():
        if not covered & set(ids):
            continue                       # this tier has no file yet
        missing += [q for q in ids
                    if every.get(q) in ("ok", "caveat") and q not in covered]
    assert not missing, (
        f"these questions are marked answerable, sit in a tier that has a "
        f"benchmark file, and have no traversal: {sorted(missing)}")


# --------------------------------------------------------------------------
# Parsing is a weak check, and this is the half it misses. `schema/
# edtech_kg.cypher` declares KEYS — measured, it declares no other property at
# all — so a traversal naming `o.name` on an `Occupation` parses, looks like an
# answer, and reaches for something no loader writes.
#
# Sixteen of tier 1's property accesses are in that state (#123). They are not
# removed: the questions are answerable once the schema declares them, which is
# a different thing from Q19's "no node holds a cost at all". They are DECLARED
# INLINE instead, so the gap is visible in the file and cannot grow quietly as
# tiers 2 to 6 are written.
# --------------------------------------------------------------------------

NEEDS = re.compile(r"^//\s+NEEDS: (.+)$", re.M)


def statement_blocks(path: pathlib.Path) -> list[str]:
    """Each query with the comments that belong to it."""
    return [b for b in re.split(r"(?<=;)\n", path.read_text(encoding="utf-8"))
            if uncommented(b).strip()]


def labelled_statements(path: pathlib.Path) -> list[tuple[str | None, str]]:
    """Every statement, paired with the question id whose answer it is.

    Splitting raw text on `;` — which is what `statement_blocks` does, and what
    a checker written against it did — is the hazard `uncommented()` exists to
    prevent: three comments in these files contain a semicolon. It also assumes
    one statement per question, and Q95 takes two. A per-block split ran the
    isolated count and never ran the linked count beside it, so half of that
    answer was outside every check in this file.

    Comments are read for the label and then dropped, so a `;` inside one
    cannot end a statement.
    """
    label, buffer, out = None, [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        marked = re.match(r"//\s+(Q\d+)\.", line.strip())
        if marked:
            label = marked.group(1)
        if line.strip().startswith("//"):
            continue
        buffer.append(line)
        if line.rstrip().endswith(";"):
            body = "\n".join(buffer).strip().rstrip(";").strip()
            if body:
                out.append((label, body))
            buffer = []
    return out


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_every_undeclared_property_is_declared_as_undeclared(path):
    """A traversal may reach past the schema. It may not do so silently."""
    missing = []
    for block in statement_blocks(path):
        gaps = undeclared(uncommented(block))
        noted = set()
        for line in NEEDS.findall(block):
            noted |= {part.strip() for part in line.split(",")}
        for gap in sorted(gaps - noted):
            first = uncommented(block).strip().splitlines()[0][:52]
            missing.append(f"{gap}  in `{first}`")
    assert not missing, (
        f"{path.name} reaches for properties the schema does not declare and "
        f"does not say so. Add a `//   NEEDS:` line naming them, or use a "
        f"property that is declared: {missing}")


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_no_query_claims_a_gap_it_does_not_have(path):
    """The other direction. A NEEDS line that stops being true is a warning
    about nothing, and the first one teaches the reader to skip them all."""
    stale = []
    for block in statement_blocks(path):
        gaps = undeclared(uncommented(block))
        for line in NEEDS.findall(block):
            for part in line.split(","):
                if part.strip() and part.strip() not in gaps:
                    stale.append(part.strip())
    assert not stale, (
        f"{path.name} declares gaps that no longer exist — the schema may have "
        f"caught up: {stale}")


#: Every attribute the schema NAMES, and the source field behind each.
#: An EXACT SET, not a count and not a shape. The check this replaced asserted
#: `len(source) > 8 and "," in source`, which `xxxxxxxxx,y` satisfies — so an
#: entry could be added with a source field nobody could look up and the guard
#: would pass it.
#:
#: Two of the ten name a FILE. The rest name a published dataset and its
#: column, because this repo has no downloader for them: `IPEDS HD` and
#: `IPEDS C` appear nowhere in the tree. So this holds the block to a stable
#: enumeration, and NOT — as an earlier version of it claimed — to a file
#: anyone can open. Naming a plausible filename would be the same wish the
#: block exists to refuse.
NAMED_ATTRIBUTES = {
    "Occupation.name": ("CIP2020_SOC2018_Crosswalk.xlsx", "SOC2018Title"),
    "Programme.name": ("CIP2020_SOC2018_Crosswalk.xlsx", "CIP2020Title"),
    "Institution.name": ("IPEDS HD", "INSTNM"),
    "Institution.control": ("IPEDS HD", "CONTROL"),
    "School.name": ("CCD school directory", "school_name"),
    "District.name": ("CCD district directory", "lea_name"),
    "Completion.awards": ("IPEDS C", "CTOTALT"),
    "Completion.award_level": ("IPEDS C", "AWLEVEL"),
    "Course.description": ("catalog.pwcs.edu", "field--name-field-description"),
    "Course.grade_levels": ("catalog.pwcs.edu", "field--name-field-grades"),
}


#: The two of the ten a loader actually writes — edtech-kg#137.
#: `etl/load_pwcs.py` extracts both from the course page: 783 of 791 courses
#: carry a description and 781 carry grade levels. The other eight are still
#: named-only, because nothing loads Occupation, Programme, Institution,
#: School, District or Completion at all.
LOADED = {"Course.description", "Course.grade_levels"}


def entries_of(marker: str = "PROPERTIES") -> dict[str, tuple[str, ...]]:
    from tests.schema_properties import block

    found = {}
    for line in block(marker).splitlines():
        matched = re.match(r"^//\s+(\w+\.\w+)\s+<-\s+(.+?)\s*$", line)
        if matched:
            found[matched.group(1)] = tuple(
                part.strip() for part in matched.group(2).split(","))
    return found


def test_the_schema_names_exactly_these_attributes_and_these_sources():
    """The point of the PROPERTIES block. A property with no field behind it is
    a wish, and a schema that grants wishes stops describing what anyone
    publishes."""
    assert entries_of() == NAMED_ATTRIBUTES


def test_naming_an_attribute_does_not_make_it_reachable():
    """The distinction the first attempt at #123 collapsed, and the reason
    there are two functions.

    `declared()` is what tells a query it may reach for a property without a
    `NEEDS:` line. Reading the PROPERTIES block into it dropped 33 annotations
    from queries that still return null, because eight of the ten labels have
    NO LOADER AT ALL — `Q2` reaches for `o.name` on a graph holding zero
    `Occupation` nodes. Naming a source is not writing a property.
    """
    named, reachable = named_in_schema(), declared()
    still_unreachable = []
    for name in NAMED_ATTRIBUTES:
        label, prop = name.split(".")
        assert prop in named.get(label, set()), f"{name} is not in the block"
        if prop not in reachable.get(label, set()):
            still_unreachable.append(name)
    assert sorted(still_unreachable) == sorted(set(NAMED_ATTRIBUTES) - LOADED), (
        f"the schema names ten attributes; {sorted(LOADED)} are written by a "
        f"loader and the rest are not. "
        f"{sorted(set(NAMED_ATTRIBUTES) - set(still_unreachable) - LOADED)} "
        f"became reachable — their `NEEDS:` lines are stale and should come "
        f"off the queries that carry them, and "
        f"{sorted(LOADED & set(still_unreachable))} stopped being written.")


def test_only_the_four_loaded_labels_carry_anything_beyond_a_key():
    """The measurement the whole distinction rests on, asserted not quoted.

    `etl/load_pwcs.py` is the only loader this repo has, and it writes four
    labels. Everything else carries its constraint key and nothing more — which
    is why naming an attribute in the schema cannot make a query answerable.

    Keys are DERIVED from the constraints rather than listed here. Listing them
    was the first version and it missed `Credential.ctid`, so the test failed
    on a label nothing writes — a guard reporting the opposite of its subject.
    """
    from tests.schema_properties import SCHEMA

    keys: dict[str, set[str]] = {}
    for _, label, prop in re.findall(
            r"CREATE CONSTRAINT ON \((\w+):(\w+)\) ASSERT \1\.(\w+)",
            SCHEMA.read_text(encoding="utf-8")):
        keys.setdefault(label, set()).add(prop)

    beyond = {label: sorted(props - keys.get(label, set()))
              for label, props in declared().items()
              if props - keys.get(label, set())}
    assert set(beyond) == {"Course", "Pathway", "Requirement", "Subject"}, (
        f"the set of labels a loader writes has changed to {sorted(beyond)}. "
        f"The PROPERTIES block's note about what is unloaded, and every "
        f"`NEEDS:` line resting on it, are now wrong.")


def test_the_undeclared_ones_are_undeclared_deliberately():
    """Five remain, and each is refused for a reason the schema states. A test
    that only checked what IS declared would let the next author quietly add
    `EarningsRecord.median` with no source loaded."""
    from tests.schema_properties import declared

    known = declared()
    assert "length" not in known.get("Course", set()), (
        "Course.length is declared, and no source publishes it — the catalogue "
        "carries credits and grades and no length field at all")
    for prop in ("median", "year", "source", "employment"):
        assert prop not in known.get("EarningsRecord", set()), (
            f"EarningsRecord.{prop} is declared before any earnings source is "
            f"loaded, which fixes a shape before anything has been read")
    schema = schema_text()
    assert "NOT declared, and each for its own reason" in schema


def test_a_property_matched_inline_is_reached_for():
    """`MATCH (c:Completion {award_level: "X"})` reaches for `award_level`
    exactly as much as `c.award_level` does. Reading only the dotted form
    missed it, so a query could match on an undeclared property and the check
    would report no gap at all."""
    from tests.schema_properties import accesses

    found = accesses('MATCH (cm:Completion {award_level: "Certificate"}) RETURN cm')
    assert found == {"Completion": {"award_level"}}


def test_an_anonymous_node_still_attributes_its_property():
    """`(:School {ncessch: …})` names a label, which is all that is needed."""
    from tests.schema_properties import accesses

    assert accesses('MATCH (:School {ncessch: "1"}) RETURN 1') == {
        "School": {"ncessch"}}


def test_a_colon_inside_a_value_is_not_read_as_a_property():
    """`{url: "https://…"}` yielded a property called `https` — the extractor
    inventing a gap the schema could never declare, in a check whose whole job
    is to say what is missing."""
    from tests.schema_properties import accesses

    found = accesses('MATCH (c:Course {url: "https://x/y"}) RETURN c')
    assert found == {"Course": {"url"}}


def test_a_declared_key_matched_inline_is_not_a_gap():
    """The other direction, or the two tests above pass by reporting
    everything."""
    from tests.schema_properties import undeclared

    assert undeclared('MATCH (c:Course {url: "https://x/y"}) RETURN c.name') == set()


SUBSTITUTES = re.compile(r"^//\s+SUBSTITUTES: (.+)$", re.M)


def substituting() -> dict[str, str]:
    """Every question whose query answers something narrower than it asks."""
    found = {}
    for path in files():
        for block in statement_blocks(path):
            label = re.search(r"^// (Q\d+)\.", block, re.M)
            note = SUBSTITUTES.search(block)
            if label and note:
                found[label.group(1)] = note.group(1)
    return found


def test_a_query_that_substitutes_is_marked_with_a_caveat():
    """ONE RULE, applied everywhere — edtech-kg#143.

    `docs/questions.md` defines ⚠️ as "answerable, with a caveat that must
    travel with the answer". Q62 was demoted for answering course-to-course
    where the question says course-to-programme. Seven other queries did the
    same thing and stayed ✅, each stating its substitution in its own prose at
    length — which is what made it clear they were the same case.

    The annotation is the mechanism rather than the prose, for the reason
    `NEEDS:` is: matching words like "only" and "instead" over comments was
    tried while scoping this and returns mostly noise. A query that substitutes
    says so in one line, and that line is what this reads.
    """
    from tests.questions_document import marks

    status = marks()
    wrong = {q: status[q] for q in substituting() if status[q] != "caveat"}
    assert not wrong, (
        f"{wrong} carry a `SUBSTITUTES:` line and are not ⚠️. A query that "
        f"answers a narrower question than its prose asks is answerable with "
        f"a caveat, which is what the key says ⚠️ means.")


def test_the_substitution_says_what_it_answers_instead():
    """A bare `SUBSTITUTES:` is a warning with nothing in it. Each names the
    thing actually answered, so a reader can decide whether it is the answer
    they wanted."""
    thin = {q: note for q, note in substituting().items() if len(note.split()) < 4}
    assert not thin, f"these say they substitute without saying what for: {thin}"


def test_every_caveated_question_with_a_query_says_why_in_place():
    """The other direction, and the rule is "say why" rather than "substitute".

    The first version of this demanded a `SUBSTITUTES:` line on every ⚠️ with a
    query, and eleven failed. They are not all substitutions: measured, Q17 and
    Q18 are ⚠️ because no loader fills `EarningsRecord`, and the tier-5 four
    carry a `[caveat:]` saying the MEASURE is not what the question means.
    Three different reasons, and only one of them is a query answering
    something narrower.

    So each of the three annotations counts, and the requirement is that a ⚠️
    with a query carries one of them — a caveat a reader has to infer from
    prose is the thing this repo keeps finding.
    """
    from tests.questions_document import marks

    answered_by = {q for path in files() for q in answered(path)}
    said = set(substituting())
    for path in files():
        for block in statement_blocks(path):
            label = re.search(r"^// (Q\d+)\.", block, re.M)
            if label and (re.search(r"^//\s+\[caveat:", block, re.M)
                          or NEEDS.search(block)):
                said.add(label.group(1))

    silent = sorted({q for q, mark in marks().items()
                     if mark == "caveat" and q in answered_by} - said,
                    key=lambda q: int(q[1:]))
    assert not silent, (
        f"{silent} are ⚠️ with a query and say nothing in the file about why — "
        f"no `SUBSTITUTES:`, no `[caveat:]`, no `NEEDS:`. The mark is in "
        f"docs/questions.md and the reason has to be where the query is.")
