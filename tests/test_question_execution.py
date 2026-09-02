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
- Every url-anchored statement in tier 4 anchored on a url no course carries,
  and filtered with an inline property map — which a SINGLE-NODE match does not
  apply, though a relationship pattern does. Two independent defects, and both
  hid two type errors underneath, because a predicate over no rows is never
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
def test_every_whole_graph_question_named_is_in_its_file(path):
    """The ratchet half, HOISTED OUT of the data gate.

    It read the file and nothing else, and sat below `require_engine()` and the
    loaded-district check — so in CI, which starts an empty engine, the one
    assertion here that needs no graph never ran. A ratchet that cannot fire
    where it matters most is the failure it exists to prevent.

    Renaming or deleting a question emptied the list silently: it went green by
    checking nothing.
    """
    wanted = ANSWERS_OVER_THE_WHOLE_GRAPH.get(path.stem)
    if not wanted:
        pytest.skip(f"{path.stem} has no whole-graph statements to check")
    present = {label for label, _ in labelled_statements(path)}
    assert set(wanted) <= present, (
        f"{path.name}: {sorted(set(wanted) - present)} are named in "
        f"ANSWERS_OVER_THE_WHOLE_GRAPH and are not in the file. Either the "
        f"question moved and the list did not follow, or it was dropped and "
        f"the list is now guarding fewer statements than it says.")


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

    empty = []
    for label, body in labelled_statements(path):
        if label not in wanted:
            continue
        result = query(SAMYAMA_URL, body)
        if result.get("transport"):
            continue          # excluded, as the sibling test above excludes it
        if "error" in result or answers_emptily(result):
            empty.append(label)

    assert not empty, (
        f"{path.name}: {sorted(set(empty))} answered emptily against {held:,} "
        f"prerequisite edges — no rows, or a lone aggregate row that is null "
        f"or zero. A whole-graph question answering emptily on a non-empty "
        f"graph is the signal Q68 gave: it runs, it answers, and it is wrong.")


#: EMPTY, and that is the removal condition edtech-kg#133 was written against.
#:
#: It held tier-1, tier-2 and tier-3 as strict xfails while 39 of their 51
#: statements filtered with a single-node inline property map at urls no course
#: carries. When they were fixed the six xfails XPASSed and the suite went red,
#: which is what a strict xfail is for — the exemption reported its own end
#: rather than waiting for someone to remember it.
#:
#: Kept rather than deleted so a tier can be exempted again with an argument
#: and an issue, which is how it earned its place the first time.
NOT_YET_ANCHORED: tuple[str, ...] = ()


def expect_failure(request, path) -> None:
    """Mark a not-yet-anchored tier as an EXPECTED failure, strictly.

    Not `pytest.skip()`: an exempted tier is not inapplicable, it is known
    broken, and the two read identically in every summary line. Not
    `pytest.xfail()` either, which is imperative and short-circuits — the body
    never runs, the test can never XPASS, and a reminder that cannot notice
    being satisfied is a skip wearing a different word.

    The marker is applied and the body RUNS. Verified in anger on #133: fixing
    the three tiers turned six xfails into six failures.
    """
    if path.stem in NOT_YET_ANCHORED:
        request.applymarker(pytest.mark.xfail(
            strict=True,
            reason=f"{path.stem} is not re-anchored yet — edtech-kg#133"))


INLINE_MAP = re.compile(r"\(\s*\w*\s*:\s*\w+\s*\{\s*\w+\s*:\s*[\"']")


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_no_statement_filters_with_an_inline_property_map(path, request):
    """A SINGLE-NODE match does not apply its inline property map.

    Corrected in edtech-kg#133. This said "an inline property map does not
    filter on this engine", which is too broad: inside a relationship pattern
    it filters correctly, measured both ways. What is broken is the bare
    single-node form, and it is silent in both directions at once:

        MATCH (c:Course {url: "<a url no course has>"}) RETURN count(c)   -> 791
        MATCH (c:Course {url: "<a url no course has>"}) RETURN c.url      -> []
        MATCH (pw:Pathway {kind: "career pathway"})     RETURN count(pw)  ->  42
        MATCH (pw:Pathway) WHERE pw.kind = "career pathway" ... count     ->  16

        MATCH (d:Course)-[:REQUIRES]->(c:Course {url: "<real>"}) count    ->   1
        MATCH (d:Course)-[:REQUIRES]->(c:Course {url: "<fake>"}) count    ->   0

    So an aggregate behind a bare one answers about the whole label and a
    projection behind it answers about nothing, and neither errors — while the
    same syntax two lines away is fine. Banned outright rather than only in the
    single-node case, because which one you are looking at is not visible at a
    glance and the failure is silent when you get it wrong.

    The url-anchored queries in tier 4 answered about nothing because their
    URLs were wrong. This is a second defect that was hiding behind the first,
    not the cause of it — `test_every_course_url_a_statement_anchors_on_exists`
    is what catches that one.

    `WHERE` filters correctly in every position. Use it.
    """
    expect_failure(request, path)
    offenders = [body.splitlines()[0][:60] for _, body in labelled_statements(path)
                 if INLINE_MAP.search(body)]
    assert not offenders, (
        f"{path.name} filters with an inline property map. On a single-node "
        f"match this engine does not apply it — the query answers about the "
        f"whole label or about nothing, and never says so. Use WHERE, which "
        f"works in every position: {offenders}")


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_every_course_url_a_statement_anchors_on_exists(path, request):
    """An anchor that matches no node is a question answered about nothing.

    Every url in tier 4 pointed at `catalog.pwcs.edu/agriculture/...` and
    `catalog.pwcs.edu/science/...`; the catalogue publishes
    `agriculture-food-and-natural-resources/` and `science-standard/`, and
    `landscaping-4`, `landscaping-6` and `chemistry-1` under those prefixes do
    not exist at all. Nine statements answered emptily for that reason and the
    suite was green, because the inline property map above meant the anchor was
    never applied in the first place and there was nothing to notice.
    """
    expect_failure(request, path)
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


