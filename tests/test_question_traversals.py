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

import os
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


#: A question STARTS a block. Two spellings ship — `**Q1.** text` and
#: `**Q61. text**` — and the second was invisible to a parser that required
#: the closing `**` right after the number, so five questions were not read at
#: all. Marks are read from the block, not the line, because a question that
#: wraps carries its mark on the continuation.
QUESTION = re.compile(r"^\*\*(Q\d+)\.", re.M)


def blocks() -> dict[str, str]:
    """Each question with everything up to the next one.

    Line-by-line was wrong in two ways at once. It required `**Qn.**`, so
    `**Q61. What is…**` was not a question; and it read the mark from the
    FIRST physical line, so a question wrapping onto a second was reported
    unmarked while its mark sat one line down. Eighteen were, and an unmarked
    question is exempt from the ratchet — so eighteen answerable questions
    could have had no traversal and nothing would have said so.
    """
    text = QUESTIONS.read_text(encoding="utf-8")
    starts = [(m.group(1), m.start()) for m in QUESTION.finditer(text)]
    found = {}
    for index, (name, at) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        # A block also stops at the next HEADING, or the prose between tiers
        # is read as part of the last question in the tier above.
        heading = text.find("\n## ", at)
        if heading != -1 and heading < end:
            end = heading
        found[name] = text[at:end]
    return found


def marks() -> dict[str, str]:
    """Every question in the document, with its mark."""
    found = {}
    for name, block in blocks().items():
        # The FIRST mark in the block, by position. A fixed priority order
        # reads a status character mentioned in an explanation as the
        # question's own mark — which is what happened when Q19's re-marking
        # said what it used to be.
        positions = [(block.index(c), state) for c, state in
                     (("✅", "ok"), ("⚠️", "caveat"), ("❌", "no"))
                     if c in block]
        found[name] = min(positions)[1] if positions else "unmarked"
    return found


def test_there_are_benchmark_files_to_check():
    """A glob that matches nothing makes every test below vacuous."""
    assert files(), f"no tier-*.cypher under {BENCHMARKS}"


def test_the_parser_reads_every_question_in_the_document():
    """`> 50` was the old bound and it was far too loose.

    The parser saw 97 of 102 and reported 18 of those as unmarked, so 79 were
    classified correctly and the bound passed anyway. An unmarked question is
    exempt from the ratchet below, so twenty-three answerable questions could
    have had no traversal and nothing would have said so.

    Counted against the document rather than a number written here, and
    nothing may be left unmarked — "unmarked" is the state that quietly
    excuses a question.
    """
    text = QUESTIONS.read_text(encoding="utf-8")
    in_document = {m.group(1) for m in QUESTION.finditer(text)}
    found = marks()
    assert set(found) == in_document, (
        f"the parser missed {sorted(in_document - set(found))} and invented "
        f"{sorted(set(found) - in_document)}")
    unmarked = [q for q, state in found.items() if state == "unmarked"]
    assert not unmarked, (
        f"{unmarked} carry no status, so the ratchet cannot tell whether they "
        f"need a traversal")
    assert {"ok", "caveat", "no"} <= set(found.values())


def test_the_tally_the_document_prints_is_the_one_the_parser_reads():
    """The document's own table is machine-checked by `test_questions.py`
    against a different parser. If the two disagree, one of them is wrong
    about the same file — and this one drives which questions need a
    traversal."""
    from collections import Counter

    counted = Counter(marks().values())
    text = QUESTIONS.read_text(encoding="utf-8")
    row = re.search(r"\| \*\*Total\*\* \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \| "
                    r"\*\*(\d+)\*\* \| \*\*(\d+)\*\* \|", text)
    assert row, "the totals row is no longer in questions.md"
    total, ok, caveat, no = (int(g) for g in row.groups())
    assert (counted["ok"], counted["caveat"], counted["no"]) == (ok, caveat, no), (
        f"the document's table says {ok}/{caveat}/{no} and this parser reads "
        f"{counted['ok']}/{counted['caveat']}/{counted['no']}")
    assert sum(counted.values()) == total


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


# --------------------------------------------------------------------------
# The extractor, driven. It decides which gaps get reported, so a hole in it
# is a gap nobody hears about — and it had two, both found writing tier 2.
# --------------------------------------------------------------------------

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


def prose_only(block: str) -> str:
    """The block with `code spans` removed.

    An asterisk inside backticks is code — a Cypher `*1..1`, a glob, a
    multiplication — and counting it as emphasis is how a well-formed block
    fails a truncation check.
    """
    return re.sub(r"`[^`]*`", "", block)


