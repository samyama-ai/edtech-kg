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
from etl.engine import ENGINE_VERSION, Engine
from tests.test_schema_engine import SAMYAMA_URL, require_engine

RECORD = json.loads(probe.RECORD.read_text(encoding="utf-8"))


def test_the_record_was_measured_against_the_pinned_build():
    """Every other figure in this repo describes one build.

    A record taken from a different engine passes every other check here and
    quietly means something else — the drift this probe exists to remove,
    arriving through the probe.
    """
    assert RECORD["engine_version_reported"] == ENGINE_VERSION


def test_the_records_note_is_the_one_the_probe_writes():
    """`_` in the JSON and `RECORD_NOTE` in the module are one sentence stored
    twice. Editing either alone leaves the other stale, which is the same class
    of drift as every figure this file exists to hold."""
    assert RECORD["_"] == probe.RECORD_NOTE


def test_the_record_says_which_graph_it_measured():
    """`/api/query` selects with `graph`, and the probe used to send `tenant` —
    so it measured whatever the default is while its docstring said otherwise.
    On this build nothing isolates (edtech-kg#149), which makes naming the
    field correctly more important rather than less: the record has to say what
    it claims to be about."""
    assert RECORD.get("graph"), "the record does not name the graph it measured"

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
    "in_over_a_node_list_from_a_separate_match": 0,        # should be > 0
    "not_in_over_a_node_list_from_a_separate_match": 0,    # should be very large
    "in_over_a_node_list_unwound_from_the_path": 863,      # correct, the contrast
    "bare_single_node_map_absent_url": 791,       # should be 0
    "relationship_pattern_map_absent_url": 0,     # correct, and the contrast
    "not_in_list_unparenthesised": 0,             # should be 791
    "not_in_list_parenthesised": 791,             # correct, and the contrast
}


def test_the_node_list_defect_is_only_the_separate_match_shape():
    """Both halves, because the first version of this recorded neither.

    It measured one query that dropped `x` before the WHERE and recorded the
    scoping result as evidence that "`IN` over a list of nodes matches
    nothing". Carried through properly, the operator works — 863. What is
    broken is `x` from an INDEPENDENT `MATCH`, where the test matches nothing
    in either direction rather than refusing, and that is the shape Q68 needs.
    """
    got = RECORD["constructs"]
    assert got["in_over_a_node_list_from_a_separate_match"]["value"] == 0
    assert got["not_in_over_a_node_list_from_a_separate_match"]["value"] == 0, (
        "both directions must be 0 — a query matching nothing either way is "
        "the finding; one of them working would make Q68 answerable")
    assert got["in_over_a_node_list_unwound_from_the_path"]["value"] > 0, (
        "the operator works when the list is unwound from the path, and "
        "recording only the broken shape overstates the defect")


def test_a_bare_aggregate_returns_one_row_of_null_not_no_rows():
    """The construct whose recorded SHAPE carries the finding.

    `{"value": None}` and a missing key are indistinguishable under
    `got.get("value")`, so the belief table cannot express this one — which is
    why it gets its own test. It is the reason `records != []` is not an
    emptiness check, and that cost a review round.
    """
    got = RECORD["constructs"]["aggregate_over_an_absent_label"]
    assert "value" in got, f"recorded as {got} — the one row was lost"
    assert got["value"] is None, got


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
    counted = probe.ask(Engine(SAMYAMA_URL, RECORD["graph"]),
                        "MATCH (c:Course) RETURN count(c) AS n")
    courses = (counted.get("records") or [[0]])[0][0] if "error" not in counted else 0
    if not courses:
        message = (f"the graph at {SAMYAMA_URL} holds no Course nodes, so a "
                   f"predicate inside a WHERE is never evaluated and this "
                   f"checks nothing — load a district first")
        if os.environ.get("SAMYAMA_REQUIRE_DATA") == "1":
            pytest.fail(f"{message} — SAMYAMA_REQUIRE_DATA=1 forbids skipping this")
        pytest.skip(message)

    # THE SAME CLIENT and the same graph the record names. This counted
    # courses through one helper and ran the constructs through another that
    # sent a different selector key — so a drift report could have been two
    # graphs disagreeing rather than the engine changing.
    engine = Engine(SAMYAMA_URL, RECORD["graph"])
    drifted = []
    for name, cypher, _ in probe.CONSTRUCTS:
        live = probe.rows(probe.ask(engine, cypher))
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


def test_a_retried_code_is_never_recorded_as_a_fact_about_a_construct():
    """`Engine` retries 429 and 5xx and then raises. One of those arriving
    means the retries were exhausted — a dying or rate-limited engine — and
    committing it as the recorded behaviour of a construct is the failure the
    refusal/transport split exists to prevent.

    `< 500` sent 429 down the measurement path, so a rate-limited run wrote
    `{"error": "429 on: …"}` into the record as the fact.
    """
    from etl.engine import RETRIED, Refused

    class Raising(Engine):
        def __init__(self, error):
            super().__init__("http://fake", "g")
            self.error = error

        def run(self, query, attempts=4):
            raise self.error

    for code in RETRIED:
        with pytest.raises(probe.Unreachable, match="after retries"):
            probe.ask(Raising(Refused(code, f"{code} on: X", detail="x")), "X")

    # And the other side: a refusal the engine MEANT is recorded, in both
    # shapes it arrives in — 400 from this build, 200-with-an-error-key
    # documented by etl/engine.py. The message lands on opposite sides of the
    # newline in the two, so the engine's own text is carried explicitly.
    for refused in (Refused(400, "400 on: X\nParse error: bad", detail="Parse error: bad"),
                    Refused(200, "Parse error: bad\n  on: X", detail="Parse error: bad")):
        assert probe.ask(Raising(refused), "X") == {"error": "Parse error: bad"}

