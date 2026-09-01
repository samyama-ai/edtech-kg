"""Every answerable question has a traversal, and the traversal parses — #22.

`docs/questions.md` marks questions ✅ answerable, ⚠️ answerable with a caveat,
or ❌ not. Those marks were a judgement. This turns them into a check: a
question marked answerable whose query the engine will not parse is a question
the schema does not serve, and the mark is wrong.

**Parsing is the honest bound.** Nothing is loaded, so a query returning rows
is not available as evidence; what these establish is that the traversal is
expressible against the declared schema. A query that parses and names a
property no loader writes would still pass — stated here rather than left for a
reader to assume otherwise.

Written for the engine this repo pins: a pattern inside `WHERE` does not parse
(see `docs/schema.md`), so absence is `NOT EXISTS { MATCH ... }` throughout.
"""

from __future__ import annotations

import pathlib
import re

import pytest

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


def files() -> list[pathlib.Path]:
    return sorted(BENCHMARKS.glob("tier-*.cypher"))


def statements(path: pathlib.Path) -> list[str]:
    return [s.strip() for s in uncommented(path.read_text(encoding="utf-8")).split(";")
            if s.strip()]


def answered(path: pathlib.Path) -> list[str]:
    """The question ids a benchmark file claims to answer."""
    return re.findall(r"^// (Q\d+)\.", path.read_text(encoding="utf-8"), re.M)


def marks() -> dict[str, str]:
    """Every question in the document, with its mark."""
    found = {}
    for line in QUESTIONS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\*\*(Q\d+)\.\*\*", line)
        if m:
            # The FIRST mark in the line, by position. A fixed priority order
            # reads a status character mentioned in an explanation as the
            # question's own mark — which is exactly what happened when Q19's
            # re-marking said what it used to be.
            positions = [(line.index(c), name) for c, name in
                         (("✅", "ok"), ("⚠️", "caveat"), ("❌", "no"))
                         if c in line]
            found[m.group(1)] = min(positions)[1] if positions else "unmarked"
    return found


def test_there_are_benchmark_files_to_check():
    """A glob that matches nothing makes every test below vacuous."""
    assert files(), f"no tier-*.cypher under {BENCHMARKS}"


def test_the_questions_document_still_parses_into_marks():
    found = marks()
    assert len(found) > 50, f"only {len(found)} questions read from questions.md"
    assert "ok" in found.values() and "no" in found.values()


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
        m = re.match(r"^\*\*(Q\d+)\.\*\*", line)
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


def test_the_schema_still_declares_almost_nothing_but_keys():
    """The premise the annotations rest on, asserted rather than assumed.

    If this fails the schema has gained properties, which is #123 being fixed —
    and the NEEDS lines above should shrink with it rather than linger.
    """
    from tests.schema_properties import declared

    known = declared()
    with_attributes = {label for label, props in known.items() if len(props) > 1}
    assert with_attributes == {"Course", "Subject", "Pathway", "Requirement"}, (
        f"the set of labels carrying more than a key has changed: "
        f"{sorted(with_attributes)}. Every one of those has a loader; if a "
        f"label gained properties another way, this check is now reading the "
        f"wrong source")

