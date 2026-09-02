"""What the benchmark statements do when they are RUN.

Split from `tests/test_question_traversals.py` at the 500-line review limit.
Split by SUBJECT: that file reads the `.cypher` files and `docs/questions.md`
against each other — every statement parses, every question that claims a
traversal has one, every property a query reaches for is declared. None of it
needs a graph. This file needs a loaded one, because every defect below was
invisible without it.

The three that got through, in order of how quietly:

- Q68 PARSED, ran, and returned nothing on a graph holding 119 chains.
- Q71 ran and returned 359 rows that were every edge in the graph.
- Every url-anchored statement in tier 4 filtered with an inline property map,
  which this engine does not apply, at urls that no course carries anyway —
  two independent defects, each of which hid the other, and both of which hid
  two type errors underneath, because a predicate over no rows is never
  evaluated.

So: it runs, it answers something, it answers about the thing it names.
"""

from __future__ import annotations

import os
import re

import pytest

from tests.test_schema_engine import SAMYAMA_URL, query, require_engine
from tests.test_question_traversals import files, labelled_statements, statements


def require_data(message: str) -> None:
    """Skip, or FAIL under `SAMYAMA_REQUIRE_DATA=1`.

    A SEPARATE FLAG from `SAMYAMA_REQUIRE_ENGINE`, which these three gates used
    and which does not mean this. `SAMYAMA_REQUIRE_ENGINE=1` asserts an engine
    is REACHABLE — `tests/test_schema_engine.py` defines it that way and CI sets
    it against a deliberately empty engine, which is the right thing for the
    schema tests to check. These gates need a district LOADED, which is a
    different claim, and reading one flag as the other turned every one of them
    into a hard failure on a run that was behaving exactly as intended.

    So: `SAMYAMA_REQUIRE_DATA=1` in a job that loads a district. Nothing sets it
    today, which is honest — CI loads no district — and the skips it produces
    are on the `conftest.py` allowlist so they stay visible rather than silent.
    """
    if os.environ.get("SAMYAMA_REQUIRE_DATA") == "1":
        pytest.fail(f"{message} — SAMYAMA_REQUIRE_DATA=1 forbids skipping this")
    pytest.skip(message)


