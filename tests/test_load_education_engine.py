"""The loader against a real engine, on a small slice.

    SAMYAMA_TEST_URL=http://localhost:8201 pytest \\
        tests/test_load_education_engine.py

edtech-kg#7. The file beside this one drives the loader against a recorder and
proves what it *sends*. That is not the same claim as what the graph *holds*,
and on this engine the two come apart in ways that matter: a unique constraint
does not reject a duplicate, and a MATCH whose endpoints are both already bound
does not filter. Neither is visible from the statements alone.

**These tests cannot silently skip.** `SAMYAMA_REQUIRE_ENGINE=1` turns an
unreachable engine into a failure — CI sets it, so a green run without an
engine is not possible here.
"""

from __future__ import annotations

import json
import os

import pytest

from etl import load_education as loader
from etl.cypher_script import apply_schema
from etl.engine import Engine
from tests.test_schema_engine import require_engine

TEST_URL = os.environ.get("SAMYAMA_TEST_URL")

ROWS = [
    {"unitid": 231624, "cipcode_6digit": 110701, "award_level": 5,
     "majornum": 1, "race": 1, "sex": 1, "awards_6digit": 3},
    # Same institution, CIP, level and demographic — SECOND major. Under the
    # five-part key this row and the one above were one node and one of the
    # two award counts was lost.
    {"unitid": 231624, "cipcode_6digit": 110701, "award_level": 5,
     "majornum": 2, "race": 1, "sex": 1, "awards_6digit": 1},
    {"unitid": 232982, "cipcode_6digit": 512208, "award_level": 7,
     "majornum": 1, "race": 2, "sex": 2, "awards_6digit": 11},
]
INSTITUTIONS = [
    {"unitid": 231624, "inst_name": "Virginia Tech", "state_abbr": "VA"},
    {"unitid": 232982, "inst_name": "George Mason University",
     "state_abbr": "VA"},
]


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    """A scratch engine holding nothing, loaded ONCE with the slice above.

    `load()` reads the download from `data/education/`, so the slice is fed by
    repointing that cache — the alternative, passing rows as arguments, would
    leave the disk-reading half of the loader untested by the only tests that
    touch an engine.

    Module-scoped, and the engine must start EMPTY. Every test below then runs
    against one load, in file order: the re-load test is idempotent so it
    changes nothing, and the constraint probe writes its own node and is last.
    Re-running this file needs a fresh engine, which is what the refusal says.
    """
    require_engine()
    if not TEST_URL:
        pytest.fail("SAMYAMA_TEST_URL is unset; see this module's docstring")
    engine = Engine(TEST_URL)
    held = sum(
        int((engine.run(f"MATCH (n:{label}) WITH n RETURN count(n)")
             .get("records") or [[0]])[0][0])
        for label in ("Institution", "Programme", "Completion"))
    if held:
        pytest.fail(
            f"{TEST_URL} already holds {held} nodes of the labels this test "
            "writes. It refuses rather than damage a loaded graph, and it "
            "does not clean up after itself either — 1.1.0's scoped DETACH "
            "DELETE removes more than it names. Point SAMYAMA_TEST_URL at a "
            "fresh engine.")
    apply_schema(engine, quiet=True)

    cache = tmp_path_factory.mktemp("education")
    (cache / f"institutions-{loader.FIPS}-{loader.YEAR}.json").write_text(
        json.dumps({"rows": INSTITUTIONS}), encoding="utf-8")
    (cache / f"completions-{loader.FIPS}-{loader.YEAR}.json").write_text(
        json.dumps({"rows": ROWS}), encoding="utf-8")
    original, loader.CACHE = loader.CACHE, cache
    try:
        summary = loader.load(engine)
    finally:
        loader.CACHE = original
    return engine, cache, summary


def reload_with(engine, cache):
    original, loader.CACHE = loader.CACHE, cache
    try:
        return loader.load(engine)
    finally:
        loader.CACHE = original


def test_the_slice_lands_with_no_gap_between_issued_and_held(loaded):
    """**The gap column is the test.** A loader reporting what it issued is
    reporting its own intentions; this reads the graph back.

    Three rows, two institutions, two programmes, three completions — and
    three of each edge. The third completion is the one the five-part key
    would have swallowed.
    """
    engine, _, summary = loaded
    held = loader.in_the_graph(engine)
    assert held == {"Institution": 2, "Programme": 2, "Completion": 3,
                    "AT": 3, "IN": 3}, held
    assert summary["nodes_and_edges_created"] == sum(held.values())


def test_a_second_run_creates_nothing(loaded):
    """**This is the one that caught the defect.** The nodes were idempotent
    from the first version and the EDGES were not: a second run over the
    Virginia slice added 2,000 duplicate AT and IN edges, and only the
    read-back showed it.

    An edge MERGE would not have fixed it — #163 measured edge MERGE ignoring
    its property map on 1.1.0.
    """
    engine, cache, _ = loaded
    before = loader.in_the_graph(engine)
    again = reload_with(engine, cache)
    assert again["nodes_and_edges_created"] == 0, (
        "a second run created something; the load is not idempotent")
    assert loader.in_the_graph(engine) == before


def test_the_second_major_is_a_node_of_its_own(loaded):
    """The schema fix, stated against the graph rather than against the key
    function. Two completions at one institution, one CIP, one award level and
    one demographic, carrying 3 awards and 1 — and readable apart, because
    `major_number` is a property and not only a component of a hash."""
    engine, _, _ = loaded
    rows = engine.run(
        'MATCH (c:Completion) WHERE c.cip_code = "110701" '
        "WITH c RETURN c.major_number, c.awards").get("records") or []
    assert sorted((int(m), int(a)) for m, a in rows) == [(1, 3), (2, 1)], rows


def test_a_duplicate_create_is_not_rejected_by_the_constraint(loaded):
    """**Why the loader looks before it writes.** The schema declares
    `Completion.id` unique. Issuing the same CREATE twice leaves two nodes and
    raises nothing, so the constraint cannot be relied on to make the load
    idempotent — only the lookup can.

    Written as this repo's belief about 1.1.0: an engine that starts enforcing
    the constraint fails here rather than quietly changing what the loader's
    comments mean. Last in the file, because it writes.
    """
    engine, _, _ = loaded
    statement = ('CREATE (n:Completion {id: "duplicate-probe", '
                 'awards: 1, cip_code: "999999"})')
    engine.run(statement)
    engine.run(statement)
    held = (engine.run('MATCH (n:Completion) WHERE n.id = "duplicate-probe" '
                       "WITH n RETURN count(n)").get("records") or [[0]])[0][0]
    assert int(held) == 2, (
        "the unique constraint rejected a duplicate; if that is now true the "
        "loader's lookup-then-create rationale needs re-measuring")
