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
from tests.schema_properties import undeclared
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


def SCHEMA_TEXT() -> str:
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


def test_the_schema_declares_the_attributes_the_questions_need():
    """This replaces a test that asserted the OPPOSITE.

    It used to assert only four labels carried more than a key, and said in its
    own docstring: "when #123 fixes that, this fails and the NEEDS lines shrink
    with it rather than lingering." #123 is fixed, it failed, and 27 NEEDS lines
    went with it.

    What remains is the honest floor: the labels a question asks for by name
    must carry one, because `Q2. What occupation does this SOC code name?` is
    entirely the name.
    """
    from tests.schema_properties import declared

    known = declared()
    for label in ("Occupation", "Programme", "Institution", "School", "District"):
        assert "name" in known.get(label, set()), (
            f"{label} carries no name, so a question asking what something is "
            f"called cannot be answered")
    assert {"awards", "award_level"} <= known.get("Completion", set())


def test_nothing_is_declared_without_a_source_field_behind_it():
    """The point of the PROPERTIES block. A property with no field behind it is
    a wish, and a schema that grants wishes stops describing what anyone
    publishes."""
    from tests.schema_properties import declared_block

    lines = [line for line in declared_block().splitlines()
             if re.match(r"^//\s+\w+\.\w+", line)]
    assert len(lines) >= 10, f"the PROPERTIES block reads {len(lines)} entries"
    for line in lines:
        assert "<-" in line, f"no source named: {line.strip()}"
        source = line.split("<-", 1)[1].strip()
        assert len(source) > 8 and "," in source, (
            f"the source is not a named file and field: {line.strip()}")


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
    schema = SCHEMA_TEXT()
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