def test_no_question_carries_an_orphaned_fragment():
    """A by-line re-mark leaves the continuation behind, and the tier count
    does not notice.

    Q75's re-mark left two orphan lines and the document's own guards caught it
    — the tier read 21 questions. Q78's left one, and nothing caught it,
    because the fragment does not begin with `**Q` so the count stayed at 20.
    The ratchet detects one shape of this bug and not the other.

    What the fragment DOES carry is an unmatched `*`: `cover over paths.*` is
    the tail of an italic whose opening went with the replaced line. Emphasis
    markers pair, so an odd count in a block is a truncated one — measured,
    Q78 was the only block in the document with one.

    A PROXY for truncation, not a Markdown check. The message says emphasis
    because that is the symptom, and the next person who trips it should know
    they are looking at a truncation heuristic.

    Asterisks inside `code spans` are excluded, and that is not a nicety: the
    Q71 re-mark quotes a Cypher fragment whose `*` is a path quantifier, and
    counting it failed this test on a block that was perfectly well formed. A
    literal asterisk in PROSE still fails, and the fix then is to escape it,
    because the pairing is what makes this mean anything.
    """
    ragged = {q: prose_only(block).count("*") for q, block in blocks().items()
              if prose_only(block).count("*") % 2}
    assert not ragged, (
        f"these questions have unbalanced emphasis markers, which is what a "
        f"line-replaced re-mark leaves behind: {ragged}. Replace the whole "
        f"block, not its first line.")


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_every_statement_runs_where_there_is_data_to_run_against(path):
    """EXECUTION, not parsing. The distinction Q68 cost a round to learn.

    A predicate inside a `WHERE` is never evaluated on an empty graph, so a
    type error that would fail on real data passes on an empty engine. Q68
    parsed, ran, and returned a confident wrong answer for exactly that reason,
    and the validation that missed it ran against an engine holding nothing.

    Gated on the graph holding COURSES rather than on the engine answering.
    Skipping when there is no data is honest; skipping when there IS data would
    be the failure this file is about, so `SAMYAMA_REQUIRE_ENGINE=1` turns the
    skip into a failure the same way the schema tests do.
    """
    require_engine()
    loaded = query(SAMYAMA_URL, "MATCH (c:Course) RETURN count(c) AS n")
    held = (loaded.get("records") or [[0]])[0][0] if "error" not in loaded else 0
    if not held:
        message = (f"the graph at {SAMYAMA_URL} holds no Course nodes, so a "
                   f"predicate inside a WHERE is never evaluated and this "
                   f"checks nothing — load a district first")
        if os.environ.get("SAMYAMA_REQUIRE_ENGINE") == "1":
            pytest.fail(f"{message} — SAMYAMA_REQUIRE_ENGINE=1 forbids skipping this")
        pytest.skip(message)

    broken = []
    for statement in statements(path):
        result = query(SAMYAMA_URL, statement)
        if "error" in result and not result.get("transport"):
            broken.append(f"{statement.splitlines()[0][:56]} -> "
                          f"{result['error'][:110]}")
    assert not broken, (
        f"{path.name} carries statements that PARSE and fail when run against "
        f"{held:,} loaded courses: {broken}")


#: Statements that walk the WHOLE graph and touch only loaded labels. Each must
#: return at least one row against a loaded district, because zero from one of
#: these is the signal Q68 emitted — a query that runs, answers, and is wrong.
#:
#: Not every question belongs here. Q61-Q65, Q69, Q70 and Q77 scope to an
#: example URL, and Q97, Q98 and Q100 reach for Programme and Occupation, which
#: no loader fills. Zero from those is correct and asserting otherwise would
#: turn a fixture choice into a failure.
ANSWERS_OVER_THE_WHOLE_GRAPH = {
    "tier-4-graph-algorithms": ["Q66", "Q72", "Q73", "Q74", "Q76", "Q79"],
    "tier-6-whole-graph": ["Q95", "Q96", "Q99", "Q101", "Q102"],
}


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_a_whole_graph_question_answers_when_the_graph_is_not_empty(path):
    """The check the two above are not.

    Q68 ran clean and returned nothing on a graph with 119 chains; Q71 ran
    clean and returned 359 rows that were every edge in the graph. Erroring is
    not the failure mode that hurt — answering is.

    This catches the empty half. The non-empty-but-wrong half is not
    guardable without knowing the right answer, and saying so is better than a
    check that implies otherwise.
    """
    wanted = ANSWERS_OVER_THE_WHOLE_GRAPH.get(path.stem)
    if not wanted:
        pytest.skip(f"{path.stem} has no whole-graph statements to check")
    require_engine()
    loaded = query(SAMYAMA_URL, "MATCH (c:Course)-[:REQUIRES]->(:Course) RETURN count(*) AS n")
    held = (loaded.get("records") or [[0]])[0][0] if "error" not in loaded else 0
    if not held:
        message = (f"the graph at {SAMYAMA_URL} holds no prerequisite edges, so "
                   f"every whole-graph statement is legitimately empty and this "
                   f"checks nothing — load a district first")
        if os.environ.get("SAMYAMA_REQUIRE_ENGINE") == "1":
            pytest.fail(f"{message} — SAMYAMA_REQUIRE_ENGINE=1 forbids skipping this")
        pytest.skip(message)

    text = path.read_text(encoding="utf-8")
    empty = []
    for block in re.split(r"(?<=;)\n", text):
        label = re.search(r"^// (Q\d+)\.", block, re.M)
        body = uncommented(block).strip().rstrip(";")
        if not label or label.group(1) not in wanted or not body:
            continue
        result = query(SAMYAMA_URL, body)
        if "error" in result or not (result.get("records") or []):
            empty.append(label.group(1))
    assert not empty, (
        f"{path.name}: {empty} returned nothing against {held:,} prerequisite "
        f"edges. A whole-graph question answering emptily on a non-empty graph "
        f"is the signal Q68 gave — it runs, it answers, and it is wrong.")