def answers_emptily(result: dict) -> bool:
    """Whether a result is empty in the sense this file cares about.

    Not `records == []`. A BARE AGGREGATE returns exactly one row on any graph
    whatsoever — measured: `max(length(p))` over a label the graph does not
    contain returns `[[None]]`, and `count(c)` returns `[[0]]`. Four of the
    eleven statements guarded below are bare aggregates, so a check that reads
    the row count could not fail for them however wrong the answer was. It was
    written to catch Q68, and Q68's own shape would have walked straight
    through it.

    So for a single row the ANSWER is what to read, not the row.
    """
    records = result.get("records") or []
    if not records:
        return True
    if len(records) == 1:
        return all(v is None or v == 0 for v in records[0])
    return False


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_every_statement_runs_where_there_is_data_to_run_against(path):
    """EXECUTION, not parsing. The distinction Q68 cost a round to learn.

    A predicate inside a `WHERE` is never evaluated on an empty graph, so a
    type error that would fail on real data passes on an empty engine. Q68
    parsed, ran, and returned a confident wrong answer for exactly that reason,
    and the validation that missed it ran against an engine holding nothing.

    Gated on the graph holding COURSES rather than on the engine answering.
    Skipping when there is no data is honest; skipping when there IS data would
    be the failure this file is about, so `SAMYAMA_REQUIRE_DATA=1` turns the
    skip into a failure — a flag about DATA, not about the engine answering.
    """
    require_engine()
    loaded = query(SAMYAMA_URL, "MATCH (c:Course) RETURN count(c) AS n")
    held = (loaded.get("records") or [[0]])[0][0] if "error" not in loaded else 0
    if not held:
        message = (f"the graph at {SAMYAMA_URL} holds no Course nodes, so a "
                   f"predicate inside a WHERE is never evaluated and this "
                   f"checks nothing — load a district first")
        require_data(message)

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
#: Not every question belongs here. Q61-Q65, Q69, Q70, Q73 and Q77 scope to an
#: example URL, and Q97, Q98 and Q100 reach for Programme and Occupation, which
#: no loader fills. Zero from those is correct and asserting otherwise would
#: turn a fixture choice into a failure.
#:
#: Q101 IS here because `etl/load_pwcs.py` fills `Pathway` and writes
#: `INCLUDES` — 42 pathways and 316 edges on the district it loads — so a zero
#: there is a defect rather than a missing loader. Named, because the rule
#: above is about which labels a loader fills and Q101 is the one case where
#: that has to be checked rather than assumed.
#:
#: COST: Q72 runs `shortestPath` over every Course pair and Q74 unwinds every
#: path in the prerequisite graph. Both complete on one district — 791 courses,
#: 240 edges — and both scale with whatever is loaded. When a second district
#: lands (#19) this test is where the suite slows down, and it will look like a
#: hang rather than a failure. Bound them or drop them from this list then;
#: they are here now because they are the two that exercise the deepest
#: traversal the engine does.
ANSWERS_OVER_THE_WHOLE_GRAPH = {
    "tier-4-graph-algorithms": ["Q66", "Q72", "Q74", "Q76", "Q79"],
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
        require_data(message)

    empty, reached = [], set()
    for label, body in labelled_statements(path):
        if label not in wanted:
            continue
        reached.add(label)
        result = query(SAMYAMA_URL, body)
        if result.get("transport"):
            continue          # excluded, as the sibling test above excludes it
        if "error" in result or answers_emptily(result):
            empty.append(label)

    # The list is a ratchet, so it has to fail when it stops applying. Renaming
    # or deleting a question silently emptied it before, which is the failure
    # mode a ratchet exists to not have: it went green by checking nothing.
    assert reached == set(wanted), (
        f"{path.name}: {sorted(set(wanted) - reached)} are named in "
        f"ANSWERS_OVER_THE_WHOLE_GRAPH and are not in the file. Either the "
        f"question moved and the list did not follow, or it was dropped and "
        f"the list is now guarding fewer statements than it says.")
    assert not empty, (
        f"{path.name}: {sorted(set(empty))} answered emptily against {held:,} "
        f"prerequisite edges — no rows, or a lone aggregate row that is null "
        f"or zero. A whole-graph question answering emptily on a non-empty "
        f"graph is the signal Q68 gave: it runs, it answers, and it is wrong.")


#: The tiers this change re-anchored. Tiers 1 to 3 carry both defects below in
#: about thirty statements and are NOT fixed here — that is a PR of its own,
#: and a guard that quietly skipped them would read as coverage.
ANCHORS_CHECKED = ("tier-4-graph-algorithms", "tier-5-multi-domain",
                   "tier-6-whole-graph")

INLINE_MAP = re.compile(r"\(\s*\w*\s*:\s*\w+\s*\{\s*\w+\s*:\s*[\"']")


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_no_statement_filters_with_an_inline_property_map(path):
    """An inline property map does not filter on this engine.

    Measured, and it is the worst thing in this file's history because it is
    silent in both directions at once:

        MATCH (c:Course {url: "<a url no course has>"}) RETURN count(c)   -> 791
        MATCH (c:Course {url: "<a url no course has>"}) RETURN c.url      -> []
        MATCH (pw:Pathway {kind: "career pathway"})     RETURN count(pw)  ->  42
        MATCH (pw:Pathway) WHERE pw.kind = "career pathway" ... count     ->  16

    So an aggregate behind one answers about the whole graph and a projection
    behind one answers about nothing, and neither errors. Every url-anchored
    query in tier 4 was written this way: they returned zero rows, which read
    as "this district has no such chain" and was really "this filter was never
    applied". It also hid the anchors being wrong — see the test below — and
    hid two type errors, because a predicate over no rows is never evaluated.

    `WHERE` filters correctly. Use it.
    """
    if path.stem not in ANCHORS_CHECKED:
        pytest.skip(f"{path.stem} is not re-anchored yet — edtech-kg#22 follow-up")
    offenders = [body.splitlines()[0][:60] for _, body in labelled_statements(path)
                 if INLINE_MAP.search(body)]
    assert not offenders, (
        f"{path.name} filters with an inline property map, which this engine "
        f"does not apply — the query answers about the whole label or about "
        f"nothing, and never says so. Use WHERE: {offenders}")


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_every_course_url_a_statement_anchors_on_exists(path):
    """An anchor that matches no node is a question answered about nothing.

    Every url in tier 4 pointed at `catalog.pwcs.edu/agriculture/...` and
    `catalog.pwcs.edu/science/...`; the catalogue publishes
    `agriculture-food-and-natural-resources/` and `science-standard/`, and
    `landscaping-4`, `landscaping-6` and `chemistry-1` under those prefixes do
    not exist at all. Nine statements answered emptily for that reason and the
    suite was green, because the inline property map above meant the anchor was
    never applied in the first place and there was nothing to notice.
    """
    if path.stem not in ANCHORS_CHECKED:
        pytest.skip(f"{path.stem} is not re-anchored yet — edtech-kg#22 follow-up")
    require_engine()
    loaded = query(SAMYAMA_URL, "MATCH (c:Course) RETURN count(c) AS n")
    held = (loaded.get("records") or [[0]])[0][0] if "error" not in loaded else 0
    if not held:
        message = (f"the graph at {SAMYAMA_URL} holds no Course nodes, so no "
                   f"anchor can resolve and this checks nothing")
        require_data(message)

    anchors = set()
    for _, body in labelled_statements(path):
        anchors |= set(re.findall(r'\w+\.url\s*=\s*"([^"]+)"', body))
        anchors |= set(re.findall(r'"(https://catalog\.pwcs\.edu/[^"]+)"', body))
    if not anchors:
        # A ratchet with a named baseline rather than a silent skip: tier 4 is
        # the file that anchors on example courses, and it going quiet is the
        # thing this test exists to notice.
        assert path.stem != "tier-4-graph-algorithms", (
            f"{path.name} anchors on no course url at all — either the parser "
            f"stopped reading it or the examples were removed")
        pytest.skip(f"{path.stem} anchors on no course url")
    missing = []
    for url in sorted(anchors):
        result = query(SAMYAMA_URL, f'MATCH (c:Course) WHERE c.url = "{url}" '
                                    f'RETURN count(c) AS n')
        if result.get("transport"):
            pytest.skip("the engine stopped answering mid-check")
        if not (result.get("records") or [[0]])[0][0]:
            missing.append(url)
    assert not missing, (
        f"{path.name} anchors on course urls that no node carries, so those "
        f"statements answer about nothing: {missing}")