# --------------------------------------------------------------------------
# The constants above are keyed on FILE STEMS, and a stem is not a thing the
# type system checks. Measured on #128: renaming `tier-4-graph-algorithms.cypher`
# made the suite GREENER — two failures vanished and three skips appeared —
# and deleting `tier-6-whole-graph.cypher` lost the whole-graph guard with
# nothing said. A ratchet that goes quiet when its subject moves is the exact
# class it exists to prevent.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name, keys", [
    ("ANSWERS_OVER_THE_WHOLE_GRAPH", tuple(ANSWERS_OVER_THE_WHOLE_GRAPH)),
    ("NOT_YET_ANCHORED", NOT_YET_ANCHORED),
])
def test_every_tier_a_constant_names_is_a_file_that_exists(name, keys):
    """Renaming or deleting a tier file has to say so, not go quiet."""
    stems = {path.stem for path in files()}
    assert stems, "files() found no benchmark files at all"
    missing = sorted(set(keys) - stems)
    assert not missing, (
        f"{name} names {missing}, and no `tier-*.cypher` has that stem. Either "
        f"the file was renamed and the constant did not follow — in which case "
        f"its guard is now silently checking nothing — or it was deleted and "
        f"the entry is stale.")


def test_require_data_fails_rather_than_skips_when_the_flag_is_set(monkeypatch):
    """`SAMYAMA_REQUIRE_DATA=1` has no test and no job that sets it.

    It was introduced so these gates stop misreading `SAMYAMA_REQUIRE_ENGINE`,
    which asserts an engine is REACHABLE and not that a district is LOADED.
    Nothing exercises the fail branch, so it can rot unnoticed — which is the
    class of bug it was added to fix. Verified by hand once is not covered.
    """
    monkeypatch.setenv("SAMYAMA_REQUIRE_DATA", "1")
    # NOT `pytest.raises(pytest.fail.Exception)`. `Skipped` is a
    # `BaseException` and is not `Failed`, so if `require_data` starts skipping
    # here — which is exactly the regression this test exists to catch — the
    # skip escapes the block and SKIPS this test rather than failing it.
    # Measured: deleting the fail branch left the suite green at 17 passed,
    # 11 skipped. The type of what was raised has to BE the assertion.
    try:
        require_data("no district loaded")
    except BaseException as raised:      # noqa: B036 - the type is the assertion
        outcome: BaseException | None = raised
    else:
        outcome = None
    assert isinstance(outcome, pytest.fail.Exception), (
        f"SAMYAMA_REQUIRE_DATA=1 must FAIL, not skip — require_data raised "
        f"{type(outcome).__name__ if outcome else 'nothing'}")
    assert "forbids skipping this" in str(outcome)


def test_require_data_skips_when_the_flag_is_unset(monkeypatch):
    """The other bound, and `pytest.raises(Skipped)` rather than
    `pytest.raises(Failed)`: `Skipped` is a `BaseException` and is not
    `Failed`, so a `Failed` block around a skip SKIPS the test instead of
    failing it — and every assertion about the guard turns green."""
    monkeypatch.delenv("SAMYAMA_REQUIRE_DATA", raising=False)
    with pytest.raises(pytest.skip.Exception, match="no district loaded"):
        require_data("no district loaded")


def test_the_inline_map_defect_is_the_single_node_form_and_only_that():
    """The claim the ban rests on, measured rather than remembered.

    It was first written down as "an inline property map does not filter on
    this engine", and that is too broad — every example behind it happened to
    be a single-node match. Inside a relationship pattern the map filters
    correctly, which is why `Q15` returned the same 98 rows before and after
    conversion while seven other statements went from 0 rows to 1.

    Overstating a defect is not a safe direction to be wrong in: it moves the
    reason for a rule away from the thing the rule protects, and the next
    person removes the rule because the reason does not hold.

    Engine-gated because it is a statement about the engine.
    """
    require_engine()
    loaded = query(SAMYAMA_URL, "MATCH (c:Course) RETURN count(c) AS n")
    held = (loaded.get("records") or [[0]])[0][0] if "error" not in loaded else 0
    if not held:
        require_data(f"the graph at {SAMYAMA_URL} holds no Course nodes, so a "
                     f"predicate inside a WHERE is never evaluated and this "
                     f"checks nothing — load a district first")

    def rows(cypher):
        result = query(SAMYAMA_URL, cypher)
        assert "error" not in result, f"{cypher} -> {result['error']}"
        return (result.get("records") or [[0]])[0][0]

    absent = "https://catalog.pwcs.edu/no/such-course"

    # BROKEN: a bare single-node match ignores the map entirely.
    assert rows(f'MATCH (c:Course {{url: "{absent}"}}) RETURN count(c) AS n') == held, (
        "a single-node inline map now filters — the ban above can be narrowed, "
        "and the docstring explaining it is out of date")
    assert rows(f'MATCH (c:Course) WHERE c.url = "{absent}" RETURN count(c) AS n') == 0

    # FINE: the same syntax inside a relationship pattern.
    assert rows(f'MATCH (:Course)-[:REQUIRES]->(c:Course {{url: "{absent}"}}) '
                f'RETURN count(*) AS n') == 0, (
        "a relationship-pattern inline map has stopped filtering too — the "
        "defect is wider than this file says")

