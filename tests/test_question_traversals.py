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
            marks = [(line.index(c), name) for c, name in
                     (("✅", "ok"), ("⚠️", "caveat"), ("❌", "no"))
                     if c in line]
            found[m.group(1)] = min(marks)[1] if marks else "unmarked"
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
    wrong = [q for q in answered(path) if marks().get(q) == "no"]
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
