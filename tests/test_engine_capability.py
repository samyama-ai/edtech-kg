"""The committed record of what this engine does, against the engine.

edtech-kg#136. Every engine fact this repo relies on was typed into a comment
by hand — 240 edges, 359 rows from a query that should return none, 0 of 791
from one that should return some. `431 of 791` is what that costs: it was
written into two files and the graph said 463.

The record at `docs/sources/engine-capability-measured.json` is one measured
run, committed so the prose can be checked without an engine. Most of this file
needs no engine at all; the one test that does is gated and says so.

**The defects are recorded, not just the capabilities.** Four constructs here
are things the engine gets wrong, and a probe that only recorded what works
would leave exactly the facts that cost the most unrecorded. The expectations
below are written as this repo's BELIEFS, so an engine that starts behaving
correctly fails a test rather than silently changing what the documents mean.
"""

from __future__ import annotations

import json
import os

import pytest

from etl import probe_engine_capability as probe
from tests.test_schema_engine import SAMYAMA_URL, query, require_engine

RECORD = json.loads(probe.RECORD.read_text(encoding="utf-8"))

#: What the repo believes, and why each matters. The value is what the record
#: must hold; a mismatch means either the engine changed or a document is about
#: to go stale.
BELIEVED = {
    "requires_edges": 240,
    "courses": 791,
    "chains_any_length": 359,
    "chains_length_two_or_more": 119,
    "deepest_chain": 4,
    "isolated_courses": 463,
    # The defects.
    "repeated_variable_across_var_length": 240,   # should be 0
    "in_over_a_node_list": 0,                     # should be > 0
    "bare_single_node_map_absent_url": 791,       # should be 0
    "relationship_pattern_map_absent_url": 0,     # correct, and the contrast
    "not_in_list_unparenthesised": 0,             # should be 791
    "not_in_list_parenthesised": 791,             # correct, and the contrast
}


def test_the_record_holds_every_construct_the_probe_runs():
    """A construct added to the probe and not to the record is a measurement
    nobody sees, and one removed from the probe leaves a figure in the record
    that nothing re-runs."""
    assert set(RECORD["constructs"]) == {name for name, _, _ in probe.CONSTRUCTS}


def test_every_construct_says_why_it_is_measured():
    """A recorded number with no reason beside it is the thing this issue is
    about, one level up: a figure a reader cannot challenge."""
    thin = {name: got.get("why", "") for name, got in RECORD["constructs"].items()
            if len(got.get("why", "").split()) < 5}
    assert not thin, f"these are recorded without saying why: {thin}"


@pytest.mark.parametrize("name, expected", sorted(BELIEVED.items()))
def test_the_record_matches_what_this_repo_believes(name, expected):
    """The record and the prose have to agree, and this is the half that needs
    no engine — it runs on a clean checkout, in CI, on every push."""
    got = RECORD["constructs"][name]
    assert got.get("value") == expected, (
        f"{name} is recorded as {got.get('value', got.get('error'))} and this "
        f"repo's documents say {expected}. Either the engine changed — re-run "
        f"`python -m etl.probe_engine_capability --record` and update the "
        f"prose that quotes it — or the belief was wrong.")


def test_the_two_chain_figures_are_not_the_same_measurement():
    """119 and 359 sat in the same tier-4 paragraph, and they answer different
    questions: paths of length two or more, and paths of any length. The probe
    surfaced it by measuring both under one name."""
    assert (RECORD["constructs"]["chains_any_length"]["value"]
            > RECORD["constructs"]["chains_length_two_or_more"]["value"])


def test_a_bound_variable_in_a_property_map_is_still_a_parse_error():
    """Recorded as an ERROR rather than a row count, because a construct the
    engine refuses is a measurement too — and this one is why Q82 uses a
    `WHERE` for a figure it had already bound."""
    got = RECORD["constructs"]["bound_variable_in_property_map"]
    assert "error" in got, got
    assert "Parse error" in got["error"], got["error"]


def test_the_record_agrees_with_a_live_engine():
    """The only test here that needs one, and the reason the rest do not.

    A record nothing re-runs is the failure this issue names, so one test
    reconciles it — and it is gated, because re-measuring on every push needs a
    loaded district on every machine.
    """
    require_engine()
    held = query(SAMYAMA_URL, "MATCH (c:Course) RETURN count(c) AS n")
    courses = (held.get("records") or [[0]])[0][0] if "error" not in held else 0
    if not courses:
        message = (f"the graph at {SAMYAMA_URL} holds no Course nodes, so a "
                   f"predicate inside a WHERE is never evaluated and this "
                   f"checks nothing — load a district first")
        if os.environ.get("SAMYAMA_REQUIRE_DATA") == "1":
            pytest.fail(f"{message} — SAMYAMA_REQUIRE_DATA=1 forbids skipping this")
        pytest.skip(message)

    drifted = []
    for name, cypher, _ in probe.CONSTRUCTS:
        live = probe.rows(probe.ask(SAMYAMA_URL, cypher))
        recorded = {k: v for k, v in RECORD["constructs"][name].items()
                    if k in ("value", "rows", "error")}
        if live.get("error") and recorded.get("error"):
            continue          # both refuse; the message wording is not the fact
        if live != recorded:
            drifted.append(f"{name}: live {live}, recorded {recorded}")
    assert not drifted, (
        f"the committed record no longer matches this engine: {drifted}. "
        f"Re-run `python -m etl.probe_engine_capability --record` and update "
        f"every document quoting the figures that moved.")
