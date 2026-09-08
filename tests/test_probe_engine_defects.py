"""The defect probe's verdicts, driven without an engine.

Every `still_defective` here is a boolean that decides whether an engine
upgrade is reported as a fix or passes unnoticed, so the arithmetic behind
each one is checked against fabricated readings rather than against whatever
the local engine happens to do today.
"""

from __future__ import annotations

import pytest

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
    with pytest.raises(probe.Unusable) as refused:
        probe.measure("http://localhost:9999")
    assert "4392" in str(refused.value)
    assert "scratch" in str(refused.value)


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
