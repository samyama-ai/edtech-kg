"""The defect probe's verdicts, driven without an engine.

Every `still_defective` here is a boolean that decides whether an engine
upgrade is reported as a fix or passes unnoticed, so the arithmetic behind
each one is checked against fabricated readings rather than against whatever
the local engine happens to do today.
"""

from __future__ import annotations

import pytest

from etl.engine import Refused
from etl import engine_bench as bench
from etl import probe_engine_defects as probe


class Fake:
    """An engine that answers from a script, and records what it was asked."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []

    def run(self, cypher):
        self.asked.append(cypher)
        return self.answers.pop(0) if self.answers else {"records": []}


def test_a_bare_aggregate_row_is_not_read_as_a_value():
    """The engine returns one row over an empty graph, so `records != []` is
    not an emptiness check. `scalar` must read the cell, not count the row."""
    assert probe.scalar(Fake([{"records": [[None]]}]), "q") is None
    assert probe.scalar(Fake([{"records": []}]), "q") is None
    assert probe.scalar(Fake([{"records": [[7]]}]), "q") == 7


def test_merge_degrading_alone_is_not_the_finding():
    """MERGE slowing while MATCH slows too is a slow engine, not this bug.
    The verdict requires MERGE to fall and MATCH to hold."""
    def points(first_merge, last_merge, first_match, last_match):
        return [{"nodes_at_start": 1000, "nodes_at_end": 1360, "merge_per_sec": first_merge,
                 "create_per_sec": 800.0, "match_per_sec": first_match},
                {"nodes_at_start": 16000, "nodes_at_end": 16360, "merge_per_sec": last_merge,
                 "create_per_sec": 800.0, "match_per_sec": last_match}]

    # THE PROBE'S OWN function, not a copy of its rule. The first version of
    # this test reimplemented the verdict and so agreed with itself whatever
    # the probe did.
    verdict = bench.merge_is_still_defective

    # The real shape: MERGE collapses, MATCH holds.
    assert verdict(points(640.0, 68.0, 750.0, 740.0)) is True
    # Everything slowed — a loaded machine, not an ignored index.
    assert verdict(points(640.0, 68.0, 750.0, 90.0)) is False
    # MERGE held — the defect is fixed and must be reported as fixed.
    assert verdict(points(640.0, 600.0, 750.0, 740.0)) is False
    # And no points at all is not evidence of a defect.
    assert verdict([]) is False


def test_the_probe_refuses_a_loaded_engine(monkeypatch):
    """It writes tens of thousands of nodes and cannot remove them — that
    inability is one of the defects. Running against a loaded graph corrupts
    it, which is how :8200 came to hold four copies of one district."""
    monkeypatch.setattr(probe, "api",
                        lambda url, path, *a, **k:
                        (200, {"storage": {"nodes": 4392}, "version": "1.7.0"}))
    # Its own labels are cleared first — that is what makes the probe
    # re-runnable — so the count that decides is what is LEFT afterwards.
    monkeypatch.setattr(probe, "clear_our_own", lambda engine: 4392)
    with pytest.raises(probe.Unusable) as refused:
        probe.measure("http://localhost:9999")
    assert "4392" in str(refused.value)
    assert "did not write" in str(refused.value)
    assert "scratch" in str(refused.value)


def test_a_graph_holding_only_a_previous_run_is_cleared_not_refused(monkeypatch):
    """The probe wrote ~33,000 nodes and then refused to start against them,
    so re-measuring meant destroying the container. Zero left after clearing
    its own labels means the graph was its own last run."""
    monkeypatch.setattr(probe, "api",
                        lambda url, path, *a, **k:
                        (200, {"storage": {"nodes": 33000}, "version": "1.7.0"}))
    monkeypatch.setattr(probe, "clear_our_own", lambda engine: 0)
    monkeypatch.setattr(probe, "remove_is_a_no_op", lambda e: {"ok": 1})
    monkeypatch.setattr(probe, "tenant_is_ignored", lambda u, e: {"ok": 1})
    monkeypatch.setattr(probe, "merge_ignores_the_index",
                        lambda e, sizes: {"ok": 1})
    measured = probe.measure("http://localhost:9999")
    assert measured["remove"] == {"ok": 1}, "the run was refused"


def test_an_engine_that_does_not_answer_status_is_refused(monkeypatch):
    monkeypatch.setattr(probe, "api", lambda *a, **k: (503, None))
    with pytest.raises(probe.Unusable):
        probe.measure("http://localhost:9999")


def test_a_tenant_api_that_stops_accepting_the_call_stops_the_run(monkeypatch):
    """The probe's own worst failure mode, guarded.

    Its first version sent only `id`, got a 422, and would have recorded the
    API as REFUSING these calls — reporting #149 as absent when it is
    present. A status other than 201 now stops the run rather than being
    stored as a finding.
    """
    monkeypatch.setattr(probe, "api",
                        lambda url, path, method="GET", payload=None:
                        (422, None) if path == "/api/tenants" else (200, None))
    with pytest.raises(probe.Unusable) as refused:
        probe.tenant_is_ignored("http://localhost:9999",
                                Fake([{"records": [[1]]}] * 8))
    assert "422" in str(refused.value)
    assert "re-recording" in str(refused.value)


def test_the_warmup_is_not_inside_the_timing():
    """At a batch of 40 with no warm-up, MERGE measured FASTER at 2,000 nodes
    than at 500 — the opposite of the finding, because the first call of a
    statement shape pays for parsing and planning that none of the rest do."""
    engine = Fake([{"records": []}] * (bench.WARMUP + 5))
    bench.rate(engine, lambda i: f"CREATE (n {{i: {i}}})", 5)
    assert len(engine.asked) == bench.WARMUP + 5, (
        "the warm-up must run, and must not be counted in the batch")
    assert bench.WARMUP > 0 and bench.BATCH >= 100, (
        "a batch this small is dominated by warm-up; 40 gave a non-monotonic "
        "table that reversed the finding")


def test_the_verdict_does_not_require_the_row_to_have_lost_the_key():
    """**The case #163 originally described must not report FIXED.**

    Requiring `row_no_longer_holds_it` did exactly that: an engine where the
    row keeps the property and every read is stale — the issue's own wording —
    came out as fixed. That is the milder version of this defect and it is
    still the defect. What the row did is a refinement recorded beside the
    finding, not a gate on it.
    """
    before = {"projection": "keep", "count_by_value": 1,
              "row_has_the_key": True, "row_value": "keep"}

    # The issue's original claim: nothing changed anywhere.
    unchanged = dict(before)
    assert probe.reads_disagree_with_the_row(before, unchanged) is True

    # What 1.1.0 actually does: the row loses the key, the reads do not.
    row_cleared = {"projection": "keep", "count_by_value": 1,
                   "row_has_the_key": False, "row_value": None}
    assert probe.reads_disagree_with_the_row(before, row_cleared) is True

    # Genuinely fixed: the reads follow the write.
    fixed = {"projection": None, "count_by_value": 0,
             "row_has_the_key": False, "row_value": None}
    assert probe.reads_disagree_with_the_row(before, fixed) is False


def test_a_probe_run_can_follow_another_on_the_same_engine():
    """It wrote ~33,000 nodes and then refused to start against them, so
    re-measuring meant destroying the container. Its own labels are cleared;
    anything else is still refused."""
    assert probe.LABEL in probe.OUR_LABELS
    assert all(lbl for lbl in probe.OUR_LABELS), "an unnamed label survives a reset"


def test_a_ratio_with_an_unmeasured_end_is_none_not_zero():
    """`rate()` returns 0.0 when the clock reports no elapsed time. Only the
    denominator was guarded, so a 0.0 numerator gave `merge_fell_by: 0.0` — a
    number that reads as "it did not fall" and means "nothing was measured"."""
    assert bench.ratio(0.0, 500.0) is None
    assert bench.ratio(500.0, 0.0) is None
    assert bench.ratio(640.0, 80.0) == 8.0


def test_the_fresh_label_control_is_declared_too(monkeypatch):
    """Without the constraint the "identical MERGE" differed in two variables
    — label size AND index presence — so a fast result could mean either. It
    is an isolating control only if the one difference is label size."""
    import inspect
    source = inspect.getsource(bench.merge_ignores_the_index)
    assert "declare_constraint(engine, f\"{LABEL}Fresh\")" in source, (
        "the fresh control label is measured without a uniqueness constraint")


def test_a_refused_constraint_is_recorded_rather_than_swallowed():
    """The old `except Refused: pass` carried a comment saying it was
    "recorded, not swallowed", and nothing was written and no field existed."""
    class Refuses:
        def run(self, cypher):
            raise Refused(400, "constraint already declared")

    said = bench.declare_constraint(Refuses(), "X")
    assert said.startswith("refused: "), said

    class Accepts:
        def run(self, cypher):
            return {"records": []}

    assert bench.declare_constraint(Accepts(), "X") == "declared"
